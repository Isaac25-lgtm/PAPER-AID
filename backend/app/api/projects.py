"""Proposal project routes. Thin, like app.api.routes: parse input, call app.proposals.service."""

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile
from fastapi.responses import Response
from pydantic import Field

from app.core.auth import current_user
from app.jobs.models import Camel, JobView
from app.jobs.service import User
from app.proposals import feedback, rulebook
from app.proposals import service as projects
from app.proposals.models import CitationStyle, EvidenceItem, FeedbackStatus, ProjectView, ProposalInputs, ProposalPlan, SampleSize, TitlePage
from app.runtime import Runtime, get_runtime

router = APIRouter(prefix="/api/projects")
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class Details(Camel):
    inputs: ProposalInputs
    title_page: TitlePage = TitlePage()
    citation: CitationStyle = "APA6"


class PlanEdit(Camel):
    plan: ProposalPlan
    base_version: int


class StepRequest(Camel):
    step: Literal["PLAN", "CHAPTER_1", "CHAPTER_2", "CHAPTER_3", "CONCEPT", "REVISE_1", "REVISE_2", "REVISE_3", "PROFILE"]
    note: str = ""


class FeedbackText(Camel):
    text: str = Field(min_length=3, max_length=30000)


class FeedbackEdit(Camel):
    chapter: int | None = None
    sections: list[str] = Field(default=[], max_length=12)
    status: FeedbackStatus = "OPEN"
    response: str = Field(default="", max_length=1000)


class ChapterChoice(Camel):
    version: int
    approved: bool = False


@router.get("/rulebook")
def rulebook_summary() -> dict:
    """What the forms need: levels, citation profiles and where the rules come from."""
    book = rulebook.load(rulebook.DEFAULT)
    return {
        "id": book["id"],
        "institution": book["institution"],
        "source": book["source"],
        "levels": {k: {"label": v["label"], "pages": v["pages"]} for k, v in book["levels"].items()},
        "citationProfiles": {k: v["label"] for k, v in book["citation_profiles"].items()},
        "defaultCitation": book["default_citation"],
    }


@router.get("", response_model=list[ProjectView])
def list_projects(user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> list[ProjectView]:
    return projects.list_mine(rt, user)


@router.post("", response_model=ProjectView)
def create(body: Details, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.create(rt, user, body.inputs, body.title_page, body.citation)


@router.get("/{project_id}", response_model=ProjectView)
def get(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.get(rt, user, project_id)


@router.post("/{project_id}/details", response_model=ProjectView)
def details(project_id: str, body: Details, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.update_details(rt, user, project_id, body.inputs, body.title_page, body.citation)


@router.delete("/{project_id}", status_code=204)
def delete(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    projects.delete(rt, user, project_id)
    return Response(status_code=204)


@router.post("/{project_id}/plan", response_model=ProjectView)
def save_plan(project_id: str, body: PlanEdit, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.save_plan(rt, user, project_id, body.plan, body.base_version)


@router.post("/{project_id}/plan/approve", response_model=ProjectView)
def approve_plan(project_id: str, base_version: int = Body(..., embed=True, alias="baseVersion"), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.approve_plan(rt, user, project_id, base_version)


@router.post("/{project_id}/plan/candidate", response_model=ProjectView)
def candidate(project_id: str, accept: bool = Body(..., embed=True), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.take_candidate(rt, user, project_id, accept)


@router.post("/{project_id}/sample-size")
def sample_size(project_id: str, body: SampleSize, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> dict:
    """What PaperAid will calculate from these figures (nothing is saved)."""
    projects.get(rt, user, project_id)
    return projects.sample_size_preview(body)


@router.post("/{project_id}/steps", response_model=projects.StepQuote)
def quote_step(project_id: str, body: StepRequest, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> projects.StepQuote:
    return projects.quote_step(rt, user, project_id, body.step, body.note)


@router.post("/{project_id}/steps/{job_id}/submit", response_model=JobView)
def submit_step(project_id: str, job_id: str, quote_id: str = Body(..., embed=True, alias="quoteId"), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> JobView:
    return projects.submit_step(rt, user, project_id, job_id, quote_id)


@router.get("/{project_id}/chapters/{number}", response_model=projects.ChapterView)
def chapter(project_id: str, number: int, version: int | None = Query(None), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> projects.ChapterView:
    return projects.chapter(rt, user, project_id, number, version)


@router.post("/{project_id}/chapters/{number}", response_model=ProjectView)
def choose_chapter(project_id: str, number: int, body: ChapterChoice, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.set_chapter(rt, user, project_id, number, body.version, body.approved)


@router.get("/{project_id}/evidence", response_model=list[EvidenceItem])
def evidence(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> list[EvidenceItem]:
    return projects.library(rt, user, project_id)


@router.get("/{project_id}/export")
def export(project_id: str, final: bool = Query(False), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    """Built on request (no AI) and streamed; the browser saves it from the response."""
    return _docx(*projects.export_docx(rt, user, project_id, final))


def _docx(data: bytes, name: str) -> Response:
    ascii_name = name.encode("ascii", "ignore").decode() or "proposal.docx"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"
    return Response(data, media_type=DOCX, headers={"Content-Disposition": disposition, "Cache-Control": "no-store"})


@router.get("/{project_id}/export.pdf")
def export_pdf(project_id: str, final: bool = Query(False), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    data, name = projects.export_pdf(rt, user, project_id, final)
    ascii_name = name.encode("ascii", "ignore").decode() or "proposal.pdf"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": disposition, "Cache-Control": "no-store"})


@router.get("/{project_id}/concept/export")
def export_concept(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return _docx(*projects.export_concept(rt, user, project_id))


@router.get("/{project_id}/chapters/{number}/compare", response_model=projects.Comparison)
def compare(project_id: str, number: int, older: int = Query(...), newer: int = Query(...), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> projects.Comparison:
    return projects.compare(rt, user, project_id, number, older, newer)


@router.post("/{project_id}/guide", response_model=ProjectView)
async def upload_guide(project_id: str, file: UploadFile = File(...), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    data = await file.read(rt.settings.max_upload_bytes + 1)
    return projects.upload_guide(rt, user, project_id, file.filename or "guide", data)


@router.post("/{project_id}/rulebook/default", response_model=ProjectView)
def default_rulebook(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.use_default_rulebook(rt, user, project_id)


@router.post("/{project_id}/feedback", response_model=ProjectView)
def add_feedback(project_id: str, body: FeedbackText, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.add_feedback(rt, user, project_id, body.text)


@router.post("/{project_id}/feedback/file", response_model=ProjectView)
async def add_feedback_file(project_id: str, file: UploadFile = File(...), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    data = await file.read(feedback.MAX_FILE_BYTES + 1)
    return projects.add_feedback(rt, user, project_id, "", file.filename or "feedback", data)


@router.get("/{project_id}/feedback/report")
def feedback_report(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return _docx(*projects.response_report(rt, user, project_id))


@router.post("/{project_id}/feedback/{comment_id}", response_model=ProjectView)
def edit_feedback(project_id: str, comment_id: str, body: FeedbackEdit, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.update_feedback(rt, user, project_id, comment_id, body.chapter, body.sections, body.status, body.response)


@router.delete("/{project_id}/feedback/{comment_id}", response_model=ProjectView)
def delete_feedback(project_id: str, comment_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.delete_feedback(rt, user, project_id, comment_id)
