"""Work routes (concept notes, coursework, funding proposals). Thin, like app.api.routes: parse the
input, call app.works.service. Every edit carries the version it started from."""

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import Field

from app.api.public import student_json
from app.core.auth import current_user
from app.jobs.models import Camel, JobView
from app.jobs.service import User
from app.runtime import Runtime, get_runtime
from app.works import service as works
from app.works.models import Budget, CitationStyle, ResultsModel, SourceRole, WorkInputs, WorkPlan, WorkView

router = APIRouter(prefix="/api/works")
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class NewWork(Camel):
    kind: Literal["CONCEPT_NOTE", "COURSEWORK", "FUNDING_PROPOSAL"]
    variant: str
    mode: str = ""
    inputs: WorkInputs
    citation: CitationStyle = "APA7"


class Details(Camel):
    inputs: WorkInputs
    mode: str | None = None
    variant: str | None = None
    citation: CitationStyle | None = None
    base_version: int


class Answers(Camel):
    answers: dict[str, str] = Field(default={}, max_length=80)
    skip_rest: bool = False
    base_version: int


class Pasted(Camel):
    role: SourceRole
    name: str = Field(default="", max_length=120)
    text: str = Field(min_length=10, max_length=600_000)


class PlanEdit(Camel):
    plan: WorkPlan
    base_version: int


class ResultsEdit(Camel):
    results: ResultsModel
    base_version: int


class BudgetEdit(Camel):
    budget: Budget
    base_version: int


class StepRequest(Camel):
    step: Literal["READ", "PLAN", "DRAFT", "REVISE"]
    note: str = Field(default="", max_length=1000)


class ChangeRequest(Camel):
    instruction: str = Field(min_length=3, max_length=2000)
    sections: list[str] = Field(default=[], max_length=60)


@router.get("", response_model=list[WorkView])
def list_works(user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> list[WorkView]:
    return works.list_mine(rt, user)


@router.post("", response_model=WorkView)
def create(body: NewWork, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.create(rt, user, body.kind, body.variant, body.mode, body.inputs, body.citation)


@router.get("/{work_id}", response_model=WorkView)
def get(work_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.get(rt, user, work_id)


@router.delete("/{work_id}", status_code=204)
def delete(work_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    works.delete(rt, user, work_id)
    return Response(status_code=204)


@router.post("/{work_id}/details", response_model=WorkView)
def details(work_id: str, body: Details, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.update_inputs(rt, user, work_id, body.inputs, body.mode, body.variant, body.citation, body.base_version)


@router.post("/{work_id}/answers", response_model=WorkView)
def answers(work_id: str, body: Answers, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.answer(rt, user, work_id, body.answers, body.base_version, body.skip_rest)


@router.post("/{work_id}/spec/confirm", response_model=WorkView)
def confirm(work_id: str, base_version: int = Body(..., embed=True, alias="baseVersion"), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.confirm_spec(rt, user, work_id, base_version)


@router.post("/{work_id}/ai-note", response_model=WorkView)
def ai_note(work_id: str, on: bool = Body(..., embed=True), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.set_ai_note(rt, user, work_id, on)


@router.post("/{work_id}/sources", response_model=WorkView)
def upload_source(work_id: str, role: SourceRole = Form(...), file: UploadFile = File(...), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    data = file.file.read(rt.settings.max_upload_bytes + 1)
    return works.upload_source(rt, user, work_id, role, file.filename or "document", data)


@router.post("/{work_id}/sources/text", response_model=WorkView)
def paste_source(work_id: str, body: Pasted, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.paste_source(rt, user, work_id, body.role, body.name, body.text)


@router.delete("/{work_id}/sources/{source_id}", response_model=WorkView)
def remove_source(work_id: str, source_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.remove_source(rt, user, work_id, source_id)


@router.post("/{work_id}/plan", response_model=WorkView)
def save_plan(work_id: str, body: PlanEdit, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.save_plan(rt, user, work_id, body.plan, body.base_version)


@router.post("/{work_id}/plan/approve", response_model=WorkView)
def approve_plan(work_id: str, base_version: int = Body(..., embed=True, alias="baseVersion"), acknowledge: list[str] = Body(default=[], embed=True, max_length=4),
                 user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.approve_plan(rt, user, work_id, base_version, acknowledge)


@router.post("/{work_id}/plan/candidate", response_model=WorkView)
def candidate(work_id: str, accept: bool = Body(..., embed=True), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.take_candidate(rt, user, work_id, accept)


@router.post("/{work_id}/results", response_model=WorkView)
def save_results(work_id: str, body: ResultsEdit, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.save_results(rt, user, work_id, body.results, body.base_version)


@router.post("/{work_id}/results/approve", response_model=WorkView)
def approve_results(work_id: str, base_version: int = Body(..., embed=True, alias="baseVersion"), acknowledge: list[str] = Body(default=[], embed=True, max_length=4),
                    user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.approve_results(rt, user, work_id, base_version, acknowledge)


@router.post("/{work_id}/budget", response_model=WorkView)
def save_budget(work_id: str, body: BudgetEdit, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.save_budget(rt, user, work_id, body.budget, body.base_version)


@router.post("/{work_id}/steps", response_model=works.WorkStepQuote)
def quote_step(work_id: str, body: StepRequest, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return student_json(rt, works.quote_step(rt, user, work_id, body.step, body.note))


@router.post("/{work_id}/steps/{job_id}/submit", response_model=JobView)
def submit_step(work_id: str, job_id: str, quote_id: str = Body(..., embed=True, alias="quoteId"), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return student_json(rt, works.submit_step(rt, user, work_id, job_id, quote_id))


@router.post("/{work_id}/requests", response_model=WorkView)
def request_changes(work_id: str, body: ChangeRequest, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.request_changes(rt, user, work_id, body.instruction, body.sections)


@router.delete("/{work_id}/requests/{request_id}", response_model=WorkView)
def remove_request(work_id: str, request_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.remove_request(rt, user, work_id, request_id)


@router.post("/{work_id}/version", response_model=WorkView)
def choose_version(work_id: str, version: int = Body(..., embed=True), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WorkView:
    return works.set_version(rt, user, work_id, version)


@router.get("/{work_id}/document", response_model=works.DocumentView)
def document(work_id: str, version: int | None = Query(None), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> works.DocumentView:
    return works.document(rt, user, work_id, version)


def _file(data: bytes, name: str, media: str) -> Response:
    disposition = f"attachment; filename*=UTF-8''{quote(name)}"
    return Response(data, media_type=media, headers={"Content-Disposition": disposition, "Cache-Control": "no-store"})


@router.get("/{work_id}/export")
def export_docx(work_id: str, version: int | None = Query(None), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    data, name = works.export_docx(rt, user, work_id, version)
    return _file(data, name, DOCX)


@router.get("/{work_id}/export.pdf")
def export_pdf(work_id: str, version: int | None = Query(None), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    data, name = works.export_pdf(rt, user, work_id, version)
    return _file(data, name, "application/pdf")
