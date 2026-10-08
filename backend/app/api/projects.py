"""Proposal project routes. Thin, like app.api.routes: parse input, call app.proposals.service."""

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import Field

from app.api.public import student_json
from app.core.auth import current_user
from app.jobs.models import Camel, JobView
from app.jobs.service import User
from app.proposals import feedback, rulebook
from app.proposals import service as projects
from app.proposals.models import CitationStyle, EvidenceItem, FeedbackStatus, ProjectView, ProposalInputs, ProposalPlan, SampleSize, TitlePage, Variables
from app.runtime import Runtime, get_runtime

router = APIRouter(prefix="/api/projects")
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class Details(Camel):
    inputs: ProposalInputs
    title_page: TitlePage = TitlePage()
    citation: CitationStyle = "APA6"
    goal: Literal["FULL", "CONCEPT"] = "FULL"  # creation only: a concept note first, or the full proposal


class PlanEdit(Camel):
    plan: ProposalPlan
    base_version: int


class StepRequest(Camel):
    step: Literal["PLAN", "CHAPTER_1", "CHAPTER_2", "CHAPTER_3", "CONCEPT", "REVISE_1", "REVISE_2", "REVISE_3", "REVISE_4", "COMPLETE_1", "COMPLETE_2", "COMPLETE_3", "COMPLETE_4", "PROFILE"]
    note: str = ""
    comments: list[str] = Field(default=[], max_length=50)  # REVISE: exactly these requests


class FeedbackText(Camel):
    text: str = Field(min_length=3, max_length=30000)


class ChangeRequest(Camel):
    instruction: str = Field(min_length=3, max_length=2000)
    sections: list[str] = Field(default=[], max_length=40)


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
    return projects.create(rt, user, body.inputs, body.title_page, body.citation, body.goal)


