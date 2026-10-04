"""Data Lab (owner decision 2026-10-03): a researcher's dataset, read and profiled by code, cleaned
only with their confirmation, analysed by code (free: computing costs PaperAid nothing worth a
charge, so analyses are limited by fair use, not priced), and written up as an analysis report (the
one paid step, priced by its tier and reserved when it starts). The original upload is never
changed; every change makes a new version. Rows never reach the database or a model.

After Codex's audit (findings 1, 4, 8, 13): the data work (reading a file, applying or undoing a
change, an analysis, the cleaned-data file) runs in the worker, one piece at a time per project.
Every file is written under a name of its own before the record points to it, and old files are
deleted only after the record changed. A result is kept only if the data and settings it used are
still the project's, and every analysis carries a fingerprint of what it depended on, so a changed
setting marks it out of date instead of leaving it current."""

import hashlib
import io
import json
import logging
import re
import secrets
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path, PurePosixPath
from typing import Literal

import pandas as pd
from pydantic import Field

from app.ai.orchestration import work_engine
from app.core.errors import AppError, Conflict, NotFound
from app.core.logging import log
from app.datalab.engine import charts, clean, filters, ingest, profile, stats
from app.datalab.models import (
    AnalysisRef,
    AnalysisResult,
    AnalysisSpec,
    CleaningStep,
    DataOp,
    DataProject,
    DatasetVersion,
    Export,
    Kind,
    QualDocument,
    ReportVersion,
    SourceFile,
    Variable,
    VariableSetting,
)
from app.datalab.report import ReportDocument
from app.jobs import state
from app.jobs.models import Camel, Job, JobEvent, JobStatus, JobView, Quote, ServiceSelection, utcnow
from app.jobs.service import ACCOUNT_CLOSING, User, _erase_datalab, _rate_limit, availability, require_terms, resumable, resume_step, step_running, submit
from app.pricing.quote import bound_quote, fixed_price, work_prices_set
from app.runtime import Runtime

logger = logging.getLogger("paperaid.datalab")
MAX_PROJECTS = 40
MAX_ANALYSES = 60
MAX_REPORTED = 25
PARQUET = "application/vnd.apache.parquet"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
INPUT = "datalab_input.json"
RULES_VERSION = "disclosure-v2"  # part of every fingerprint: a change to the disclosure rules makes results out of date
OP_LEASE = timedelta(minutes=10)  # data work longer than this has stopped (measured limits keep it far shorter)
OP_WAIT = timedelta(minutes=20)  # data work still queued after this never started
MAX_RECORD_BYTES = 800_000  # a project record stays well inside Firestore's 1 MiB document limit
LONG_PARAMS = 2_000  # a cleaning step's parameters longer than this live in file storage
CLEANED_XLSX_CELLS = 1_000_000  # the cleaned data as Excel up to this size, otherwise as CSV
NOT_AVAILABLE = "Data Lab is not available on your account yet."
REPORT_RUNNING = "A report is being written. Change the data or its settings when it has finished."
BUSY = "PaperAid is still working on your last request. Wait for it to finish, then try again."
DATA_CHANGED = "The data or its settings changed while PaperAid was working on this, so nothing was kept. Please try again."
STOPPED = "PaperAid couldn't finish this. Nothing was changed; please try again."
SURVEY_ASK = "First tell PaperAid what {} is: a survey weight, cluster or stratum, or something else."
SURVEY_BLOCKED = ("This dataset comes from a survey with a sampling design (weights, clusters or strata). PaperAid can't yet analyse such data correctly, "
                  "so it won't run analyses that would ignore the design. You can still review the data and its quality.")
TOKEN = re.compile(r"⟦[^⟧]*⟧")
UPLOAD_WORDING = "datalab-upload-2026-10-04"  # the confirmations the researcher ticks at each upload (owner decision 2026-10-04)
COUNTRIES = json.loads((Path(__file__).parent / "countries.json").read_text(encoding="utf-8"))["countries"]


def countries() -> list[dict]:
    """Where data may come from: only a country marked available is open (fail closed)."""
    return [{"iso3": c["iso3"], "name": c["name"], "available": c["status"] == "AVAILABLE"} for c in COUNTRIES] + \
        [{"iso3": "OTHER", "name": "Another country", "available": False}]


def _country(iso3: str) -> dict | None:
    return next((c for c in COUNTRIES if c["iso3"] == iso3), None)


def _check_country(iso3: str) -> None:
    """Data from a country whose data protection rules PaperAid hasn't yet met is refused, with why."""
    country = _country(iso3)
    if iso3 != "OTHER" and country is None:
        raise AppError("Choose the country your data is from.", code="COUNTRY_REQUIRED")
    if country is not None and country["status"] == "AVAILABLE":
        return
    name = country["name"] if country else "this country"
    law = f"{name}'s" if country else "Its"
    raise AppError(f"Data Lab isn't available yet for data from {name}. {law} data protection law sets rules on how personal data from {name} is "
                   "handled, and we're making sure PaperAid meets them before we offer this. Data from Uganda works as normal.",
                   code="COUNTRY_NOT_AVAILABLE")


# --- records ---------------------------------------------------------------------------------------


def _valid_id(project_id: str) -> bool:
    return project_id.startswith("dl_") and project_id[3:].isalnum() and len(project_id) <= 40


def _owned(rt: Runtime, user: User, project_id: str) -> DataProject:
    project = rt.store.get_datalab(project_id) if _valid_id(project_id) else None
    if project is None or project.owner_uid != user.uid or project.deleting:
        raise NotFound("We couldn't find this Data Lab project.")
    return project


def _require(rt: Runtime, user: User) -> None:
    if availability(rt.settings, user).get("DATALAB") != "available":
        raise AppError(NOT_AVAILABLE, code="SERVICE_UNAVAILABLE")


def _renew(rt: Runtime, p: DataProject) -> DataProject:
    now = utcnow()
    p.updated_at, p.expires_at = now, now + timedelta(days=rt.settings.retention_days)
    return p


def _check_size(p: DataProject) -> None:
    if len(p.model_dump_json(by_alias=True).encode()) > MAX_RECORD_BYTES:
        raise AppError("This project has grown too large to save. Remove analyses you don't need, or start a new project for another dataset.",
                       code="PROJECT_TOO_LARGE")


def _change(rt: Runtime, user: User, project_id: str, mutate) -> DataProject:
    """Apply an owner action atomically, renewing the expiry."""
    _owned(rt, user, project_id)
    refusal: list[AppError] = []

    def apply(p: DataProject) -> DataProject | None:
        if p.deleting or p.owner_uid != user.uid:
            return None
        try:
            result = mutate(p)
            if result is not None:
                _check_size(result)
        except AppError as exc:
            refusal.append(exc)
            return None
        return _renew(rt, result) if result is not None else None

    updated = rt.store.update_datalab(project_id, apply)
    if refusal:
        raise refusal[0]
    if updated is None:
        raise Conflict("This project changed meanwhile. Reload it and try again.", code="DATALAB_CHANGED")
    return updated


def _limits(rt: Runtime) -> ingest.Limits:
    s = rt.settings
    return ingest.Limits(rows=s.datalab_max_rows, columns=s.datalab_max_columns, cells=s.datalab_max_cells, expanded_bytes=s.datalab_max_expanded_bytes)


def _entry(p: DataProject, version: int | None = None) -> DatasetVersion:
    wanted = version or p.current
    entry = next((v for v in p.versions if v.version == wanted), None)
    if entry is None:
        raise AppError("Upload a dataset first.", code="NO_DATASET")
    return entry


def _frame(rt: Runtime, p: DataProject, version: int | None = None) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(rt.files.get(_entry(p, version).path)))


def _base_variables(rt: Runtime, p: DataProject) -> list[Variable]:
    if not p.profile_path:
        return []
    return [Variable.model_validate(v) for v in json.loads(rt.files.get(p.profile_path))]


def _apply_settings(variables: list[Variable], settings: dict[str, VariableSetting]) -> list[Variable]:
    out = []
    for var in variables:
        s = settings.get(var.name)
        if s is None:
            out.append(var)
            continue
        out.append(var.model_copy(update={"label": s.label or var.label, "kind": s.kind or var.kind, "excluded": var.excluded if s.excluded is None else s.excluded}))
    return out


def variables_of(rt: Runtime, p: DataProject) -> list[Variable]:
    return _apply_settings(_base_variables(rt, p), p.settings)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _new_path(p: DataProject, folder: str, suffix: str) -> str:
    """A file name of its own: written before the record names it, never overwritten (finding 1)."""
    return f"{p.storage_prefix()}/{folder}/{secrets.token_hex(8)}{suffix}"


def _describe(frame: pd.DataFrame, flags: dict[str, list] | None, previous: dict[str, Variable]) -> list[Variable]:
    described = []
    for name in frame.columns:
        series = frame[name]
        stored = "number" if pd.api.types.is_float_dtype(series) else "date" if pd.api.types.is_datetime64_any_dtype(series) else "text"
        kept = [f for f in (flags or {}).get(name, previous[name].flags if name in previous else []) if f in ("LEADING_ZEROS", "MIXED", "LONG_NUMBER", "DECIMAL_COMMA")]
        described.append(profile.describe(name, series, stored, kept))
    return described


def _write_version(rt: Runtime, p: DataProject, frame: pd.DataFrame, note: str, number: int, written: list[str], flags: dict[str, list] | None = None,
                   previous: dict[str, Variable] | None = None) -> tuple[DatasetVersion, list[Variable]]:
    """A new version and its profile, written under new names; the caller attaches them to the record."""
    buffer = io.BytesIO()
    frame.to_parquet(buffer, index=False)
    data = buffer.getvalue()
    path = _new_path(p, "versions", ".parquet")
    rt.files.put(path, data, PARQUET)
    written.append(path)
    described = _describe(frame, flags, previous or {})
    profile_path = _new_path(p, "profile", ".json")
    rt.files.put(profile_path, json.dumps([v.model_dump(by_alias=True) for v in described]).encode(), "application/json")
    written.append(profile_path)
    entry = DatasetVersion(version=number, path=path, profile=profile_path, rows=len(frame), columns=len(frame.columns), sha256=hashlib.sha256(data).hexdigest(),
                           note=note[:300])
    return entry, described


