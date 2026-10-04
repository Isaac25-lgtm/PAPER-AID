"""Data Lab routes (owner decision 2026-10-03). Thin, like app.api.works: parse the input, call
app.datalab.service."""

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import Field

from app.api.public import student_json
from app.core.auth import current_user
from app.datalab import service as datalab
from app.datalab.models import AnalysisResult, AnalysisSpec
from app.datalab.report import ReportDocument
from app.datalab.service import DataView, VariableEdit
from app.jobs.models import Camel
from app.jobs.service import User
from app.runtime import Runtime, get_runtime

router = APIRouter(prefix="/api/datalab")
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class NewProject(Camel):
    title: str = Field(default="", max_length=200)
    purpose: str = Field(default="", max_length=1500)
    kind: Literal["QUANT", "QUAL"] = "QUANT"


class PastedTranscript(Camel):
    label: str = Field(default="", max_length=80)
    text: str = Field(min_length=1, max_length=1_000_000)
    consent: bool = False
    country: str = Field(default="UGA", max_length=8)
    replace: list[tuple[str, str]] = Field(default=[], max_length=200)


class Details(Camel):
    title: str | None = Field(default=None, max_length=200)
    purpose: str | None = Field(default=None, max_length=1500)
    alpha: float | None = None
    threshold: int | None = None


class Decision(Camel):
    accept: bool


class ReportRequest(Camel):
    analyses: list[str] = Field(default=[], max_length=60)
    missing_ok: list[int] = Field(default=[], max_length=12)  # Chapter Four: objectives the researcher confirmed have no analysis


class ObjectiveLink(Camel):
    objective: int | None = Field(default=None, ge=1, le=12)


def _file(data: bytes, name: str, media: str) -> Response:
    return Response(data, media_type=media, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}", "Cache-Control": "no-store"})


