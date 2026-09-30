"""Work rules (concept notes, coursework, funding proposals). Like the proposal service, every function
takes the runtime and the verified user, so ownership, versions and state rules can be tested
directly.

- Every edit names the version it started from; a stale edit is refused, never merged (If-Match).
- The requirement set is resolved in one place (app.rules.resolve) and saved as an immutable file;
  the record only moves its pointer. Answers, documents and the READ step all produce a new version.
- A step is an ordinary priced job, frozen when priced and bound to its quote. A step is offered only
  when what it needs is in place: nothing the student must settle is left to be discovered after
  they have paid (Codex review 2026-09-30 #4).
- One step runs at a time per work; genuine actions renew the 30-day expiry."""

import hashlib
import json
import logging
import re
import secrets
from datetime import timedelta
from pathlib import PurePosixPath
from typing import Any, Literal

from app.ai.orchestration import work_engine
from app.analysis import signals
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.logging import log
from app.documents.intake import inspect_upload
from app.jobs import state
from app.jobs.models import Camel, Job, JobEvent, JobStatus, JobView, Quote, ReadinessItem, ServiceSelection, utcnow
from app.jobs.service import ACCOUNT_CLOSING, User, _erase_work, _rate_limit, availability, step_running, submit
from app.latex.convert import convert as to_latex
from app.latex.package import compile_pdf
from app.pricing.quote import bound_quote
from app.proposals import evidence as ev
from app.proposals.pipeline import load_library
from app.rules import compliance
from app.rules.resolve import SKIPPED, resolve
from app.rules.validators import Context
from app.runtime import Runtime
from app.works import budget as budget_engine
from app.works import export, numbers
from app.works.models import (
    AI_NOTE,
    KIND_MODES,
    KIND_VARIANTS,
    Budget,
    ChangeRequest,
    CitationStyle,
    Requirement,
    ResolvedSpec,
    ResultsModel,
    SourceFile,
    SourceRole,
    Work,
    WorkDocument,
    WorkInputs,
    WorkPlan,
    WorkStepInput,
    WorkView,
)
from app.works.pipeline import INPUT, _plan_problems

logger = logging.getLogger("paperaid.works")
Step = Literal["READ", "PLAN", "DRAFT", "REVISE"]
MAX_SOURCES = 12
MAX_SOURCE_WORDS = 60_000
MAX_REQUESTS = 60
MAX_COURSEWORK_WORDS = 8000
MAX_FUNDING_WORDS = 14000


def _valid_id(work_id: str) -> bool:
    return work_id.startswith("wrk_") and work_id[4:].isalnum() and len(work_id) <= 40


def _owned(rt: Runtime, user: User, work_id: str) -> Work:
    work = rt.store.get_work(work_id) if _valid_id(work_id) else None
    if work is None or work.owner_uid != user.uid or work.deleting:
        raise NotFound("We couldn't find this work.")
    return work


def _require(rt: Runtime, user: User, kind: str) -> None:
    if availability(rt.settings, user).get(kind) != "available":
        raise AppError("This service is not available on your account yet.", code="SERVICE_UNAVAILABLE")


def _renew(rt: Runtime, k: Work) -> Work:
    now = utcnow()
    k.updated_at, k.expires_at = now, now + timedelta(days=rt.settings.retention_days)
    return k


def _change(rt: Runtime, user: User, work_id: str, mutate, conflict: str = "This work changed meanwhile. Reload it and try again.") -> Work:
    """Apply an owner action atomically, renewing the expiry."""
    _owned(rt, user, work_id)
    refusal: list[AppError] = []

    def apply(k: Work) -> Work | None:
        if k.deleting or k.owner_uid != user.uid:
            return None
        try:
            result = mutate(k)
        except AppError as exc:  # a rule broken against the current record: reported after the transaction
            refusal.append(exc)
            return None
        return _renew(rt, result) if result is not None else None

    updated = rt.store.update_work(work_id, apply)
    if refusal:
        raise refusal[0]
    if updated is None:
        raise Conflict(conflict, code="WORK_CHANGED")
    return updated


def _expect(current: int, base: int, what: str) -> None:
    if current != base:
        raise Conflict(f"Your {what} changed since you opened it (another tab or a finished step). Reload to see the latest version.", code="VERSION_CHANGED")


# --- the requirement set -----------------------------------------------------------------------------


def spec_of(rt: Runtime, work: Work) -> ResolvedSpec | None:
    if not work.spec_path or not rt.files.exists(work.spec_path):
        return None
    return ResolvedSpec.model_validate_json(rt.files.get(work.spec_path))


def _external(rt: Runtime, work: Work) -> tuple[list[Requirement], list[str]]:
    if not work.requirements_path or not rt.files.exists(work.requirements_path):
        return [], []
    data = json.loads(rt.files.get(work.requirements_path))
    return [Requirement.model_validate(r) for r in data.get("requirements", [])], list(data.get("unclear", []))