def _stored_steps(rt: Runtime, p: DataProject, steps: list[CleaningStep], written: list[str]) -> list[CleaningStep]:
    """Proposals with long parameters (a merge of many spellings) moved to file storage (finding 8)."""
    out = []
    for step in steps:
        if len(json.dumps(step.params)) > LONG_PARAMS:
            path = _new_path(p, "steps", ".json")
            rt.files.put(path, json.dumps(step.params).encode(), "application/json")
            written.append(path)
            step = step.model_copy(update={"params": {}, "params_path": path})
        out.append(step)
    return out


def _with_params(rt: Runtime, step: CleaningStep) -> CleaningStep:
    return step.model_copy(update={"params": json.loads(rt.files.get(step.params_path))}) if step.params_path else step


def _step_files(steps: list[CleaningStep]) -> list[str]:
    return [s.params_path for s in steps if s.params_path]


# --- fingerprints (finding 4) ------------------------------------------------------------------------


def _spec_sha(spec: AnalysisSpec) -> str:
    return hashlib.sha256(json.dumps(spec.model_dump(by_alias=True, exclude={"objective"}), sort_keys=True).encode()).hexdigest()


def _fingerprint(p: DataProject, variables: dict[str, Variable], kind: str, names: list[str], spec_sha: str) -> str:
    """Everything an analysis depended on: the data version's content, the settings of the variables
    it used, the significance level, the disclosure threshold, the survey answers, the rules, the
    map layer, and the analysis itself (its Chapter Four objective excepted: that link can change)."""
    entry = next((v for v in p.versions if v.version == p.current), None)
    used = [(n, variables[n].kind, variables[n].excluded, variables[n].title()) if n in variables else (n, "", True, "") for n in names]
    parts = {"data": entry.sha256 if entry else "", "alpha": p.alpha, "threshold": p.threshold, "rules": RULES_VERSION,
             "survey": sorted((n, s.survey) for n, s in p.settings.items() if s.survey), "variables": used, "spec": spec_sha}
    if kind == "MAP":
        from app.datalab.engine import maps

        parts["layer"] = maps.layer_sha()
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _ref_fingerprint(p: DataProject, variables: dict[str, Variable], ref: AnalysisRef) -> str:
    return _fingerprint(p, variables, ref.kind, ref.variables, ref.spec_sha)


def _stale_ids(rt: Runtime, p: DataProject, variables: dict[str, Variable] | None = None) -> set[str]:
    """The analyses whose data or settings changed since they ran: shown as out of date, never reported."""
    variables = variables if variables is not None else {v.name: v for v in variables_of(rt, p)}
    return {ref.id for ref in p.analyses if ref.version != p.current or not ref.fingerprint or _ref_fingerprint(p, variables, ref) != ref.fingerprint}


# --- views ------------------------------------------------------------------------------------------


class AnalysisView(AnalysisRef):
    stale: bool = False  # the data or a setting it used changed: run it again before reporting it


class OpView(Camel):
    kind: str
    status: Literal["QUEUED", "RUNNING", "DONE", "FAILED"]
    error: str = ""
    code: str = ""
    result: str = ""


class Released(Camel):
    name: str
    at: str
    by: str


class DataView(Camel):
    id: str
    title: str
    purpose: str
    created_at: str
    updated_at: str
    expires_at: str
    source: SourceFile | None
    rows: int = 0
    columns: int = 0
    version: int = 0
    versions: list[DatasetVersion] = []
    variables: list[Variable] = []
    pending: list[CleaningStep] = []  # confirmations, one at a time in the page
    applied: list[CleaningStep] = []
    survey: Literal["NONE", "ASK", "DESIGN"] = "NONE"
    survey_columns: list[str] = []
    analyses: list[AnalysisView] = []
    reports: list[ReportVersion] = []
    report_current: int = 0
    active_job: str | None = None
    report_failure: str = ""
    alpha: float = 0.05
    threshold: int = 5
    availability: str = "soon"
    report_priced: bool = False  # the paid report is offered only once its tier prices are set (owner)
    proposal_id: str = ""  # Chapter Four of this research proposal
    objectives: list[str] = []
    op: OpView | None = None  # the data work in the worker, or the last one
    cleaned_ready: bool = False  # the cleaned-data file matches the current data
    released: list[Released] = []  # flagged columns included again, as recorded decisions
    kind: Literal["QUANT", "QUAL"] = "QUANT"
    documents: list[QualDocument] = []  # qualitative: the transcripts (their text stays in file storage)
    qual_priced: bool = False  # the qualitative analysis is offered only once its prices are set (owner)


def _expired(op: DataOp) -> bool:
    now = utcnow()
    if op.status == "RUNNING":
        return op.lease_until is not None and op.lease_until < now
    if op.status == "QUEUED":
        return op.created_at + OP_WAIT < now
    return False


def _active(op: DataOp | None) -> bool:
    return op is not None and op.status in ("QUEUED", "RUNNING") and not _expired(op)


def _op_view(op: DataOp | None) -> OpView | None:
    if op is None:
        return None
    if op.status in ("QUEUED", "RUNNING") and _expired(op):  # it stopped (an instance went away): say so, never "still working" forever
        return OpView(kind=op.kind, status="FAILED", error=STOPPED, code="OP_STOPPED")
    return OpView(kind=op.kind, status=op.status, error=op.error, code=op.code, result=op.result)


def _export_fingerprint(p: DataProject, variables: list[Variable]) -> str:
    entry = next((v for v in p.versions if v.version == p.current), None)
    return _sha(json.dumps([entry.sha256 if entry else "", sorted(v.name for v in variables if not v.excluded)]))


def view(rt: Runtime, p: DataProject, user: User | None = None) -> DataView:
    # A column left out of analysis (personal identifiers and coordinates by default) is shown without
    # its values, as in the preview: the page never lists names, phone numbers or locations back.
    all_vars = variables_of(rt, p) if p.profile_path else []
    variables = [v.model_copy(update={"levels": [], "summary": {}}) if v.excluded else v for v in all_vars]
    current = next((v for v in p.versions if v.version == p.current), None)
    flagged = [v.name for v in variables if "SURVEY_DESIGN" in v.flags]
    answers = {name: p.settings.get(name, VariableSetting()).survey for name in flagged}
    survey: Literal["NONE", "ASK", "DESIGN"] = "DESIGN" if "DESIGN" in answers.values() else "ASK" if any(a == "" for a in answers.values()) else "NONE"
    running = step_running(rt, p)
    failure = ""
    if not running and p.jobs:
        last = rt.store.get(p.jobs[-1])
        if last is not None and last.status in (JobStatus.FAILED, JobStatus.CANCELLED) and last.id not in {r.job_id for r in p.reports}:
            failure = last.failure.user_message if last.failure else "The report could not be finished. Nothing was charged."
    stale = _stale_ids(rt, p, {v.name: v for v in all_vars}) if p.analyses else set()
    analyses = [AnalysisView(**a.model_dump(), stale=a.id in stale) for a in reversed(p.analyses)]
    released = [Released(name=n, at=s.released_at.isoformat(), by=s.released_by) for n, s in p.settings.items() if s.released_at is not None]
    return DataView(
        id=p.id, title=p.title, purpose=p.purpose, created_at=p.created_at.isoformat(), updated_at=p.updated_at.isoformat(), expires_at=p.expires_at.isoformat(),
        source=p.source, rows=current.rows if current else 0, columns=current.columns if current else 0, version=p.current, versions=p.versions,
        variables=variables, pending=[s for s in p.steps if s.status == "PROPOSED"], applied=[s for s in p.steps if s.status == "APPLIED"],
        survey=survey, survey_columns=[n for n, a in answers.items() if a != "NOT_DESIGN"], analyses=analyses, reports=p.reports,
        report_current=p.report_current, active_job=p.active_job if running else None, report_failure=failure, alpha=p.alpha, threshold=p.threshold,
        proposal_id=p.proposal_id, objectives=p.objectives, op=_op_view(p.op),
        cleaned_ready=p.cleaned is not None and p.cleaned.fingerprint == _export_fingerprint(p, all_vars), released=released,
        kind=p.kind, documents=p.documents, qual_priced=work_prices_set(rt.settings, "DATALAB_QUAL"),
        availability=availability(rt.settings, user).get("DATALAB", "soon") if user else "soon", report_priced=work_prices_set(rt.settings, "DATALAB"),
    )


def list_projects(rt: Runtime, user: User) -> list[DataView]:
    return [view(rt, p, user) for p in rt.store.list_datalab(user.uid) if not p.deleting]


def get(rt: Runtime, user: User, project_id: str) -> DataView:
    return view(rt, _owned(rt, user, project_id), user)


# --- data work in the worker (finding 13) ----------------------------------------------------------------

Commit = Callable[[DataProject], list[str]]  # applies the result to the record; returns the files it made obsolete


def _queue(rt: Runtime, user: User, project_id: str, kind: str, params: dict, check: Callable[[DataProject], None] | None = None) -> DataView:
    """Hand a piece of data work to the worker. One at a time per project, never while a report is
    being written; the page follows it through the project's `op`."""
    op = DataOp(id=f"dop_{project_id}_{secrets.token_hex(4)}", kind=kind, params=params)  # type: ignore[arg-type]

    def apply(p: DataProject) -> DataProject:
        if step_running(rt, p):
            raise Conflict(REPORT_RUNNING, code="STEP_RUNNING")
        if _active(p.op):
            raise Conflict(BUSY, code="OP_RUNNING")
        if check is not None:
            check(p)
        p.op = op
        return p

    updated = _change(rt, user, project_id, apply)
    rt.queue.enqueue(op.id, op.id)
    return view(rt, updated, user)


