"""Proposal project routes. Thin, like app.api.routes: parse input, call app.proposals.service."""

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import Response

from app.core.auth import current_user
from app.jobs.models import Camel, JobView
from app.jobs.service import User
from app.proposals import rulebook
from app.proposals import service as projects
from app.proposals.models import CitationStyle, EvidenceItem, ProjectView, ProposalInputs, ProposalPlan, SampleSize, TitlePage
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
    step: Literal["PLAN", "CHAPTER_1", "CHAPTER_2", "CHAPTER_3"]
    note: str = ""


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
    data, name = projects.export_docx(rt, user, project_id, final)
    ascii_name = name.encode("ascii", "ignore").decode() or "proposal.docx"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"
    return Response(data, media_type=DOCX, headers={"Content-Disposition": disposition, "Cache-Control": "no-store"})