def respec(rt: Runtime, work: Work) -> Work:
    """Resolve the requirement set again from the work's inputs, documents and what was read. A new
    version is written only when something changed; a changed set needs confirming again and puts
    an approved plan back to draft (it was planned against the old set)."""
    external, unclear = _external(rt, work)
    read = {s.id for s in work.sources if s.id in set(work.read_sources)}
    spec = resolve(work.spec_version + 1, work.kind, work.variant, work.mode, work.inputs, [s for s in work.sources if s.id in read], external, unclear)
    prior = spec_of(rt, work)
    if prior is not None and prior.model_dump(exclude={"version"}) == spec.model_dump(exclude={"version"}):
        return work
    data = spec.model_dump_json(by_alias=True).encode()
    path = f"{work.storage_prefix()}/spec/v{spec.version}-{hashlib.sha256(data).hexdigest()[:12]}.json"
    rt.files.put(path, data, "application/json")  # immutable, written before the pointer moves
    work.spec_path, work.spec_version, work.spec_status = path, spec.version, "DRAFT"
    if work.plan_status == "APPROVED":
        work.plan_status = "DRAFT"
    return work


# --- the student's views -----------------------------------------------------------------------------


def _doc(rt: Runtime, work: Work, version: int | None = None) -> WorkDocument | None:
    number = version or work.current
    entry = next((d for d in work.documents if d.version == number), None)
    if entry is None or not rt.files.exists(entry.path):
        return None
    return WorkDocument.model_validate_json(rt.files.get(entry.path))


def view(rt: Runtime, work: Work) -> WorkView:
    out = work.view()
    spec = spec_of(rt, work)
    out.spec = spec
    doc = _doc(rt, work)
    if doc is not None:
        out.readiness, out.status = doc.readiness, doc.status
    if spec is not None:
        out.checks = before_draft(rt, work, spec)
    out.needs_read = any(s.id not in set(work.read_sources) for s in work.sources)
    if work.budget is not None and work.budget.lines:
        t = budget_engine.totals(work.budget)
        out.budget_totals = {"total": t.total, "direct": t.direct, "indirect": t.indirect, "byCategory": t.by_category, "byYear": {str(y): v for y, v in t.by_year.items()},
                             "lines": {li.id: budget_engine.line_total(li) for li in work.budget.lines}, "currency": work.budget.currency}
    out.active_job = work.active_job if step_running(rt, work) else None
    return out


def before_draft(rt: Runtime, work: Work, spec: ResolvedSpec) -> list[ReadinessItem]:
    """The code checks that must hold before a draft is priced: the plan against the requirement
    set, and for funding the Results Model and budget (their arithmetic and links)."""
    ctx = Context(spec=spec, stage="PLAN", inputs=work.inputs, plan=work.plan, results=work.results, budget=work.budget,
                  library=load_library(rt.files, work.evidence_files), tokens=numbers.values(spec, work.results, work.budget, work.inputs))
    return compliance.report(ctx, ("PLAN", "FINAL")) if work.plan is not None else []


def create(rt: Runtime, user: User, kind: str, variant: str, mode: str, inputs: WorkInputs, citation: CitationStyle) -> WorkView:
    if not user.verified:
        raise Forbidden("Verify your email address before starting.", code="EMAIL_NOT_VERIFIED")
    if kind not in KIND_VARIANTS or variant not in KIND_VARIANTS[kind]:
        raise AppError("Choose what you are preparing.", code="INVALID_VARIANT")
    mode = mode if kind != "COURSEWORK" else ""
    if mode not in KIND_MODES[kind]:
        raise AppError("Choose a length.", code="INVALID_MODE")
    _require(rt, user, kind)
    _rate_limit(rt, user, "work", rt.settings.quotes_per_hour)
    if kind == "COURSEWORK" and "citation_style" not in inputs.answers:  # the style chosen on the first screen is the student's answer
        inputs = inputs.model_copy(update={"answers": {**inputs.answers, "citation_style": citation}})
    now = utcnow()
    work = Work(
        id=f"wrk_{secrets.token_hex(6)}", owner_uid=user.uid, owner_email=user.email, kind=kind, variant=variant, mode=mode, citation=citation,  # type: ignore[arg-type]
        inputs=inputs, created_at=now, updated_at=now, expires_at=now + timedelta(days=rt.settings.retention_days),
    )
    respec(rt, work)
    if not rt.store.create_work_if_open(work):
        rt.files.delete_prefix(work.storage_prefix())
        raise Conflict(ACCOUNT_CLOSING, code="ACCOUNT_CLOSING")
    log(logger, logging.INFO, "work created", workId=work.id, kind=kind)
    return view(rt, work)


def list_mine(rt: Runtime, user: User) -> list[WorkView]:
    return [view(rt, k) for k in rt.store.list_works(user.uid) if not k.deleting]


def get(rt: Runtime, user: User, work_id: str) -> WorkView:
    return view(rt, _owned(rt, user, work_id))