def run_op(rt: Runtime, op_id: str) -> None:
    """The worker's side: claim the work, do it, and keep its result only if the project is still
    as the work found it. Files it wrote are removed when the result isn't kept."""
    project_id = op_id[len("dop_"):].rsplit("_", 1)[0]

    def claim(q: DataProject) -> DataProject | None:
        if q.deleting or q.op is None or q.op.id != op_id or q.op.status in ("DONE", "FAILED"):
            return None
        if q.op.status == "RUNNING" and not _expired(q.op):
            return None  # another delivery of the same task is doing it
        q.op.status, q.op.lease_until = "RUNNING", utcnow() + OP_LEASE
        return q

    p = rt.store.update_datalab(project_id, claim) if _valid_id(project_id) else None
    if p is None or p.op is None:
        return
    op = p.op
    written: list[str] = []
    try:
        commit, result = HANDLERS[op.kind](rt, p, op, written)
    except AppError as exc:
        _end_op(rt, project_id, op_id, written, exc.message, exc.code)
        return
    except Exception as exc:  # the worker boundary: an unexpected failure ends this piece of work, the project stays as it was
        log(logger, logging.ERROR, "data work failed", projectId=project_id, kind=op.kind, error=type(exc).__name__)
        _end_op(rt, project_id, op_id, written, STOPPED, "OP_FAILED")
        return
    obsolete: list[str] = []
    refusal: list[AppError] = []

    def keep(q: DataProject) -> DataProject | None:
        if q.deleting or q.op is None or q.op.id != op_id or q.op.status != "RUNNING":
            return None
        try:
            obsolete[:] = commit(q)
            q.op.status, q.op.result, q.op.lease_until = "DONE", result, None
            _check_size(q)
        except AppError as exc:
            refusal.append(exc)
            return None
        return _renew(rt, q)

    if rt.store.update_datalab(project_id, keep) is None:
        reason = refusal[0] if refusal else AppError(DATA_CHANGED, code="DATA_CHANGED")
        _end_op(rt, project_id, op_id, written, reason.message, reason.code)
        return
    for path in obsolete:  # only now that the record no longer names them
        rt.files.delete(path)
    log(logger, logging.INFO, "data work done", projectId=project_id, kind=op.kind)


def _end_op(rt: Runtime, project_id: str, op_id: str, written: list[str], message: str, code: str) -> None:
    for path in written:
        rt.files.delete(path)

    def fail(q: DataProject) -> DataProject | None:
        if q.op is None or q.op.id != op_id:
            return None
        q.op.status, q.op.error, q.op.code, q.op.lease_until = "FAILED", message, code, None
        return q

    rt.store.update_datalab(project_id, fail)


def _op_load(rt: Runtime, p: DataProject, op: DataOp, written: list[str]) -> tuple[Commit, str]:
    """A new file (or another sheet of the same workbook) starts the project's data afresh: earlier
    versions, cleaning and analyses go (reports already written are kept)."""
    params = op.params
    replacing = op.kind == "LOAD"
    if replacing:
        written.append(params["path"])  # the upload itself goes too if it can't be read
    table = ingest.read(rt.files.get(params["path"]), params["name"], params.get("sheet"), _limits(rt))
    frame, variables = profile.infer(table)
    flags = {v.name: list(v.flags) for v in variables}
    first, described = _write_version(rt, p, frame, "As uploaded", 1, written, flags)
    versions = [first]
    working = frame
    trims = [s for s in clean.proposals(frame, described, p.threshold) if s.automatic]
    for step in trims:  # the one automatic change: spaces around category labels (decision 2026-10-03)
        working, n = clean.apply(working, step)
        step.affected, step.status, step.decided_at = n, "APPLIED", utcnow()
    if trims:
        second, described = _write_version(rt, p, working, "Spaces trimmed around category labels", 2, written, flags)
        versions.append(second)
        for step in trims:
            step.version = second.version
    steps = trims + _stored_steps(rt, p, [s for s in clean.proposals(working, described, p.threshold) if not s.automatic], written)
    source = SourceFile(name=params["name"], path=params["path"], sha256=params["sha"], bytes=params["bytes"], sheet=table.sheet, sheets=table.sheets,
                        removed=params.get("removed", []) if replacing else (p.source.removed if p.source else []))

    def commit(q: DataProject) -> list[str]:
        if step_running(rt, q):
            raise AppError(REPORT_RUNNING, code="STEP_RUNNING")
        if not replacing and (q.source is None or q.source.sha256 != params["sha"]):
            raise AppError(DATA_CHANGED, code="DATA_CHANGED")
        obsolete = [v.path for v in q.versions] + [v.profile for v in q.versions if v.profile] + _step_files(q.steps)
        obsolete += [path for a in q.analyses for path in (a.path, a.path.removesuffix(".json") + ".png")]
        if q.cleaned is not None:
            obsolete.append(q.cleaned.path)
        if replacing and q.source is not None and q.source.path != source.path:
            obsolete.append(q.source.path)
        q.source, q.versions, q.current, q.profile_path = source, versions, versions[-1].version, versions[-1].profile
        q.steps, q.analyses, q.settings, q.cleaned = steps, [], {}, None
        if replacing:
            q.country, q.consent = params.get("country", q.country), params.get("consent", q.consent)
        return obsolete

    log(logger, logging.INFO, "dataset read", projectId=p.id, rows=len(frame), columns=len(frame.columns))
    return commit, ""


def _op_decide(rt: Runtime, p: DataProject, op: DataOp, written: list[str]) -> tuple[Commit, str]:
    """Apply a proposed change: a new version. The remaining proposals are worked out again on it,
    without asking again about anything declined."""
    step_id = op.params["step"]
    step = next((s for s in p.steps if s.id == step_id and s.status == "PROPOSED"), None)
    if step is None:
        raise AppError("That change was already decided. Reload to see the latest.", code="ALREADY_DECIDED")
    base = p.current
    frame, n = clean.apply(_frame(rt, p), _with_params(rt, step))
    number = max(v.version for v in p.versions) + 1
    entry, described = _write_version(rt, p, frame, step.description, number, written, previous={v.name: v for v in _base_variables(rt, p)})
    declined = {(s.kind, s.column) for s in p.steps if s.status == "DECLINED"}
    fresh = _stored_steps(rt, p, [s for s in clean.proposals(frame, described, p.threshold) if not s.automatic and (s.kind, s.column) not in declined], written)

    def commit(q: DataProject) -> list[str]:
        mine = next((s for s in q.steps if s.id == step_id and s.status == "PROPOSED"), None)
        if q.current != base or mine is None:
            raise AppError(DATA_CHANGED, code="DATA_CHANGED")
        mine.affected, mine.status, mine.version, mine.decided_at = n, "APPLIED", entry.version, utcnow()
        replaced = [s for s in q.steps if s.status == "PROPOSED"]
        q.steps = [s for s in q.steps if s.status != "PROPOSED"] + fresh
        q.versions.append(entry)
        q.current, q.profile_path = entry.version, entry.profile
        return _step_files(replaced)

    return commit, ""


def _op_undo(rt: Runtime, p: DataProject, op: DataOp, written: list[str]) -> tuple[Commit, str]:
    """Go back to the version before the last confirmed change (the change is recorded as undone)."""
    base = p.current
    last = next((s for s in reversed(p.steps) if s.status == "APPLIED" and not s.automatic and s.version == p.current), None)
    earlier = [v for v in p.versions if v.version < p.current]
    if last is None or not earlier:
        raise AppError("There's no confirmed change to undo.", code="NOTHING_TO_UNDO")
    previous = max(earlier, key=lambda v: v.version)
    frame = _frame(rt, p, previous.version)
    variables = [Variable.model_validate(v) for v in json.loads(rt.files.get(previous.profile))]
    declined = {(s.kind, s.column) for s in p.steps if s.status == "DECLINED" and not s.description.startswith("Undone:")}
    fresh = _stored_steps(rt, p, [s for s in clean.proposals(frame, variables, p.threshold) if not s.automatic and (s.kind, s.column) not in declined], written)

    def commit(q: DataProject) -> list[str]:
        mine = next((s for s in q.steps if s.id == last.id and s.status == "APPLIED"), None)
        if q.current != base or mine is None:
            raise AppError(DATA_CHANGED, code="DATA_CHANGED")
        mine.status, mine.description = "DECLINED", f"Undone: {mine.description}"
        replaced = [s for s in q.steps if s.status == "PROPOSED"]
        q.steps = [s for s in q.steps if s.status != "PROPOSED"] + fresh
        q.current, q.profile_path = previous.version, previous.profile
        return _step_files(replaced)

    return commit, ""