@router.get("/{project_id}", response_model=ProjectView)
def get(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.get(rt, user, project_id)


class GuideAnswer(Camel):
    id: str = Field(max_length=80)
    answer: Literal["KEEP", "STANDARD"]


@router.post("/{project_id}/guide-answers", response_model=ProjectView)
def answer_guide(project_id: str, body: GuideAnswer, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    """Where the student's guide departs a lot from the standard guide: keep it, or take the standard version."""
    return projects.answer_guide(rt, user, project_id, body.id, body.answer)


@router.post("/{project_id}/details", response_model=ProjectView)
def details(project_id: str, body: Details, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.update_details(rt, user, project_id, body.inputs, body.title_page, body.citation)


class Setting(Camel):
    study_area: str = Field(max_length=200)
    population: str = Field(max_length=200)
    base_version: int


@router.post("/{project_id}/setting", response_model=ProjectView)
def confirm_setting(project_id: str, body: Setting, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    """Where the study takes place and who it studies, as PaperAid proposed them or as the student corrects them."""
    return projects.confirm_setting(rt, user, project_id, body.study_area, body.population, body.base_version)


@router.delete("/{project_id}", status_code=204)
def delete(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    projects.delete(rt, user, project_id)
    return Response(status_code=204)


@router.post("/{project_id}/plan", response_model=ProjectView)
def save_plan(project_id: str, body: PlanEdit, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.save_plan(rt, user, project_id, body.plan, body.base_version)


@router.post("/{project_id}/plan/approve", response_model=ProjectView)
def approve_plan(project_id: str, base_version: int = Body(..., embed=True, alias="baseVersion"), acknowledge: list[str] = Body(default=[], embed=True, max_length=4),
                 user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.approve_plan(rt, user, project_id, base_version, acknowledge)


@router.post("/{project_id}/continue", response_model=ProjectView)
def continue_full(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.continue_to_full(rt, user, project_id)


@router.post("/{project_id}/plan/candidate", response_model=ProjectView)
def candidate(project_id: str, accept: bool = Body(..., embed=True), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.take_candidate(rt, user, project_id, accept)


@router.post("/{project_id}/sample-size")
def sample_size(project_id: str, body: SampleSize, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> dict:
    """What PaperAid will calculate from these figures (nothing is saved)."""
    projects.get(rt, user, project_id)
    return projects.sample_size_preview(body)


@router.post("/{project_id}/steps", response_model=projects.StepQuote)
def quote_step(project_id: str, body: StepRequest, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return student_json(rt, projects.quote_step(rt, user, project_id, body.step, body.note, body.comments))


@router.post("/{project_id}/steps/{job_id}/submit", response_model=JobView)
def submit_step(project_id: str, job_id: str, quote_id: str = Body(..., embed=True, alias="quoteId"), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return student_json(rt, projects.submit_step(rt, user, project_id, job_id, quote_id))


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


@router.get("/{project_id}/export.zip")
def export_latex(project_id: str, final: bool = Query(False), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    data, name = projects.export_latex(rt, user, project_id, final)
    ascii_name = name.encode("ascii", "ignore").decode() or "proposal.zip"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"
    return Response(data, media_type="application/zip", headers={"Content-Disposition": disposition, "Cache-Control": "no-store"})


@router.get("/{project_id}/concept/export")
def export_concept(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return _docx(*projects.export_concept(rt, user, project_id))


@router.get("/{project_id}/chapters/{number}/compare", response_model=projects.Comparison)
def compare(project_id: str, number: int, older: int = Query(...), newer: int = Query(...), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> projects.Comparison:
    return projects.compare(rt, user, project_id, number, older, newer)


@router.post("/{project_id}/guide", response_model=ProjectView)
def upload_guide(project_id: str, file: UploadFile = File(...), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    # A plain (threadpool) route: parsing a Word file or PDF must not block the event loop (M21).
    data = file.file.read(rt.settings.max_upload_bytes + 1)
    return projects.upload_guide(rt, user, project_id, file.filename or "guide", data)


@router.post("/{project_id}/rulebook/default", response_model=ProjectView)
def default_rulebook(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.use_default_rulebook(rt, user, project_id)


@router.post("/{project_id}/chapters/{number}/request", response_model=ProjectView)
def request_changes(project_id: str, number: int, body: ChangeRequest, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.request_changes(rt, user, project_id, number, body.instruction, body.sections)


@router.post("/{project_id}/chapters/{number}/request/with-document", response_model=ProjectView)
def request_changes_with_document(project_id: str, number: int, instruction: str = Form(..., min_length=3, max_length=2000), sections: str = Form(default=""),
                                  file: UploadFile = File(...), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    """Ask for changes with a document added for context (Word or PDF): its text goes to the writer with the request."""
    data = file.file.read(rt.settings.max_upload_bytes + 1)
    return projects.request_changes_with_document(rt, user, project_id, number, instruction, [s for s in sections.split(",") if s], file.filename or "document", data)


@router.post("/{project_id}/start", response_model=ProjectView)
def start(project_id: str, accept_sampling: bool = Body(default=False, embed=True, alias="acceptSampling"), user: User = Depends(current_user),
          rt: Runtime = Depends(get_runtime)) -> ProjectView:
    """One Start (owner decision 2026-10-01): plan, then the first chapter, by itself. `acceptSampling`:
    the student ticked the standard sample-size settings."""
    return projects.start(rt, user, project_id, accept_sampling)


class FrameworkEdit(Camel):
    base_version: int
    style: Literal["MONO", "GREEN", "BLUE"] | None = None
    variables: Variables | None = None


@router.post("/{project_id}/framework", response_model=ProjectView)
def edit_framework(project_id: str, body: FrameworkEdit, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    """The student's edit of the conceptual framework: its style (only redraws it) or its variables."""
    return projects.edit_framework(rt, user, project_id, body.base_version, body.style, body.variables)


@router.get("/{project_id}/framework.png")
def framework(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    """The conceptual framework figure, as it appears in the Word file."""
    return Response(projects.framework_png(rt, user, project_id), media_type="image/png", headers={"Cache-Control": "private, no-store"})


@router.post("/{project_id}/feedback", response_model=ProjectView)
def add_feedback(project_id: str, body: FeedbackText, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    return projects.add_feedback(rt, user, project_id, body.text)


@router.post("/{project_id}/feedback/file", response_model=ProjectView)
def add_feedback_file(project_id: str, file: UploadFile = File(...), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ProjectView:
    data = file.file.read(feedback.MAX_FILE_BYTES + 1)
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