def update_inputs(rt: Runtime, user: User, work_id: str, inputs: WorkInputs, mode: str | None, variant: str | None, citation: CitationStyle | None, base_version: int) -> WorkView:
    """The student's description and answers (their own facts, locked once given), length, kind
    and citation style. The requirement set is resolved again; nothing written is changed."""

    def apply(k: Work) -> Work:
        _expect(k.spec_version, base_version, "details")
        if variant is not None and variant != k.variant:
            if k.plan is not None or k.documents:
                raise AppError("The kind of work is fixed once it has a plan. Start a new one to change it.", code="VARIANT_FIXED")
            if variant not in KIND_VARIANTS[k.kind]:
                raise AppError("Choose what you are preparing.", code="INVALID_VARIANT")
            k.variant = variant  # type: ignore[assignment]
        if mode is not None and mode != k.mode:
            if mode not in KIND_MODES[k.kind]:
                raise AppError("Choose a length.", code="INVALID_MODE")
            k.mode = mode  # type: ignore[assignment]
        given = inputs
        if citation is not None:
            k.citation = citation
            if k.kind == "COURSEWORK":
                given = inputs.model_copy(update={"answers": {**inputs.answers, "citation_style": citation}})
        k.inputs = given
        return respec(rt, k)

    return view(rt, _change(rt, user, work_id, apply))


def answer(rt: Runtime, user: User, work_id: str, answers: dict[str, str], base_version: int, skip_rest: bool = False) -> WorkView:
    """Answers to the questions on the "PaperAid understood" screen (confirmations, conflicts,
    eligibility and the ask-once questions). `skip_rest` accepts PaperAid's stated fallback for every
    ask-once question still open; blocking questions can never be skipped."""

    def apply(k: Work) -> Work:
        _expect(k.spec_version, base_version, "requirements")
        merged = {**k.inputs.answers, **{a: v.strip()[:3000] for a, v in answers.items() if a and isinstance(v, str)}}
        if skip_rest:
            spec = spec_of(rt, k)
            for q in spec.questions if spec else []:
                if q.gate == "ASK_ONCE" and not q.answered and not merged.get(q.id):
                    merged[q.id] = SKIPPED
        k.inputs = k.inputs.model_copy(update={"answers": {a: v for a, v in merged.items() if v}})
        return respec(rt, k)

    return view(rt, _change(rt, user, work_id, apply))


def confirm_spec(rt: Runtime, user: User, work_id: str, base_version: int) -> WorkView:
    """The student confirms what PaperAid understood. Only possible when nothing blocks it."""

    def apply(k: Work) -> Work:
        _expect(k.spec_version, base_version, "requirements")
        spec = spec_of(rt, k)
        if spec is None:
            raise AppError("PaperAid has not worked out the requirements yet.", code="NO_SPEC")
        if spec.gate == "BLOCK":
            raise AppError("Before PaperAid can plan: " + " ".join(spec.blockers), code="SPEC_BLOCKED")
        if spec.gate == "ASK_ONCE":
            raise AppError("Answer the remaining questions, or accept PaperAid's defaults for them.", code="QUESTIONS_OPEN")
        if any(s.id not in set(k.read_sources) for s in k.sources):
            raise AppError("PaperAid has not read your latest documents yet. Read them first.", code="SOURCES_UNREAD")
        k.spec_status = "CONFIRMED"
        return k

    return view(rt, _change(rt, user, work_id, apply))


def set_ai_note(rt: Runtime, user: User, work_id: str, on: bool) -> WorkView:
    """Coursework whose AI rule is unknown: the student may leave out the last-page note. When the
    brief bans AI the note is always added (owner decision 2026-09-30)."""

    def apply(k: Work) -> Work:
        k.ai_note = on
        return k

    return view(rt, _change(rt, user, work_id, apply))


# --- the student's documents ---------------------------------------------------------------------------


def _attach(rt: Runtime, user: User, work_id: str, name: str, role: SourceRole, text: str, words: int) -> WorkView:
    work = _owned(rt, user, work_id)
    if step_running(rt, work):
        raise Conflict("A step is running. Add documents after it finishes.", code="STEP_RUNNING")
    sid = f"src_{secrets.token_hex(4)}"
    path = f"{work.storage_prefix()}/sources/{sid}.txt"
    rt.files.put(path, text.encode("utf-8"), "text/plain")
    source = SourceFile(id=sid, name=name[:120] or "document", role=role, words=words, sha256=hashlib.sha256(text.encode()).hexdigest(), path=path)

    def apply(k: Work) -> Work:
        if step_running(rt, k):
            raise Conflict("A step is running. Add documents after it finishes.", code="STEP_RUNNING")
        if len(k.sources) >= MAX_SOURCES:
            raise AppError(f"A work keeps up to {MAX_SOURCES} documents. Remove one first.", code="TOO_MANY_SOURCES")
        k.sources.append(source)
        k.spec_status = "DRAFT"  # read the new document before confirming again
        return k

    attached: Work | None = None
    try:
        attached = _change(rt, user, work_id, apply)
    finally:
        if attached is None:
            rt.files.delete(path)
    return view(rt, attached)