def _op_analyse(rt: Runtime, p: DataProject, op: DataOp, written: list[str]) -> tuple[Commit, str]:
    spec = AnalysisSpec.model_validate(op.params["spec"])
    variables = variables_of(rt, p)
    _check_survey(p, variables)
    by_name = {v.name: v for v in variables}
    _check_kinds(spec, by_name)
    _check_maps_country(p, spec)
    whole = _frame(rt, p)
    frame, notes, population = filters.apply(whole, spec.filters, by_name, p.threshold)  # before anything is counted
    cleaning = [s.description for s in p.steps if s.status == "APPLIED" and s.version is not None and s.version <= p.current]
    ctx = stats.Context(frame, by_name, p.current, p.alpha, p.threshold, cleaning, available=len(whole), population=population, notes=notes)
    if spec.kind == "MAP":
        from app.datalab.engine import maps

        result, png = maps.run(ctx, spec)
    else:
        result = stats.run(ctx, spec)
        png = charts.for_result(result, frame, p.threshold)
    base = f"{p.storage_prefix()}/analyses/{result.id}"
    if png is not None:
        rt.files.put(base + ".png", png, "image/png")
        written.append(base + ".png")
        result.chart = base + ".png"
    rt.files.put(base + ".json", result.model_dump_json(by_alias=True).encode(), "application/json")
    written.append(base + ".json")
    spec_sha = _spec_sha(spec)
    fingerprint = _fingerprint(p, by_name, spec.kind, spec.names(), spec_sha)
    version = p.current

    def commit(q: DataProject) -> list[str]:
        if q.current != version or _fingerprint(q, {v.name: v for v in variables_of(rt, q)}, spec.kind, spec.names(), spec_sha) != fingerprint:
            raise AppError(DATA_CHANGED, code="DATA_CHANGED")
        if len(q.analyses) >= MAX_ANALYSES:
            raise AppError(f"A project keeps up to {MAX_ANALYSES} analyses. Remove ones you don't need first.", code="TOO_MANY_ANALYSES")
        objective = spec.objective if spec.objective is not None and spec.objective <= len(q.objectives) else None
        q.analyses.append(AnalysisRef(id=result.id, kind=spec.kind, title=result.title, status=result.status, version=version, path=base + ".json",
                                      objective=objective, objective_sha=_sha(q.objectives[objective - 1]) if objective else "", variables=spec.names(),
                                      spec_sha=spec_sha, fingerprint=fingerprint))
        return []

    return commit, result.id


def _op_cleaned(rt: Runtime, p: DataProject, op: DataOp, written: list[str]) -> tuple[Commit, str]:
    """The researcher's own cleaned data, apart from the shareable report workbook (finding 2): its
    individual records, without the columns left out (names, phone numbers, coordinates) unless
    the researcher included them, as a recorded decision."""
    from app.datalab import workbook

    variables = variables_of(rt, p)
    frame = _frame(rt, p)
    kept = [v.name for v in variables if not v.excluded and v.name in frame.columns]
    data = frame[kept]
    if data.size <= CLEANED_XLSX_CELLS:
        content, suffix, media = workbook.cleaned(p.title, p.source.name if p.source else "", p.current, data, released=[n for n in kept if p.settings.get(n) and
                                                                                                                        p.settings[n].released_at]), ".xlsx", XLSX
    else:
        content, suffix, media = data.to_csv(index=False).encode("utf-8-sig"), ".csv", "text/csv"
    path = _new_path(p, "exports", suffix)
    rt.files.put(path, content, media)
    written.append(path)
    fingerprint = _export_fingerprint(p, variables)

    def commit(q: DataProject) -> list[str]:
        if _export_fingerprint(q, variables_of(rt, q)) != fingerprint:
            raise AppError(DATA_CHANGED, code="DATA_CHANGED")
        obsolete = [q.cleaned.path] if q.cleaned is not None else []
        q.cleaned = Export(path=path, fingerprint=fingerprint, rows=len(data))
        return obsolete

    return commit, path


HANDLERS: dict[str, Callable[[Runtime, DataProject, DataOp, list[str]], tuple[Commit, str]]] = {
    "LOAD": _op_load, "SHEET": _op_load, "DECIDE": _op_decide, "UNDO": _op_undo, "ANALYSE": _op_analyse, "CLEANED": _op_cleaned}


# --- the project and its dataset ------------------------------------------------------------------------


def create(rt: Runtime, user: User, title: str, purpose: str, kind: Literal["QUANT", "QUAL"] = "QUANT") -> DataView:
    _require(rt, user)
    if sum(1 for p in rt.store.list_datalab(user.uid) if not p.deleting) >= MAX_PROJECTS:
        raise AppError(f"You have {MAX_PROJECTS} Data Lab projects. Delete one you no longer need first.", code="TOO_MANY_PROJECTS")
    now = utcnow()
    project = DataProject(id=f"dl_{secrets.token_hex(6)}", owner_uid=user.uid, owner_email=user.email, title=" ".join(title.split())[:200] or "My analysis",
                          purpose=purpose.strip()[:1500], created_at=now, updated_at=now, expires_at=now + timedelta(days=rt.settings.retention_days), kind=kind)
    if not rt.store.create_datalab_if_open(project):
        raise Conflict(ACCOUNT_CLOSING, code="ACCOUNT_CLOSING")
    return view(rt, project, user)


def _quantitative(p: DataProject) -> None:
    if p.kind != "QUANT":
        raise AppError("This is a qualitative project: add transcripts to it instead.", code="WRONG_KIND")


def update_details(rt: Runtime, user: User, project_id: str, title: str | None, purpose: str | None, alpha: float | None, threshold: int | None) -> DataView:
    def apply(p: DataProject) -> DataProject:
        if (alpha is not None or threshold is not None) and step_running(rt, p):
            raise Conflict(REPORT_RUNNING, code="STEP_RUNNING")
        if title is not None:
            p.title = " ".join(title.split())[:200] or p.title
        if purpose is not None:
            p.purpose = purpose.strip()[:1500]
        if alpha is not None:
            if alpha not in (0.01, 0.05, 0.1):
                raise AppError("Choose a significance level of .01, .05 or .10.", code="INVALID_ALPHA")
            p.alpha = alpha
        if threshold is not None:
            if threshold < 5 or threshold > 50:  # can be raised, never lowered (decision 2026-10-03)
                raise AppError("Small counts are hidden below 5 at least; you can raise it up to 50.", code="INVALID_THRESHOLD")
            p.threshold = threshold
        return p

    return view(rt, _change(rt, user, project_id, apply), user)


def upload(rt: Runtime, user: User, project_id: str, filename: str, data: bytes, sheet: str | None = None, country: str = "UGA", consent: bool = False,
           removed: list[str] | None = None) -> DataView:
    """Store the upload as received (under a name of its own) and hand the reading to the worker. The
    researcher confirms, for every upload, that they may use the data and that names, phone numbers and
    ID numbers are removed or may be removed by PaperAid (recorded with the wording and terms they saw);
    the data's country must be one PaperAid is cleared for (owner decision 2026-10-04)."""
    _require(rt, user)
    require_terms(rt, user)
    if not consent:
        raise AppError("Confirm that you may use this data and that names, phone numbers and ID numbers are removed or may be removed.", code="CONSENT_REQUIRED")
    _check_country(country)
    _quantitative(_owned(rt, user, project_id))
    _rate_limit(rt, user, "upload", rt.settings.uploads_per_hour)
    p = _owned(rt, user, project_id)
    if step_running(rt, p):
        raise Conflict(REPORT_RUNNING, code="STEP_RUNNING")
    if _active(p.op):
        raise Conflict(BUSY, code="OP_RUNNING")
    name = PurePosixPath(filename).name[:120] or "data"
    if len(data) > rt.settings.max_upload_bytes:
        raise AppError(f"This file is larger than {rt.settings.max_upload_bytes // (1024 * 1024)} MB. Upload an extract with the rows and columns you need.", code="DATA_TOO_LARGE")
    if not name.lower().endswith((".csv", ".txt", ".tsv", ".xlsx", ".xlsm", ".xlsb", ".xltm", ".xls")):
        raise AppError("Upload a CSV file or an Excel workbook (.xlsx).", code="DATA_FORMAT")
    sha = hashlib.sha256(data).hexdigest()
    path = _new_path(p, "source", PurePosixPath(name).suffix.lower() or ".csv")
    rt.files.put(path, data, "application/octet-stream")
    try:
        return _queue(rt, user, project_id, "LOAD", {"path": path, "name": name, "sha": sha, "bytes": len(data), "sheet": sheet, "country": country,
                                                     "consent": {"wording": UPLOAD_WORDING, "terms": rt.settings.terms_version, "at": utcnow().isoformat()},
                                                     "removed": [r[:120] for r in (removed or [])[:20]]})
    except AppError:
        rt.files.delete(path)  # not handed over: the upload isn't kept
        raise


def choose_sheet(rt: Runtime, user: User, project_id: str, sheet: str) -> DataView:
    p = _owned(rt, user, project_id)
    if p.source is None or sheet not in p.source.sheets:
        raise AppError("Choose one of the workbook's sheets.", code="DATA_SHEET")
    return _queue(rt, user, project_id, "SHEET", {"path": p.source.path, "name": p.source.name, "sha": p.source.sha256, "bytes": p.source.bytes, "sheet": sheet})


# --- variables, survey design and cleaning -----------------------------------------------------------------


class VariableEdit(Camel):
    label: str | None = Field(default=None, max_length=120)
    kind: Kind | None = None
    excluded: bool | None = None
    survey: Literal["DESIGN", "NOT_DESIGN"] | None = None


def edit_variable(rt: Runtime, user: User, project_id: str, name: str, edit: VariableEdit) -> DataView:
    def apply(p: DataProject) -> DataProject:
        if step_running(rt, p):
            raise Conflict(REPORT_RUNNING, code="STEP_RUNNING")
        base = {v.name: v for v in _base_variables(rt, p)}
        var = base.get(name)
        if var is None:
            raise NotFound("That variable isn't in the dataset.")
        s = p.settings.get(name, VariableSetting()).model_copy()
        if edit.label is not None:
            s.label = " ".join(edit.label.split())[:120]
        if edit.kind is not None:
            allowed: dict[str, set[str]] = {"number": {"NUMERIC", "CATEGORICAL", "BINARY", "IDENTIFIER"}, "text": {"CATEGORICAL", "BINARY", "TEXT", "IDENTIFIER"},
                                             "date": {"DATE", "IDENTIFIER"}}
            if edit.kind not in allowed[var.stored]:
                raise AppError(f"\"{var.title()}\" is stored as {var.stored}; it can't be treated as {edit.kind.lower()}.", code="INVALID_KIND")
            if edit.kind == "BINARY" and var.distinct != 2:
                raise AppError(f"\"{var.title()}\" has {var.distinct} different values; a yes/no variable has two.", code="INVALID_KIND")
            s.kind = edit.kind
        if edit.excluded is not None:
            s.excluded = edit.excluded
            sensitive = "PERSONAL" in var.flags or "LOCATION" in var.flags
            if sensitive and not edit.excluded:  # including names, phone numbers or coordinates is a recorded decision (finding 3)
                s.released_at, s.released_by = utcnow(), user.email
            elif edit.excluded:
                s.released_at, s.released_by = None, ""
        if edit.survey is not None:
            if "SURVEY_DESIGN" not in var.flags:
                raise AppError("Only columns PaperAid asked about need this answer.", code="NOT_ASKED")
            s.survey = edit.survey
        p.settings[name] = s
        return p

    return view(rt, _change(rt, user, project_id, apply), user)