@router.get("", response_model=list[DataView])
def list_projects(user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> list[DataView]:
    return datalab.list_projects(rt, user)


@router.post("", response_model=DataView)
def create(body: NewProject, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> DataView:
    return datalab.create(rt, user, body.title, body.purpose, body.kind)


@router.post("/for-proposal/{proposal_id}", response_model=DataView)
def for_proposal(proposal_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> DataView:
    """Chapter Four: the Data Lab project for this research proposal's data (created on first use)."""
    return datalab.for_proposal(rt, user, proposal_id)


@router.get("/countries")
def countries(user: User = Depends(current_user)) -> list[dict]:
    """Where data may come from, and which countries are open (fail closed)."""
    return datalab.countries()


@router.get("/identifier-rules")
def identifier_rules(user: User = Depends(current_user)) -> dict:
    """The rule set for columns that may identify people or places, the same one the server uses."""
    from app.datalab.engine import profile

    return profile.RULES


@router.get("/places")
def places(user: User = Depends(current_user)) -> dict:
    """The map step's choices: Uganda's regions and sub-regions (with their districts)."""
    from app.datalab.engine import maps

    return maps.places()


@router.get("/{project_id}", response_model=DataView)
def get(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> DataView:
    return datalab.get(rt, user, project_id)


@router.delete("/{project_id}", status_code=204)
def delete(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    datalab.delete(rt, user, project_id)
    return Response(status_code=204)


@router.post("/{project_id}/details", response_model=DataView)
def details(project_id: str, body: Details, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> DataView:
    return datalab.update_details(rt, user, project_id, body.title, body.purpose, body.alpha, body.threshold)


@router.post("/{project_id}/dataset", response_model=DataView)
def upload(project_id: str, file: UploadFile = File(...), sheet: str | None = Form(None), country: str = Form("UGA", max_length=8),
           consent: bool = Form(False), removed: str = Form("[]", max_length=4000), user: User = Depends(current_user),
           rt: Runtime = Depends(get_runtime)) -> DataView:
    """`consent`: the researcher's confirmations; `removed`: the columns they removed in their browser, by kind (JSON list)."""
    import json

    data = file.file.read(rt.settings.max_upload_bytes + 1)
    try:
        dropped = [str(x) for x in json.loads(removed)] if removed else []
    except ValueError:
        dropped = []
    return datalab.upload(rt, user, project_id, file.filename or "data.csv", data, sheet or None, country, consent, dropped)


@router.post("/{project_id}/sheet", response_model=DataView)
def sheet(project_id: str, name: str = Body(..., embed=True, max_length=120), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> DataView:
    return datalab.choose_sheet(rt, user, project_id, name)


@router.get("/{project_id}/preview")
def preview(project_id: str, offset: int = Query(0, ge=0), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    from fastapi.responses import JSONResponse

    return JSONResponse(datalab.preview(rt, user, project_id, offset), headers={"Cache-Control": "no-store"})


@router.post("/{project_id}/variables/{name}", response_model=DataView)
def edit_variable(project_id: str, name: str, body: VariableEdit, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> DataView:
    return datalab.edit_variable(rt, user, project_id, name, body)


@router.post("/{project_id}/cleaning/{step_id}", response_model=DataView)
def decide(project_id: str, step_id: str, body: Decision, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> DataView:
    return datalab.decide(rt, user, project_id, step_id, body.accept)


@router.post("/{project_id}/undo", response_model=DataView)
def undo(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> DataView:
    return datalab.undo(rt, user, project_id)


@router.post("/{project_id}/analyses", response_model=DataView)
def analyse(project_id: str, body: AnalysisSpec, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> DataView:
    """Checked at once, run in the worker: the page follows the project's `op` to the result."""
    return datalab.analyse(rt, user, project_id, body)


@router.post("/{project_id}/analyses/{analysis_id}/objective", response_model=DataView)
def set_objective(project_id: str, analysis_id: str, body: ObjectiveLink, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> DataView:
    return datalab.set_objective(rt, user, project_id, analysis_id, body.objective)


@router.get("/{project_id}/analyses/{analysis_id}", response_model=AnalysisResult)
def analysis(project_id: str, analysis_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> AnalysisResult:
    return datalab.analysis(rt, user, project_id, analysis_id)


@router.get("/{project_id}/analyses/{analysis_id}/chart.png")
def chart(project_id: str, analysis_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return Response(datalab.chart(rt, user, project_id, analysis_id), media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@router.delete("/{project_id}/analyses/{analysis_id}", response_model=DataView)
def remove_analysis(project_id: str, analysis_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> DataView:
    return datalab.remove_analysis(rt, user, project_id, analysis_id)


@router.post("/{project_id}/report")
def start_report(project_id: str, body: ReportRequest, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return student_json(rt, datalab.start_report(rt, user, project_id, body.analyses, body.missing_ok))


@router.get("/{project_id}/report", response_model=ReportDocument)
def report(project_id: str, version: int | None = Query(None), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ReportDocument:
    return datalab.report_document(rt, user, project_id, version)


@router.get("/{project_id}/report/export")
def export_report(project_id: str, version: int | None = Query(None), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    data, name = datalab.export_report(rt, user, project_id, version)
    return _file(data, name, DOCX)


@router.get("/{project_id}/report/export.pdf")
def export_report_pdf(project_id: str, version: int | None = Query(None), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    data, name = datalab.export_report_pdf(rt, user, project_id, version)
    return _file(data, name, "application/pdf")


@router.get("/{project_id}/workbook")
def workbook(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    """The shareable report workbook: protected tables, no individual records."""
    data, name = datalab.export_workbook(rt, user, project_id)
    return _file(data, name, XLSX)


@router.post("/{project_id}/documents", response_model=DataView)
def add_document(project_id: str, file: UploadFile = File(...), label: str = Form("", max_length=80), consent: bool = Form(False),
                 country: str = Form("UGA", max_length=8), replace: str = Form("[]", max_length=20_000), user: User = Depends(current_user),
                 rt: Runtime = Depends(get_runtime)) -> DataView:
    """A transcript file; `replace`: the names to replace before it is stored, as JSON pairs [["Agnes", "Participant A"], ...]."""
    import json

    data = file.file.read(rt.settings.max_upload_bytes + 1)
    try:
        pairs = [(str(a), str(b)) for a, b in json.loads(replace)] if replace else []
    except (ValueError, TypeError):
        pairs = []
    return datalab.add_document(rt, user, project_id, label, file.filename or "transcript.txt", data, consent, country, pairs)


@router.post("/{project_id}/documents/text", response_model=DataView)
def add_text(project_id: str, body: PastedTranscript, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> DataView:
    """A transcript pasted as text."""
    return datalab.add_document(rt, user, project_id, body.label, "", body.text.encode("utf-8"), body.consent, body.country, list(body.replace))


@router.delete("/{project_id}/documents/{document_id}", response_model=DataView)
def remove_document(project_id: str, document_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> DataView:
    return datalab.remove_document(rt, user, project_id, document_id)


@router.post("/{project_id}/themes")
def start_themes(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    """The qualitative analysis: the paid step."""
    return student_json(rt, datalab.start_themes(rt, user, project_id))


@router.get("/{project_id}/report/codebook")
def codebook(project_id: str, version: int | None = Query(None), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    data, name = datalab.export_codebook(rt, user, project_id, version)
    return _file(data, name, XLSX)


@router.post("/{project_id}/cleaned", response_model=DataView)
def make_cleaned(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> DataView:
    """Make the researcher's cleaned-data file (in the worker)."""
    return datalab.make_cleaned(rt, user, project_id)


@router.get("/{project_id}/cleaned")
def cleaned(project_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    data, name, media = datalab.export_cleaned(rt, user, project_id)
    return _file(data, name, media)