def upload_source(rt: Runtime, user: User, work_id: str, role: SourceRole, filename: str, data: bytes) -> WorkView:
    _rate_limit(rt, user, "upload", rt.settings.uploads_per_hour)
    model = inspect_upload(data, filename, rt.settings.max_upload_bytes, MAX_SOURCE_WORDS, rt.settings.max_pdf_pages, min_words=10)
    text = "\n".join(b.text for b in model.blocks if b.text.strip())
    return _attach(rt, user, work_id, PurePosixPath(filename).name, role, text, model.word_count)


def paste_source(rt: Runtime, user: User, work_id: str, role: SourceRole, name: str, text: str) -> WorkView:
    _rate_limit(rt, user, "upload", rt.settings.uploads_per_hour)
    clean = text.strip()
    words = len(clean.split())
    if words < 5:
        raise AppError("Paste the text of the document.", code="TOO_SHORT")
    if words > MAX_SOURCE_WORDS:
        raise AppError(f"That text is too long ({words:,} words; up to {MAX_SOURCE_WORDS:,}).", code="TOO_LONG")
    return _attach(rt, user, work_id, name or "Pasted text", role, clean, words)


def remove_source(rt: Runtime, user: User, work_id: str, source_id: str) -> WorkView:
    removed: list[str] = []

    def apply(k: Work) -> Work:
        if step_running(rt, k):
            raise Conflict("A step is running. Remove documents after it finishes.", code="STEP_RUNNING")
        removed[:] = [s.path for s in k.sources if s.id == source_id]
        k.sources = [s for s in k.sources if s.id != source_id]
        k.read_sources = [s for s in k.read_sources if s != source_id]
        if removed and k.requirements_path:
            external, unclear = _external(rt, k)
            kept = [r for r in external if r.source_id != source_id]
            data = json.dumps({"requirements": [r.model_dump(by_alias=True) for r in kept], "unclear": unclear, "readings": {}}).encode()
            path = f"{k.storage_prefix()}/requirements/edit-{hashlib.sha256(data).hexdigest()[:12]}.json"
            rt.files.put(path, data, "application/json")
            k.requirements_path = path
        return respec(rt, k)

    changed = _change(rt, user, work_id, apply)
    for path in removed:
        rt.files.delete(path)
    return view(rt, changed)


# --- the plan, Results Model and budget -----------------------------------------------------------------


def save_plan(rt: Runtime, user: User, work_id: str, plan: WorkPlan, base_version: int) -> WorkView:
    """The student's edit of the plan: sections renamed, resized or (when not required) removed, within
    the requirement set's limits. It needs approving again."""

    def apply(k: Work) -> Work:
        _expect(k.plan_version, base_version, "plan")
        if k.plan is None:
            raise AppError("Create a plan first.", code="NO_PLAN")
        before = {s.key: s for s in k.plan.sections}
        for s in plan.sections:
            original = before.get(s.key)
            if original is not None and original.locked and s.heading != original.heading:
                raise AppError(f"\"{original.heading}\" is required by your instructions and keeps its wording.", code="SECTION_LOCKED")
        dropped = [s.heading for s in k.plan.sections if (s.required or s.locked) and s.key not in {p.key for p in plan.sections}]
        if dropped:
            raise AppError("These sections are required and cannot be removed: " + "; ".join(dropped), code="SECTION_REQUIRED")
        merged = [before[s.key].model_copy(update={"heading": s.heading, "words": s.words, "brief": s.brief}) if s.key in before else s.model_copy(update={"locked": False, "required": False})
                  for s in plan.sections]
        k.plan = plan.model_copy(update={"sections": merged})
        k.plan_status, k.plan_version = "DRAFT", k.plan_version + 1
        return k

    return view(rt, _change(rt, user, work_id, apply))


def approve_plan(rt: Runtime, user: User, work_id: str, base_version: int) -> WorkView:
    def apply(k: Work) -> Work:
        _expect(k.plan_version, base_version, "plan")
        spec = spec_of(rt, k)
        if k.plan is None or spec is None:
            raise AppError("Create a plan first.", code="NO_PLAN")
        problems = _plan_problems(k.plan, spec)
        if problems:
            raise AppError("Fix the plan before approving it: " + " ".join(problems), code="PLAN_INCOMPLETE")
        k.plan_status = "APPROVED"
        return k

    return view(rt, _change(rt, user, work_id, apply))


def take_candidate(rt: Runtime, user: User, work_id: str, accept: bool) -> WorkView:
    def apply(k: Work) -> Work:
        if k.candidate_plan is not None and accept:
            k.plan, k.plan_status, k.plan_version = k.candidate_plan, "DRAFT", k.plan_version + 1
        k.candidate_plan = None
        return k

    return view(rt, _change(rt, user, work_id, apply))


def save_results(rt: Runtime, user: User, work_id: str, model: ResultsModel, base_version: int) -> WorkView:
    """The student's Results Model: the one source of the goal, results, indicators, targets and dates."""

    def apply(k: Work) -> Work:
        _expect(k.results_version, base_version, "Results Model")
        if k.kind != "FUNDING_PROPOSAL":
            raise AppError("Only funding proposals have a Results Model.", code="NOT_FUNDING")
        k.results, k.results_status, k.results_version = model, "DRAFT", k.results_version + 1
        return k

    return view(rt, _change(rt, user, work_id, apply))