def decide(rt: Runtime, user: User, project_id: str, step_id: str, accept: bool) -> DataView:
    """Apply a proposed change (in the worker: it makes a new version) or decline it (at once)."""
    if accept:
        def proposed(p: DataProject) -> None:
            if not any(s.id == step_id and s.status == "PROPOSED" for s in p.steps):
                raise Conflict("That change was already decided. Reload to see the latest.", code="ALREADY_DECIDED")

        return _queue(rt, user, project_id, "DECIDE", {"step": step_id}, proposed)

    def apply(p: DataProject) -> DataProject:
        if step_running(rt, p):
            raise Conflict(REPORT_RUNNING, code="STEP_RUNNING")
        if _active(p.op):
            raise Conflict(BUSY, code="OP_RUNNING")
        step = next((s for s in p.steps if s.id == step_id and s.status == "PROPOSED"), None)
        if step is None:
            raise Conflict("That change was already decided. Reload to see the latest.", code="ALREADY_DECIDED")
        step.status, step.decided_at = "DECLINED", utcnow()
        return p

    return view(rt, _change(rt, user, project_id, apply), user)


def undo(rt: Runtime, user: User, project_id: str) -> DataView:
    def possible(p: DataProject) -> None:
        if not any(s.status == "APPLIED" and not s.automatic and s.version == p.current for s in p.steps):
            raise AppError("There's no confirmed change to undo.", code="NOTHING_TO_UNDO")

    return _queue(rt, user, project_id, "UNDO", {}, possible)


def preview(rt: Runtime, user: User, project_id: str, offset: int = 0, limit: int = 50) -> dict[str, object]:
    """A page of the current version for the researcher's own eyes. Columns left out (personal
    identifiers, coordinates) are masked here too."""
    p = _owned(rt, user, project_id)
    frame = _frame(rt, p)
    variables = {v.name: v for v in variables_of(rt, p)}
    page = frame.iloc[max(0, offset): max(0, offset) + min(limit, 200)]
    rows = []
    for _, row in page.iterrows():
        cells = []
        for name in frame.columns:
            value = row[name]
            if variables.get(name) is not None and variables[name].excluded:
                cells.append("•••")
            elif pd.isna(value):
                cells.append("")
            elif isinstance(value, float):
                cells.append(f"{value:g}")
            else:
                cells.append(str(value))
        rows.append(cells)
    return {"columns": list(frame.columns), "rows": rows, "total": len(frame), "offset": offset}


# --- analyses -------------------------------------------------------------------------------------------------


def _check_survey(p: DataProject, variables: list[Variable]) -> None:
    for var in variables:
        if "SURVEY_DESIGN" not in var.flags:
            continue
        answer = p.settings.get(var.name, VariableSetting()).survey
        if answer == "":
            raise AppError(SURVEY_ASK.format(f"\"{var.title()}\""), code="SURVEY_QUESTION")
        if answer == "DESIGN":
            raise AppError(SURVEY_BLOCKED, code="SURVEY_UNSUPPORTED")


def _check_kinds(spec: AnalysisSpec, variables: dict[str, Variable]) -> None:
    """Every check on the variables' count comes before anything reads them by position (finding 9)."""
    two = {"CROSSTAB", "COMPARE_TWO", "CORRELATE"}
    if spec.kind in two and (len(spec.variables) != 2 or spec.variables[0] == spec.variables[1]):
        raise AppError("Choose two different variables.", code="VARIABLE_KIND")
    if spec.kind == "DESCRIBE" and len(spec.variables) != 1:
        raise AppError("Choose one variable to describe.", code="VARIABLE_KIND")
    if spec.kind == "MAP" and (len(spec.variables) not in (1, 2) or len(set(spec.variables)) != len(spec.variables)):
        raise AppError("Choose the variable that holds the district names, and the number to average if you want one.", code="VARIABLE_KIND")
    for name in [spec.subcounty, spec.total, spec.denominator]:
        if name and (variables.get(name) is None or variables[name].excluded):
            raise AppError("Choose map columns from the variables included in the analysis.", code="UNKNOWN_VARIABLE")
    for name in spec.variables:
        var = variables.get(name)
        if var is None:
            raise AppError("Choose variables from the dataset.", code="UNKNOWN_VARIABLE")
        if var.excluded:
            raise AppError(f"\"{var.title()}\" is left out of analysis (it may identify people). Include it first if you need it.", code="VARIABLE_EXCLUDED")
        if var.kind == "TEXT" and spec.kind == "MAP" and name == spec.variables[0]:
            continue  # a column of district names has many different values: it is text, and that's what a map needs
        if var.kind in ("IDENTIFIER", "TEXT", "DATE"):
            what = {"IDENTIFIER": "an identifier", "TEXT": "free text", "DATE": "a date"}[var.kind]
            raise AppError(f"\"{var.title()}\" is {what}, which these analyses can't use.", code="VARIABLE_KIND")
    kinds = [variables[n].kind for n in spec.variables]
    categorical = {"CATEGORICAL", "BINARY"}
    if spec.kind == "CROSSTAB" and not all(k in categorical for k in kinds):
        raise AppError("A cross-tabulation needs two categorical variables.", code="VARIABLE_KIND")
    if spec.kind == "COMPARE_TWO" and (kinds[0] != "NUMERIC" or kinds[1] not in categorical):
        raise AppError("Choose a numeric variable to compare and a categorical variable for the groups.", code="VARIABLE_KIND")
    if spec.kind == "CORRELATE" and not all(k == "NUMERIC" for k in kinds):
        raise AppError("A correlation needs two numeric variables.", code="VARIABLE_KIND")
    if spec.kind == "MAP" and kinds[0] not in (*categorical, "TEXT"):
        raise AppError("Choose the variable that holds the district names.", code="VARIABLE_KIND")
    if spec.kind == "MAP":
        _check_map(spec, variables)
    elif spec.level != "DISTRICT" or spec.subcounty or spec.total or spec.denominator or spec.data_form != "RECORDS" or spec.region or spec.subregion:
        raise AppError("Areas and totals belong to maps.", code="INVALID_METHOD")
    allowed = {"DESCRIBE": {""}, "CROSSTAB": {""}, "COMPARE_TWO": {"", "MEANS", "DISTRIBUTIONS"}, "CORRELATE": {"", "PEARSON", "SPEARMAN"},
               "MAP": {"", "COUNT", "MEAN", "RATE"}}[spec.kind]
    if spec.method not in allowed:
        raise AppError("That method doesn't fit this analysis.", code="INVALID_METHOD")
    filters.check(spec.filters, variables)


def _check_map(spec: AnalysisSpec, variables: dict[str, Variable]) -> None:
    """A map's columns and options (owner decision 2026-10-04): the level, records or totals, the area."""
    from app.datalab.engine import maps

    numeric = {n for n, v in variables.items() if v.kind == "NUMERIC"}
    if spec.level == "SUBCOUNTY" and (not spec.subcounty or variables[spec.subcounty].kind not in ("CATEGORICAL", "BINARY", "TEXT")):
        raise AppError("A subcounty map needs the column with subcounty names, with the district column: subcounty names repeat across districts.",
                       code="VARIABLE_KIND")
    if spec.region and spec.subregion:
        raise AppError("Choose a region or a sub-region, not both.", code="INVALID_METHOD")
    if spec.subregion and spec.subregion not in maps.subregions():
        raise AppError("Choose one of Uganda's sub-regions.", code="INVALID_METHOD")
    if spec.data_form == "TOTALS":
        if len(spec.variables) != 1 or spec.method not in ("", "COUNT", "RATE"):
            raise AppError("Totals are mapped as the count itself, or as a rate per 1,000.", code="INVALID_METHOD")
        if spec.total not in numeric:
            raise AppError("Choose the column holding each area's total (a number).", code="VARIABLE_KIND")
        if spec.method == "RATE" and spec.denominator not in numeric:
            raise AppError("A rate needs the column holding each area's population (a number).", code="VARIABLE_KIND")
        return
    if spec.method == "RATE" or spec.total or spec.denominator:
        raise AppError("Rates and totals need data that already holds a total for each area.", code="INVALID_METHOD")
    if len(spec.variables) == 2 and variables[spec.variables[1]].kind != "NUMERIC":
        raise AppError("A map shows the average of a number; choose a numeric variable, or map the number of records.", code="VARIABLE_KIND")
    if spec.method == "MEAN" and len(spec.variables) != 2:
        raise AppError("Choose the number to average.", code="VARIABLE_KIND")


def _check_maps_country(p: DataProject, spec: AnalysisSpec) -> None:
    """Maps only for data from a country whose maps are open (fail closed; owner decision 2026-10-04)."""
    if spec.kind == "MAP" and (_country(p.country or "UGA") or {}).get("status") != "AVAILABLE":
        _check_country(p.country)