def approve_results(rt: Runtime, user: User, work_id: str, base_version: int) -> WorkView:
    def apply(k: Work) -> Work:
        _expect(k.results_version, base_version, "Results Model")
        if k.results is None or not k.results.goal.statement.strip() or not k.results.outcomes:
            raise AppError("Build the Results Model first.", code="NO_RESULTS")
        k.results_status = "APPROVED"
        return k

    return view(rt, _change(rt, user, work_id, apply))


def save_budget(rt: Runtime, user: User, work_id: str, budget: Budget, base_version: int) -> WorkView:
    """The student's budget lines. Code computes every total; nothing here is changed by a model."""
    ids = [li.id for li in budget.lines]
    if len(ids) != len(set(ids)):
        raise AppError("Each budget line needs its own id.", code="DUPLICATE_LINE")

    def apply(k: Work) -> Work:
        _expect(k.budget_version, base_version, "budget")
        k.budget, k.budget_version = budget, k.budget_version + 1
        return k

    return view(rt, _change(rt, user, work_id, apply))


# --- steps --------------------------------------------------------------------------------------------------


class WorkStepQuote(Camel):
    job: JobView
    quote: Quote
    notice: str | None = None  # what the student must know before buying (the last-page note, an exploratory draft)


def _band(spec: ResolvedSpec, step: Step) -> str:
    prefix = {"CONCEPT_NOTE": "CN", "COURSEWORK": "CW", "FUNDING_PROPOSAL": "FP"}[spec.kind]
    if step == "READ":
        return "WORK_READ"
    if step == "REVISE":
        return "WORK_REVISE"
    if step == "PLAN":
        return f"{prefix}_PLAN"
    words = spec.target_words
    if spec.kind == "COURSEWORK":
        if words > MAX_COURSEWORK_WORDS:
            raise AppError(f"PaperAid writes coursework of up to {MAX_COURSEWORK_WORDS:,} words.", code="TOO_LONG")
        return "CW_1500" if words <= 1500 else "CW_3000" if words <= 3000 else "CW_5000" if words <= 5000 else "CW_8000"
    if spec.kind == "FUNDING_PROPOSAL":
        if words > MAX_FUNDING_WORDS:
            raise AppError(f"PaperAid writes funding proposals of up to {MAX_FUNDING_WORDS:,} words.", code="TOO_LONG")
        if spec.mode and not any(limit.type in ("WORD", "PAGE", "FIELD") for limit in spec.limits):
            return f"FP_{spec.mode}"
        return "FP_COMPACT" if words <= 3000 else "FP_STANDARD" if words <= 6500 else "FP_COMPREHENSIVE"
    if spec.mode and not any(limit.type in ("WORD", "PAGE", "FIELD") for limit in spec.limits):
        return f"CN_{spec.mode}"
    return "CN_BRIEF" if words <= 1200 else "CN_STANDARD" if words <= 2300 else "CN_EXTENDED"


def _draft_blockers(rt: Runtime, k: Work, spec: ResolvedSpec) -> list[str]:
    problems = []
    if k.spec_status != "CONFIRMED":
        problems.append("Confirm what PaperAid understood first.")
    if k.plan is None or k.plan_status != "APPROVED":
        problems.append("Approve your plan first.")
    if k.kind == "FUNDING_PROPOSAL":
        if k.results is None or k.results_status != "APPROVED":
            problems.append("Approve your Results Model first.")
        if k.budget is None or not k.budget.lines or not any(li.unit_cost for li in k.budget.lines):
            problems.append("Add your budget lines (quantities and unit costs) first.")
    for item in before_draft(rt, k, spec):
        # Only a failed blocking check stops the draft. What PaperAid cannot measure yet (a page count
        # before rendering) does not, and neither does an eligibility criterion the student knowingly
        # does not meet when they chose an exploratory draft.
        if item.status != "BLOCKED" or (spec.exploratory and item.id in ("CN-042", "FP-003")):
            continue
        problems.append(f"{item.question}: {item.note}")
    return problems