def analyse(rt: Runtime, user: User, project_id: str, spec: AnalysisSpec) -> DataView:
    """Check the request at once, then run the analysis in the worker on the current version."""
    _require(rt, user)
    p = _owned(rt, user, project_id)
    if len(p.analyses) >= MAX_ANALYSES:
        raise AppError(f"A project keeps up to {MAX_ANALYSES} analyses. Remove ones you don't need first.", code="TOO_MANY_ANALYSES")
    if not p.versions:
        raise AppError("Upload a dataset first.", code="NO_DATASET")
    variables = variables_of(rt, p)
    _check_survey(p, variables)
    _check_kinds(spec, {v.name: v for v in variables})
    _check_maps_country(p, spec)
    if spec.objective is not None and spec.objective > len(p.objectives):
        raise AppError("Choose one of your proposal's objectives.", code="INVALID_OBJECTIVE")
    _quantitative(p)
    _rate_limit(rt, user, "analysis", rt.settings.datalab_analyses_per_hour)
    return _queue(rt, user, project_id, "ANALYSE", {"spec": spec.model_dump(by_alias=True)})


def analysis(rt: Runtime, user: User, project_id: str, analysis_id: str) -> AnalysisResult:
    p = _owned(rt, user, project_id)
    ref = next((a for a in p.analyses if a.id == analysis_id), None)
    if ref is None:
        raise NotFound("That analysis isn't in this project.")
    return AnalysisResult.model_validate_json(rt.files.get(ref.path))


def chart(rt: Runtime, user: User, project_id: str, analysis_id: str) -> bytes:
    result = analysis(rt, user, project_id, analysis_id)
    if not result.chart or not rt.files.exists(result.chart):
        raise NotFound("This analysis has no chart.")
    return rt.files.get(result.chart)


def set_objective(rt: Runtime, user: User, project_id: str, analysis_id: str, objective: int | None) -> DataView:
    """Chapter Four: link an analysis to the specific objective it answers (or to none)."""

    def apply(p: DataProject) -> DataProject:
        if step_running(rt, p):
            raise Conflict(REPORT_RUNNING, code="STEP_RUNNING")
        ref = next((a for a in p.analyses if a.id == analysis_id), None)
        if ref is None:
            raise NotFound("That analysis isn't in this project.")
        if objective is not None and not 1 <= objective <= len(p.objectives):
            raise AppError("Choose one of your proposal's objectives.", code="INVALID_OBJECTIVE")
        ref.objective = objective
        ref.objective_sha = _sha(p.objectives[objective - 1]) if objective else ""
        return p

    return view(rt, _change(rt, user, project_id, apply), user)


def remove_analysis(rt: Runtime, user: User, project_id: str, analysis_id: str) -> DataView:
    removed: list[AnalysisRef] = []

    def apply(p: DataProject) -> DataProject:
        if step_running(rt, p):  # the report being written uses its charts
            raise Conflict(REPORT_RUNNING, code="STEP_RUNNING")
        removed[:] = [a for a in p.analyses if a.id == analysis_id]
        p.analyses = [a for a in p.analyses if a.id != analysis_id]
        return p

    updated = _change(rt, user, project_id, apply)
    for ref in removed:
        rt.files.delete(ref.path)
        rt.files.delete(ref.path.removesuffix(".json") + ".png")
    return view(rt, updated, user)


def delete(rt: Runtime, user: User, project_id: str) -> None:
    p = rt.store.get_datalab(project_id) if _valid_id(project_id) else None
    if p is None or p.owner_uid != user.uid:
        return
    if not _erase_datalab(rt, p) and rt.store.get_datalab(p.id) is not None:
        raise Conflict("A report is being written for this project. Delete it when it has finished.", code="STEP_RUNNING")
    log(logger, logging.INFO, "datalab project deleted", projectId=project_id)


# --- the analysis report (the paid step) --------------------------------------------------------------------


class ChapterThreePart(Camel):
    heading: str
    text: str


class ReportInput(Camel):
    """What a report step was priced on, frozen with its job: the analyses (results, not rows), and
    for Chapter Four the approved plan and Chapter Three it was written from (finding 6)."""

    project_id: str
    title: str
    purpose: str
    version: int
    rows: int
    columns: int
    source_name: str
    sheet: str | None = None
    alpha: float
    threshold: int
    cleaning: list[CleaningStep]
    variables: list[Variable]
    analyses: list[AnalysisResult]
    charts: dict[str, str] = {}  # analysis id → chart path in the project's storage
    fingerprints: dict[str, str] = {}  # analysis id → its fingerprint when the report was started
    released: list[str] = []  # flagged columns the researcher included, named in the methods
    mode: Literal["REPORT", "CHAPTER_FOUR"] = "REPORT"
    objectives: list[str] = []  # Chapter Four: the proposal's specific objectives
    objective_of: dict[str, int] = {}  # analysis id → the objective (1-based) it answers
    missing_objectives: list[int] = []  # objectives the researcher confirmed have no analysis: the chapter says so
    proposal_id: str = ""
    plan_version: int = 0
    chapter_three_version: int = 0
    chapter_three: list[ChapterThreePart] = []  # its methods, for the writer and the reviewer


def band(rows: int, analyses: int) -> str:
    if rows <= 10_000 and analyses <= 5:
        return "DL_SMALL"
    if rows <= 100_000 and analyses <= 12:
        return "DL_STANDARD"
    return "DL_LARGE"


CHAPTER_THREE_WORDS = 2500


def _chapter_three(rt: Runtime, proposal) -> tuple[int, list[ChapterThreePart]]:
    from app.proposals.service import _chapter_doc

    state3 = proposal.chapter(3)
    doc = _chapter_doc(rt, state3) if state3.current else None
    if doc is None:
        raise AppError("Chapter Four follows Chapter Three. Write Chapter Three of your proposal first.", code="CHAPTER_THREE_MISSING")
    parts, words = [], 0
    for section in doc.sections:
        text = " ".join(TOKEN.sub("", p).strip() for p in section.paragraphs)
        take = " ".join(text.split()[: max(0, CHAPTER_THREE_WORDS - words)])
        words += len(take.split())
        parts.append(ChapterThreePart(heading=f"{section.number} {section.heading}".strip(), text=take))
    return state3.current, parts


def _proposal_for(rt: Runtime, user: User, proposal_id: str):
    proposal = rt.store.get_project(proposal_id) if proposal_id.startswith("prj_") else None
    if proposal is None or proposal.owner_uid != user.uid or proposal.deleting:
        raise NotFound("We couldn't find this proposal.")
    if proposal.plan is None or proposal.plan_status != "APPROVED" or not proposal.plan.specific_objectives:
        raise AppError("Chapter Four is written from your proposal's approved objectives. Finish the plan first.", code="PLAN_NOT_APPROVED")
    return proposal


def _objectives(proposal) -> list[str]:
    return [o[:600] for o in proposal.plan.specific_objectives[:12]]


def start_report(rt: Runtime, user: User, project_id: str, analysis_ids: list[str], missing_ok: list[int] | None = None) -> JobView:
    """Write the analysis report (or Chapter Four) from analyses that are current. Priced by its tier,
    held when it starts, charged only when the report is delivered."""
    _require(rt, user)
    require_terms(rt, user)
    if not work_prices_set(rt.settings, "DATALAB"):  # no invented prices: the report waits for the owner's
        raise AppError("The analysis report isn't available yet. Your analyses and the Excel workbook are.", code="REPORT_NOT_PRICED")
    p = _owned(rt, user, project_id)
    if step_running(rt, p):
        raise Conflict("PaperAid is already writing this report.", code="STEP_RUNNING")
    if _active(p.op):
        raise Conflict(BUSY, code="OP_RUNNING")
    variables = variables_of(rt, p)
    _check_survey(p, variables)
    stale = _stale_ids(rt, p, {v.name: v for v in variables})
    chosen = [a for a in p.analyses if (a.id in analysis_ids if analysis_ids else a.id not in stale) and a.status != "NOT_ESTIMABLE"]
    if not chosen:
        raise AppError("Run at least one analysis on the current data first.", code="NO_ANALYSES")
    if len(chosen) > MAX_REPORTED:
        raise AppError(f"A report covers up to {MAX_REPORTED} analyses. Choose the ones that answer your question.", code="TOO_MANY_ANALYSES")
    if any(a.id in stale for a in chosen):
        raise AppError("Some chosen analyses are out of date: the data or its settings changed after they ran. Run them again first.", code="STALE_ANALYSES")
    chapter = bool(p.proposal_id)
    proposal_fields: dict = {}
    if chapter:
        proposal = _proposal_for(rt, user, p.proposal_id)
        objectives = _objectives(proposal)
        if objectives != p.objectives:  # the proposal's objectives changed: follow them, then check every link again
            p = _change(rt, user, project_id, lambda q: _refresh_objectives(q, objectives))
            chosen = [a for a in p.analyses if a.id in {c.id for c in chosen}]
        relinked = [a.title for a in chosen if a.objective is not None and a.objective_sha != _sha(objectives[a.objective - 1])]
        if relinked:
            raise AppError("Your proposal's objectives changed after these analyses were linked to them. Check the objective of: " + "; ".join(relinked[:6]) + ".",
                           code="OBJECTIVES_CHANGED")
        covered = {a.objective for a in chosen if a.objective is not None}
        missing = [k for k in range(1, len(objectives) + 1) if k not in covered]
        if missing and not set(missing) <= set(missing_ok or []):
            raise AppError("No analysis answers objective " + ", ".join(str(k) for k in missing) + ". Run an analysis for each, or confirm that Chapter Four "
                           "should say so.", code="MISSING_OBJECTIVES")
        version3, parts3 = _chapter_three(rt, proposal)
        proposal_fields = {"proposal_id": proposal.id, "plan_version": proposal.plan_version, "chapter_three_version": version3, "chapter_three": parts3,
                           "missing_objectives": missing}
    last = rt.store.get(p.jobs[-1]) if p.jobs else None
    if last is not None and resumable(rt, last):
        before = ReportInput.model_validate_json(rt.files.get(f"{last.storage_prefix()}/internal/{INPUT}"))
        if before.version == p.current and {r.id for r in before.analyses} == {a.id for a in chosen} and resume_step(rt, user, last.id):
            # The same report stopped for a temporary reason, on the same data: resumed where it stopped.
            job = rt.store.get(last.id)
            assert job is not None
            return job.view()
    results = [AnalysisResult.model_validate_json(rt.files.get(a.path)) for a in chosen]
    _released_together(rt, p, results, variables)
    current = _entry(p)
    inp = ReportInput(project_id=p.id, title=p.title, purpose=p.purpose, version=p.current, rows=current.rows, columns=current.columns,
                      source_name=p.source.name if p.source else "", sheet=p.source.sheet if p.source else None, alpha=p.alpha, threshold=p.threshold,
                      cleaning=[s for s in p.steps if s.status == "APPLIED" and s.version is not None and s.version <= p.current],
                      variables=variables, analyses=results, charts={r.id: r.chart for r in results if r.chart},
                      fingerprints={a.id: a.fingerprint for a in chosen}, released=[n for n, s in p.settings.items() if s.released_at is not None],
                      mode="CHAPTER_FOUR" if chapter else "REPORT", objectives=p.objectives,
                      objective_of={a.id: a.objective for a in chosen if a.objective is not None}, **proposal_fields)
    tier = band(current.rows, len(results))
    from app.works.service import check_credits  # the same balance and minimum checks as every service, before anything is priced

    check_credits(rt, user, "DATALAB", fixed_price(rt.settings, tier, None) if rt.settings.pricing_mode == "fixed" else 0)
    _rate_limit(rt, user, "quote", rt.settings.quotes_per_hour)
    data = inp.model_dump_json(by_alias=True).encode()
    sha = hashlib.sha256(data).hexdigest()
    now = utcnow()
    selection = ServiceSelection(datalab="REPORT", datalab_band=tier)
    job = Job(id=f"job_{secrets.token_hex(6)}", status=JobStatus.DRAFT, owner_uid=user.uid, owner_email=user.email, datalab_id=p.id, input_sha256=sha,
              selection=selection, created_at=now, expires_at=now + timedelta(days=rt.settings.retention_days),
              events=[JobEvent(at=now, label=f"Analysis report priced for Data Lab project {p.id}")])
    rt.files.put(f"{job.storage_prefix()}/internal/{INPUT}", data, "application/json")
    job.quote = bound_quote(rt.settings, selection, sha, len(results), work_engine(rt.settings, "DATALAB"))
    state.transition(job, JobStatus.QUOTED, "Quote issued")
    if not rt.store.create_if_open(job):
        rt.files.delete_prefix(job.storage_prefix())
        raise Conflict(ACCOUNT_CLOSING, code="ACCOUNT_CLOSING")
    seen_active = p.active_job

    def gate(j: Job, q: DataProject | None) -> DataProject | None:
        if q is None or q.deleting or q.owner_uid != j.owner_uid or q.current != inp.version or _active(q.op):
            return None
        if q.active_job not in (seen_active, j.id):
            return None
        q.active_job = j.id
        q.jobs = q.jobs if j.id in q.jobs else (q.jobs + [j.id])[-100:]
        return _renew(rt, q)

    quote = Quote.model_validate(job.quote.model_dump())
    return submit(rt, user, job.id, quote.id, data_gate=gate)


def still_current(rt: Runtime, inp: ReportInput) -> str:
    """Before a report is published (finding 4): the data, every analysis's fingerprint and, for Chapter
    Four, the approved plan and Chapter Three must still be what it was written from. "" when they
    are, otherwise why not."""
    p = rt.store.get_datalab(inp.project_id)
    if p is None or p.deleting:
        return "deleted"
    if p.current != inp.version:
        return "data changed"
    variables = {v.name: v for v in variables_of(rt, p)}
    refs = {a.id: a for a in p.analyses}
    for analysis_id, fingerprint in inp.fingerprints.items():
        ref = refs.get(analysis_id)
        if ref is None or ref.fingerprint != fingerprint or _ref_fingerprint(p, variables, ref) != fingerprint:
            return "an analysis changed"
    if inp.mode == "CHAPTER_FOUR" and inp.proposal_id:
        proposal = rt.store.get_project(inp.proposal_id)
        if proposal is None or proposal.deleting or proposal.plan_status != "APPROVED" or proposal.plan_version != inp.plan_version:
            return "the proposal's plan changed"
        if proposal.chapter(3).current != inp.chapter_three_version:
            return "Chapter Three changed"
    return ""


def _released_together(rt: Runtime, p: DataProject, results: list[AnalysisResult], variables: list[Variable]) -> None:
    """Results that go out together (a report, the report workbook) are checked as a set: two whose
    records differ by only a few would reveal those few by subtraction (Codex, on the plan)."""
    if not any(r.spec.filters for r in results):
        return
    filters.overlaps(_frame(rt, p), {r.id: r.spec.filters for r in results}, {r.id: r.title for r in results}, {v.name: v for v in variables}, p.threshold)


def _refresh_objectives(p: DataProject, objectives: list[str]) -> DataProject:
    p.objectives = objectives
    return p


# --- downloads ---------------------------------------------------------------------------------------------------


def _report_entry(p: DataProject, version: int | None) -> ReportVersion:
    wanted = version or p.report_current
    entry = next((r for r in p.reports if r.version == wanted), None)
    if entry is None:
        raise NotFound("There's no report yet. Write one from your analyses first.")
    return entry


def _safe_name(title: str, fallback: str) -> str:
    return "".join(c for c in title[:80] if c.isalnum() or c in " -_").strip() or fallback


def report_document(rt: Runtime, user: User, project_id: str, version: int | None = None) -> ReportDocument:
    p = _owned(rt, user, project_id)
    return ReportDocument.model_validate_json(rt.files.get(_report_entry(p, version).path))


def export_report(rt: Runtime, user: User, project_id: str, version: int | None = None) -> tuple[bytes, str]:
    p = _owned(rt, user, project_id)
    entry = _report_entry(p, version)
    _change(rt, user, project_id, lambda q: q)  # downloading renews the project
    return rt.files.get(entry.docx), f"{_safe_name(p.title, 'Analysis report')}.docx"


def export_report_pdf(rt: Runtime, user: User, project_id: str, version: int | None = None) -> tuple[bytes, str]:
    """The same report as a PDF, laid out from the Word file by LibreOffice (offline, no AI)."""
    from app.works.render import to_pdf

    data, name = export_report(rt, user, project_id, version)
    _rate_limit(rt, user, "pdf", rt.settings.uploads_per_hour)
    pdf = to_pdf(data)
    if pdf is None:
        raise AppError("The PDF could not be made this time. Download the Word file instead.", code="PDF_FAILED")
    return pdf, name.removesuffix(".docx") + ".pdf"


def export_workbook(rt: Runtime, user: User, project_id: str) -> tuple[bytes, str]:
    """The report workbook (code only, shareable): the current analyses with their protected tables,
    the data dictionary and the cleaning log. No individual records: those are in the separate
    cleaned-data file (finding 2)."""
    from app.datalab import workbook

    p = _owned(rt, user, project_id)
    if not p.versions:
        raise AppError("Upload a dataset first.", code="NO_DATASET")
    _rate_limit(rt, user, "upload", rt.settings.uploads_per_hour)
    variables = variables_of(rt, p)
    stale = _stale_ids(rt, p, {v.name: v for v in variables})
    results = [AnalysisResult.model_validate_json(rt.files.get(a.path)) for a in p.analyses if a.id not in stale]
    _released_together(rt, p, results, variables)
    current = _entry(p)
    files = rt.files
    data = workbook.build(p.title, p.source.name if p.source else "", p.current, current.rows, p.threshold, variables,
                          [s for s in p.steps if s.status == "APPLIED" and s.version is not None and s.version <= p.current], results,
                          lambda path: files.get(path) if path and files.exists(path) else None)
    _change(rt, user, project_id, lambda q: q)
    return data, f"{_safe_name(p.title, 'Analysis')}.xlsx"


def make_cleaned(rt: Runtime, user: User, project_id: str) -> DataView:
    """Make the cleaned-data file (in the worker: it holds every record)."""
    _rate_limit(rt, user, "upload", rt.settings.uploads_per_hour)
    p = _owned(rt, user, project_id)
    if not p.versions:
        raise AppError("Upload a dataset first.", code="NO_DATASET")
    return _queue(rt, user, project_id, "CLEANED", {})


def export_cleaned(rt: Runtime, user: User, project_id: str) -> tuple[bytes, str, str]:
    p = _owned(rt, user, project_id)
    if p.cleaned is None or p.cleaned.fingerprint != _export_fingerprint(p, variables_of(rt, p)):
        raise Conflict("The cleaned data has changed since this file was made. Make it again.", code="CLEANED_OUT_OF_DATE")
    suffix = PurePosixPath(p.cleaned.path).suffix
    _change(rt, user, project_id, lambda q: q)
    return rt.files.get(p.cleaned.path), f"{_safe_name(p.title, 'Data')} - cleaned data{suffix}", XLSX if suffix == ".xlsx" else "text/csv"


# --- qualitative data (owner decision 2026-10-04) --------------------------------------------------------------------

TEXT_SUFFIXES = (".txt", ".docx", ".pdf")