def quote_step(rt: Runtime, user: User, work_id: str, step: Step, note: str) -> WorkStepQuote:
    """Freeze the work's input for a step, price it and return the quote. Nothing is held until the
    student submits. A step is priced only when everything it needs from the student is in place."""
    k = _owned(rt, user, work_id)
    _require(rt, user, k.kind)
    if step_running(rt, k):
        raise Conflict("A step is already running for this work. Wait for it to finish.", code="STEP_RUNNING")
    spec = spec_of(rt, k)
    if spec is None:
        raise AppError("PaperAid has not worked out the requirements yet.", code="NO_SPEC")
    note = note.strip()[:1000]
    words = spec.target_words
    base, base_sha, base_version, revise, request_ids = "", "", 0, {}, []
    if step == "READ":
        if not k.sources:
            raise AppError("Add your call, brief or template first.", code="NO_SOURCES")
        words = sum(s.words for s in k.sources)
    elif step == "PLAN":
        if spec.gate == "BLOCK":
            raise AppError("Before PaperAid can plan: " + " ".join(spec.blockers), code="SPEC_BLOCKED")
        if k.spec_status != "CONFIRMED":
            raise AppError("Confirm what PaperAid understood first.", code="SPEC_NOT_CONFIRMED")
    elif step == "DRAFT":
        blockers = _draft_blockers(rt, k, spec)
        if blockers:
            raise AppError("Before the draft can be written: " + " ".join(blockers), code="NOT_READY_TO_DRAFT")
    else:  # REVISE
        doc = _doc(rt, k)
        if doc is None:
            raise AppError("Write the document before asking for changes.", code="NOTHING_TO_REVISE")
        entry = next(d for d in k.documents if d.version == k.current)
        base, base_version = entry.path, entry.version
        base_sha = hashlib.sha256(rt.files.get(base)).hexdigest()
        written = {s.key for s in doc.sections}
        for request in k.requests:
            if request.status != "OPEN":
                continue
            for key in request.sections or list(written):
                if key in written and len(revise.setdefault(key, [])) < 8:
                    revise[key].append(request.text)
            request_ids.append(request.id)
        revise = {key: texts for key, texts in revise.items() if texts}
        if not revise:
            raise AppError("Say what you would like changed first.", code="NO_REQUESTS")
        words = sum(len(ev.ANY_TOKEN.sub(" ", p).split()) for s in doc.sections if s.key in revise for p in s.paragraphs)
    _rate_limit(rt, user, "quote", rt.settings.quotes_per_hour)
    band = _band(spec, step)
    inp = WorkStepInput(
        work_id=k.id, step=step, kind=k.kind, variant=k.variant, mode=k.mode, level=spec.level, citation=spec.citation_style, inputs=k.inputs,
        sources=[s for s in k.sources if step == "READ" or s.role == "READING"], spec=spec if step != "READ" else None,
        plan=k.plan if step in ("DRAFT", "REVISE") else None, plan_version=k.plan_version, results=k.results if step in ("DRAFT", "REVISE") else None,
        results_version=k.results_version, budget=k.budget if step in ("DRAFT", "REVISE") else None, budget_version=k.budget_version,
        evidence_files=list(k.evidence_files), note=note, ai_note=k.ai_note, exploratory=spec.exploratory,
        base=base, base_version=base_version, base_sha=base_sha, revise=revise, request_ids=request_ids,
        private=_private_words(rt, k, user) if step in ("PLAN", "DRAFT") else [],
    )
    if step == "PLAN":
        inp.plan_version = k.plan_version
    data = inp.model_dump_json(by_alias=True).encode()
    sha = hashlib.sha256(data).hexdigest()
    now = utcnow()
    selection = ServiceSelection(work=step, work_kind=k.kind, work_band=band)
    label_note = "exploratory draft, not ready to submit" if step == "DRAFT" and spec.exploratory else ""
    job = Job(
        id=f"job_{secrets.token_hex(6)}", status=JobStatus.DRAFT, owner_uid=user.uid, owner_email=user.email, work_id=k.id, input_sha256=sha, selection=selection,
        created_at=now, expires_at=now + timedelta(days=rt.settings.retention_days), events=[JobEvent(at=now, label=f"{step.title()} step priced for work {k.id}")],
    )
    rt.files.put(f"{job.storage_prefix()}/internal/{INPUT}", data, "application/json")
    job.quote = bound_quote(rt.settings, selection, sha, max(1, words), work_engine(rt.settings, k.kind), note=label_note)
    state.transition(job, JobStatus.QUOTED, "Quote issued")
    if not rt.store.create_if_open(job):
        rt.files.delete_prefix(job.storage_prefix())
        raise Conflict(ACCOUNT_CLOSING, code="ACCOUNT_CLOSING")
    current = rt.store.get_work(k.id)
    if current is None or current.deleting:
        rt.files.delete_prefix(job.storage_prefix())
        rt.store.delete(job.id)
        raise NotFound("We couldn't find this work.")
    notice = None
    if step in ("DRAFT", "REVISE") and k.kind == "COURSEWORK" and spec.ai_policy == "BANNED":
        notice = (f"Your assignment says AI tools are not allowed. Because of that, PaperAid adds a short note on the last page of your Word "
                  f"document: \"{AI_NOTE}\"")
    elif step == "DRAFT" and spec.exploratory:
        notice = "You do not meet every eligibility criterion, so this is an exploratory draft: it is marked as not ready to submit."
    return WorkStepQuote(job=job.view(), quote=Quote.model_validate(job.quote.model_dump()), notice=notice)


TITLED = re.compile(r"\b(?:Dr|Mr|Mrs|Ms|Miss|Prof|Professor|Sister|Nurse|Pastor|Rev)\.?\s+([A-Z][a-z'’-]+(?:\s+[A-Z][a-z'’-]+)?)")