def _document_text(filename: str, data: bytes, rt: Runtime) -> str:
    """A transcript's text: a text file as written; a Word file or a text PDF through the same checks as any paper."""
    from app.documents.intake import inspect_upload

    suffix = PurePosixPath(filename.lower()).suffix
    if suffix not in TEXT_SUFFIXES:
        raise AppError("Upload a transcript as a text file (.txt), a Word document (.docx) or a text PDF.", code="DATA_FORMAT")
    if suffix == ".txt":
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise AppError("PaperAid couldn't read the characters in this file. Save it as UTF-8 text and upload it again.", code="DATA_ENCODING")
    model = inspect_upload(data, filename, rt.settings.max_upload_bytes, rt.settings.datalab_qual_max_words, rt.settings.max_pdf_pages, min_words=20)
    return "\n".join(b.text for b in model.blocks if b.text.strip())


def add_document(rt: Runtime, user: User, project_id: str, label: str, filename: str, data: bytes, consent: bool, country: str,
                 replacements: list[tuple[str, str]]) -> DataView:
    """A transcript, kept only after the names the researcher listed (and any email address, phone or ID number)
    were replaced: the original never reaches PaperAid's storage (owner decision 2026-10-04)."""
    from app.datalab import qual

    _require(rt, user)
    require_terms(rt, user)
    if not consent:
        raise AppError("Confirm that your participants agreed and that names you listed may be replaced.", code="CONSENT_REQUIRED")
    _check_country(country)
    _rate_limit(rt, user, "upload", rt.settings.uploads_per_hour)
    p = _owned(rt, user, project_id)
    if p.kind != "QUAL":
        raise AppError("This project analyses a dataset of numbers and categories: start a qualitative project for transcripts.", code="WRONG_KIND")
    if step_running(rt, p):
        raise Conflict(REPORT_RUNNING, code="STEP_RUNNING")
    if len(data) > rt.settings.max_upload_bytes:
        raise AppError(f"This file is larger than {rt.settings.max_upload_bytes // (1024 * 1024)} MB.", code="DATA_TOO_LARGE")
    text, replaced = qual.pseudonymise(_document_text(filename, data, rt) if filename else data.decode("utf-8"), replacements[:200])
    words = len(text.split())
    if words < 20:
        raise AppError("There isn't enough text here to analyse.", code="NO_TEXT")
    if len(p.documents) >= rt.settings.datalab_qual_max_documents:
        raise AppError(f"A project holds up to {rt.settings.datalab_qual_max_documents} transcripts.", code="TOO_MANY_DOCUMENTS")
    if sum(d.words for d in p.documents) + words > rt.settings.datalab_qual_max_words:
        raise AppError(f"All transcripts together can hold up to {rt.settings.datalab_qual_max_words:,} words.", code="DOCUMENT_TOO_LONG")
    body = text.encode("utf-8")
    path = _new_path(p, "documents", ".txt")
    rt.files.put(path, body, "text/plain; charset=utf-8")
    document = QualDocument(id=f"doc_{secrets.token_hex(4)}", label=" ".join(label.split())[:80] or f"Transcript {len(p.documents) + 1}",
                            name=PurePosixPath(filename).name[:120] if filename else "", path=path, sha256=hashlib.sha256(body).hexdigest(), words=words,
                            replaced=replaced)

    def apply(q: DataProject) -> DataProject:
        if step_running(rt, q):
            raise Conflict(REPORT_RUNNING, code="STEP_RUNNING")
        if any(d.label.lower() == document.label.lower() for d in q.documents):
            raise AppError(f"A transcript is already called \"{document.label}\". Give this one another name.", code="DUPLICATE_LABEL")
        q.documents.append(document)
        q.country, q.consent = country, {"wording": UPLOAD_WORDING, "terms": rt.settings.terms_version, "at": utcnow().isoformat()}
        return q

    try:
        updated = _change(rt, user, project_id, apply)
    except AppError:
        rt.files.delete(path)
        raise
    return view(rt, updated, user)


def remove_document(rt: Runtime, user: User, project_id: str, document_id: str) -> DataView:
    removed: list[QualDocument] = []

    def apply(q: DataProject) -> DataProject:
        if step_running(rt, q):
            raise Conflict(REPORT_RUNNING, code="STEP_RUNNING")
        removed[:] = [d for d in q.documents if d.id == document_id]
        q.documents = [d for d in q.documents if d.id != document_id]
        return q

    updated = _change(rt, user, project_id, apply)
    for d in removed:
        rt.files.delete(d.path)
    return view(rt, updated, user)


def qual_band(words: int) -> str:
    if words <= 20_000:
        return "QL_SMALL"
    if words <= 60_000:
        return "QL_STANDARD"
    return "QL_LARGE"


def start_themes(rt: Runtime, user: User, project_id: str) -> JobView:
    """The qualitative analysis (the paid step): priced by its tier, held when it starts, charged only when delivered."""
    from app.datalab import qual

    _require(rt, user)
    require_terms(rt, user)
    if not work_prices_set(rt.settings, "DATALAB_QUAL"):
        raise AppError("The qualitative analysis isn't available yet.", code="REPORT_NOT_PRICED")
    p = _owned(rt, user, project_id)
    if p.kind != "QUAL":
        raise AppError("This project analyses a dataset: run analyses on it instead.", code="WRONG_KIND")
    if step_running(rt, p):
        raise Conflict("PaperAid is already analysing these transcripts.", code="STEP_RUNNING")
    if not p.documents:
        raise AppError("Add at least one transcript first.", code="NO_DOCUMENTS")
    inp = qual.QualInput(project_id=p.id, title=p.title, question=p.purpose,
                         documents=[qual.QualDoc(id=d.id, label=d.label, path=d.path, sha256=d.sha256, words=d.words) for d in p.documents])
    last = rt.store.get(p.jobs[-1]) if p.jobs else None
    if last is not None and resumable(rt, last) and last.selection.datalab == "THEMES":
        before = qual.QualInput.model_validate_json(rt.files.get(f"{last.storage_prefix()}/internal/{qual.INPUT}"))
        if {(d.id, d.sha256) for d in before.documents} == {(d.id, d.sha256) for d in inp.documents} and resume_step(rt, user, last.id):
            job = rt.store.get(last.id)
            assert job is not None
            return job.view()
    words = sum(d.words for d in p.documents)
    tier = qual_band(words)
    from app.works.service import check_credits

    check_credits(rt, user, "DATALAB", fixed_price(rt.settings, tier, None) if rt.settings.pricing_mode == "fixed" else 0)
    _rate_limit(rt, user, "quote", rt.settings.quotes_per_hour)
    data = inp.model_dump_json(by_alias=True).encode()
    sha = hashlib.sha256(data).hexdigest()
    now = utcnow()
    selection = ServiceSelection(datalab="THEMES", datalab_band=tier)
    job = Job(id=f"job_{secrets.token_hex(6)}", status=JobStatus.DRAFT, owner_uid=user.uid, owner_email=user.email, datalab_id=p.id, input_sha256=sha,
              selection=selection, created_at=now, expires_at=now + timedelta(days=rt.settings.retention_days),
              events=[JobEvent(at=now, label=f"Qualitative analysis priced for Data Lab project {p.id}")])
    rt.files.put(f"{job.storage_prefix()}/internal/{qual.INPUT}", data, "application/json")
    job.quote = bound_quote(rt.settings, selection, sha, words, work_engine(rt.settings, "DATALAB"))
    state.transition(job, JobStatus.QUOTED, "Quote issued")
    if not rt.store.create_if_open(job):
        rt.files.delete_prefix(job.storage_prefix())
        raise Conflict(ACCOUNT_CLOSING, code="ACCOUNT_CLOSING")
    seen_active = p.active_job
    documents = {(d.id, d.sha256) for d in inp.documents}

    def gate(j: Job, q: DataProject | None) -> DataProject | None:
        if q is None or q.deleting or q.owner_uid != j.owner_uid or {(d.id, d.sha256) for d in q.documents} != documents:
            return None
        if q.active_job not in (seen_active, j.id):
            return None
        q.active_job = j.id
        q.jobs = q.jobs if j.id in q.jobs else (q.jobs + [j.id])[-100:]
        return _renew(rt, q)

    quote = Quote.model_validate(job.quote.model_dump())
    return submit(rt, user, job.id, quote.id, data_gate=gate)


def export_codebook(rt: Runtime, user: User, project_id: str, version: int | None = None) -> tuple[bytes, str]:
    p = _owned(rt, user, project_id)
    entry = _report_entry(p, version)
    if not entry.workbook:
        raise NotFound("This report has no codebook.")
    return rt.files.get(entry.workbook), f"{_safe_name(p.title, 'Analysis')} - codebook.xlsx"


# --- Chapter Four of a research proposal (owner decision 2026-10-03) ----------------------------------------------


def for_proposal(rt: Runtime, user: User, proposal_id: str) -> DataView:
    """The Data Lab project that holds a proposal's data for Chapter Four: the existing one (its objectives
    brought up to date with the proposal's), or a new one with the proposal's approved specific objectives."""
    _require(rt, user)
    proposal = _proposal_for(rt, user, proposal_id)
    objectives = _objectives(proposal)
    existing = next((d for d in rt.store.list_datalab(user.uid) if d.proposal_id == proposal_id and not d.deleting), None)
    if existing is not None:
        if existing.objectives != objectives:
            existing = _change(rt, user, existing.id, lambda q: _refresh_objectives(q, objectives))
        return view(rt, existing, user)
    now = utcnow()
    project = DataProject(id=f"dl_{secrets.token_hex(6)}", owner_uid=user.uid, owner_email=user.email, title=f"Chapter Four: {proposal.plan.title}"[:200],
                          purpose=proposal.plan.purpose[:1500], created_at=now, updated_at=now, expires_at=now + timedelta(days=rt.settings.retention_days),
                          proposal_id=proposal_id, objectives=objectives)
    if not rt.store.create_datalab_if_open(project):
        raise Conflict(ACCOUNT_CLOSING, code="ACCOUNT_CLOSING")
    return view(rt, project, user)