def _private_words(rt: Runtime, k: Work, user: User) -> list[str]:
    """Words that must never reach a web or scholarly search (Codex audit 2026-09-30 #8): the student's
    own name parts from their email, every titled name (Dr Okello, Sister Namuli) in their details and
    documents, and the capitalised names inside sentences of their own account of their experience,
    except words of the topic itself, which the searches need. Checked on the queries proposed and on
    those actually sent."""
    topic = {w.lower() for w in re.findall(r"[A-Za-z'’-]+", " ".join([k.inputs.title, k.inputs.description]))}
    words = {w.lower() for w in re.split(r"[^A-Za-z]+", user.email.split("@")[0]) if len(w) > 2}
    texts = [k.inputs.description, k.inputs.experience, *k.inputs.answers.values()]
    texts += [rt.files.get(s.path).decode("utf-8") for s in k.sources if rt.files.exists(s.path)]
    for text in texts:
        for match in TITLED.finditer(text):
            words |= {w.lower() for w in match.group(1).split()}
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", k.inputs.experience):
        inner = re.findall(r"[A-Za-z'’-]+", sentence)[1:]  # a sentence's first word is capitalised anyway
        words |= {w.lower() for w in inner if w[0].isupper() and len(w) > 2} - topic
    return sorted(words - signals.STOPWORDS)[:500]


def _current(k: Work, inp: WorkStepInput) -> bool:
    """A step runs only on the versions it was priced on."""
    if inp.step == "READ":
        return all(any(s.id == src.id for s in k.sources) for src in inp.sources)
    if inp.spec is None or k.spec_version != inp.spec.version:
        return False
    if inp.step == "PLAN":
        return k.spec_status == "CONFIRMED" and k.plan_version == inp.plan_version
    if k.plan_version != inp.plan_version or k.results_version != inp.results_version or k.budget_version != inp.budget_version:
        return False
    if inp.step == "REVISE":
        return k.current == inp.base_version
    return True


def submit_step(rt: Runtime, user: User, work_id: str, job_id: str, quote_id: str) -> JobView:
    """Accept a step's quote. The work is checked and claimed in the same transaction that holds the
    credits: still the student's, not being deleted, on the versions the step was priced on, and
    with no other step claimed since it was looked at."""
    k = _owned(rt, user, work_id)
    job = rt.store.get(job_id)
    if job is None or job.owner_uid != user.uid or job.work_id != k.id:
        raise NotFound("We couldn't find this step.")
    inp = WorkStepInput.model_validate_json(rt.files.get(f"{job.storage_prefix()}/internal/{INPUT}"))
    if job.status not in state.SUBMITTED:
        if not _current(k, inp):
            raise Conflict("Your work changed after this step was priced. Price it again so it uses your latest version.", code="QUOTE_MISMATCH")
        if k.active_job != job_id and step_running(rt, k):
            raise Conflict("A step is already running for this work. Wait for it to finish.", code="STEP_RUNNING")
    seen_active = k.active_job

    def gate(j: Job, w: Work | None) -> Work | None:
        if w is None or w.deleting or w.owner_uid != j.owner_uid or not _current(w, inp):
            return None
        if w.active_job not in (seen_active, j.id):
            return None
        w.active_job = j.id
        w.jobs = w.jobs if j.id in w.jobs else (w.jobs + [j.id])[-100:]
        return _renew(rt, w)

    return submit(rt, user, job_id, quote_id, work_gate=gate)


def request_changes(rt: Runtime, user: User, work_id: str, text: str, sections: list[str]) -> WorkView:
    """Ask for changes: the student's own words reach the writer, on the sections chosen (or all)."""
    clean = " ".join(text.split())[:1500]
    if len(clean) < 3:
        raise AppError("Say what you would like changed.", code="NO_REQUEST")
    k = _owned(rt, user, work_id)
    doc = _doc(rt, k)
    if doc is None:
        raise AppError("Write the document before asking for changes.", code="NOTHING_TO_REVISE")
    keys = {s.key for s in doc.sections}
    chosen = [s for s in dict.fromkeys(sections) if s in keys]

    def apply(w: Work) -> Work:
        if len(w.requests) >= MAX_REQUESTS:
            raise AppError("Remove requests already dealt with first.", code="TOO_MANY_REQUESTS")
        w.requests.append(ChangeRequest(id=f"rq_{secrets.token_hex(4)}", text=clean, sections=chosen))
        return w

    return view(rt, _change(rt, user, work_id, apply))


def remove_request(rt: Runtime, user: User, work_id: str, request_id: str) -> WorkView:
    def apply(w: Work) -> Work:
        w.requests = [r for r in w.requests if r.id != request_id]
        return w

    return view(rt, _change(rt, user, work_id, apply))


def set_version(rt: Runtime, user: User, work_id: str, version: int) -> WorkView:
    def apply(w: Work) -> Work:
        if not any(d.version == version for d in w.documents):
            raise NotFound("That version doesn't exist.")
        w.current = version
        return w

    return view(rt, _change(rt, user, work_id, apply))


# --- the document --------------------------------------------------------------------------------------------


class RenderedSection(Camel):
    key: str
    heading: str
    paragraphs: list[str]
    table: list[list[str]] | None = None
    table_caption: str = ""
    field_limit: str = ""
    field_count: str = ""


class DocumentView(Camel):
    version: int
    title: str
    status: str
    exploratory: bool
    sections: list[RenderedSection]
    references: list[str]
    readiness: list[ReadinessItem]
    words: int
    ai_note: str
    tables: list[dict[str, Any]] = []  # funding: logframe, workplan, M&E and budget tables (rendered from the data)


def document(rt: Runtime, user: User, work_id: str, version: int | None = None) -> DocumentView:
    k = _owned(rt, user, work_id)
    doc = _doc(rt, k, version)
    if doc is None:
        raise NotFound("This document hasn't been written yet.")
    spec = doc.spec_snapshot or spec_of(rt, k)
    assert spec is not None
    library = load_library(rt.files, k.evidence_files)
    tokens = {key: (v[0], v[1]) for key, v in doc.number_values.items()}
    citer = ev.Citer(library, spec.citation_style)
    fields = {f.id: f for f in spec.fields}
    sections = []
    for s in doc.sections:
        paragraphs = [numbers.render(citer.render(p), tokens)[0] for p in s.paragraphs]
        field = fields.get(s.field_id)
        text = " ".join(paragraphs)
        sections.append(RenderedSection(
            key=s.key, heading=s.heading, paragraphs=paragraphs,
            table=[[numbers.render(citer.render(c), tokens)[0] for c in row] for row in s.table] if s.table else None, table_caption=s.table_caption,
            field_limit=(f"{field.max_characters:,} characters" if field.max_characters else f"{field.max_words:,} words") if field else "",
            field_count=(f"{len(text):,} characters" if field.max_characters else f"{len(text.split()):,} words") if field else "",
        ))
    tables: list[dict[str, Any]] = []
    from app.works import results as results_engine
    from app.works.export import _budget_tables

    if doc.results_snapshot is not None:
        if doc.variant == "NGO_PROJECT":
            tables.append({"caption": "Logframe", "rows": results_engine.logframe(doc.results_snapshot)})
        tables.append({"caption": "Workplan", "rows": results_engine.workplan(doc.results_snapshot, spec.duration_months)})
        tables.append({"caption": "Monitoring and evaluation indicators", "rows": results_engine.mel_table(doc.results_snapshot)})
    if doc.budget_snapshot is not None and doc.budget_snapshot.lines:
        summary, detail = _budget_tables(doc.budget_snapshot)
        tables.append({"caption": "Budget summary", "rows": summary})
        if spec.kind == "FUNDING_PROPOSAL":
            tables.append({"caption": "Detailed budget", "rows": detail})
    cited = [i for i in doc.cited if i in library]
    return DocumentView(
        version=version or k.current, title=doc.title, status=doc.status, exploratory=doc.exploratory, sections=sections,
        references=ev.reference_list([library[i].source for i in cited], spec.citation_style), readiness=doc.readiness, words=doc.words, ai_note=doc.ai_note, tables=tables,
    )


def export_docx(rt: Runtime, user: User, work_id: str, version: int | None = None) -> tuple[bytes, str]:
    k = _owned(rt, user, work_id)
    doc = _doc(rt, k, version)
    if doc is None:
        raise AppError("Write the document before downloading it.", code="NOTHING_TO_EXPORT")
    spec = doc.spec_snapshot or spec_of(rt, k)
    assert spec is not None
    data = export.build(doc, spec, doc.results_snapshot, doc.budget_snapshot, load_library(rt.files, k.evidence_files),
                        {key: (v[0], v[1]) for key, v in doc.number_values.items()}, draft=doc.status == "NOT_READY")
    _change(rt, user, work_id, lambda w: w)  # downloading renews the work
    safe = "".join(c for c in doc.title[:80] if c.isalnum() or c in " -_").strip() or "Document"
    return data, f"{safe}{' – exploratory draft' if doc.exploratory else ''}.docx"


def export_pdf(rt: Runtime, user: User, work_id: str, version: int | None = None) -> tuple[bytes, str]:
    """The same document as a PDF for reading (converted from the Word file offline, no AI). A PDF
    that would leave anything out is refused (Codex review 2026-09-30)."""
    data, name = export_docx(rt, user, work_id, version)
    converted = to_latex(data)
    if converted.omitted:
        raise AppError("Part of this document could not be converted to PDF. Download the Word file instead.", code="PDF_INCOMPLETE")
    _rate_limit(rt, user, "pdf", rt.settings.uploads_per_hour)
    pdf, problem = compile_pdf(converted)
    if pdf is None:
        log(logger, logging.WARNING, "work pdf failed", workId=work_id, problem=problem)
        raise AppError("The PDF could not be made this time. Download the Word file instead.", code="PDF_FAILED")
    return pdf, name.removesuffix(".docx") + ".pdf"


def delete(rt: Runtime, user: User, work_id: str) -> None:
    k = rt.store.get_work(work_id) if _valid_id(work_id) else None
    if k is None or k.owner_uid != user.uid:
        return
    if not _erase_work(rt, k) and rt.store.get_work(k.id) is not None:
        raise Conflict("A step is running for this work. Delete it when the step finishes.", code="STEP_RUNNING")
    log(logger, logging.INFO, "work deleted", workId=work_id)
