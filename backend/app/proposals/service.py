"""Proposal project rules. Like app.jobs.service, every function takes the runtime and the verified
user, so ownership, versions and state rules can be tested directly.

- Every change to the plan names the version it started from; a stale edit is refused, never
  silently merged (Codex review: two tabs must not overwrite each other).
- A step (the plan, a chapter) is an ordinary priced job linked to the project. Its input is frozen
  when it is priced and bound to the quote; submitting checks the plan has not changed since.
- One step runs at a time per project: the claim is taken on the project record before the quote is
  accepted, and a claim whose job is no longer queued or running is free again.
- Genuine actions renew the project's expiry (30 days); reading it does not."""

import hashlib
import logging
import secrets
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel

from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.logging import log
from app.jobs import state
from app.jobs.models import Job, JobEvent, JobStatus, JobView, Quote, QuoteLine, ReadinessItem, ServiceSelection, utcnow
from app.jobs.service import ACCOUNT_CLOSING, User, _erase_project, _rate_limit, availability, current_engine, step_running, submit
from app.pricing.quote import bound_quote, fixed_price, proposal_usd, with_margin
from app.proposals import decisions, evidence, rulebook, sampling
from app.proposals import export as proposal_export
from app.proposals.models import (
    ChapterDocument,
    CitationStyle,
    EvidenceItem,
    Project,
    ProjectView,
    ProposalInputs,
    ProposalPlan,
    SampleSize,
    StepInput,
    StoredChapterState,
    TitlePage,
)
from app.proposals.pipeline import INPUT, load_library
from app.runtime import Runtime

logger = logging.getLogger("paperaid.proposals")
Step = Literal["PLAN", "CHAPTER_1", "CHAPTER_2", "CHAPTER_3"]


def _valid_id(project_id: str) -> bool:
    return project_id.startswith("prj_") and project_id[4:].isalnum() and len(project_id) <= 40


def _owned(rt: Runtime, user: User, project_id: str) -> Project:
    project = rt.store.get_project(project_id) if _valid_id(project_id) else None
    if project is None or project.owner_uid != user.uid or project.deleting:
        raise NotFound("We couldn't find this proposal.")
    return project


def _require_ai(rt: Runtime, user: User) -> None:
    if availability(rt.settings, user).get("PROPOSAL") != "available":
        raise AppError("Proposal projects are not available on your account yet.", code="SERVICE_UNAVAILABLE")


def _renew(rt: Runtime, p: Project) -> Project:
    now = utcnow()
    p.updated_at, p.expires_at = now, now + timedelta(days=rt.settings.retention_days)
    return p


def _change(rt: Runtime, user: User, project_id: str, mutate, conflict: str = "This proposal changed meanwhile. Reload it and try again.") -> Project:
    """Apply an owner action atomically, renewing the expiry."""
    _owned(rt, user, project_id)
    refusal: list[AppError] = []

    def apply(p: Project) -> Project | None:
        if p.deleting or p.owner_uid != user.uid:
            return None
        try:
            result = mutate(p)
        except AppError as exc:  # a rule broken against the current record: report it after the transaction
            refusal.append(exc)
            return None
        return _renew(rt, result) if result is not None else None

    updated = rt.store.update_project(project_id, apply)
    if refusal:
        raise refusal[0]
    if updated is None:
        raise Conflict(conflict, code="PROJECT_CHANGED")
    return updated


# --- the student's views -------------------------------------------------------------------------


def _chapter_doc(rt: Runtime, state_: StoredChapterState, version: int | None = None) -> ChapterDocument | None:
    number = version or state_.current
    entry = next((v for v in state_.versions if v.version == number), None)
    if entry is None or not rt.files.exists(entry.path):
        return None
    return ChapterDocument.model_validate_json(rt.files.get(entry.path))


def view(rt: Runtime, p: Project) -> ProjectView:
    """The browser's view, with what is computed from the current plan: what blocks approval and
    which written sections were built on decisions that have since changed."""
    out = p.view()
    if p.plan is not None:
        out.plan_problems = rulebook.plan_problems(p.rulebook, p.plan)
        for chapter, stored in zip(out.chapters, p.chapters, strict=True):
            doc = _chapter_doc(rt, stored) if stored.current else None
            if doc is None:
                continue
            written = {s.key for s in doc.sections}
            expected = rulebook.sections(p.rulebook, stored.number, p.inputs.level, p.plan)
            missing = [f"{s.number} {s.heading} (not written yet)" for s in expected if s.key not in written]
            chapter.needs_review = decisions.stale(doc, p.plan) + missing
    out.active_job = p.active_job if step_running(rt, p) else None
    return out


def create(rt: Runtime, user: User, inputs: ProposalInputs, title_page: TitlePage, citation: CitationStyle) -> ProjectView:
    if not user.verified:
        raise Forbidden("Verify your email address before starting a proposal.", code="EMAIL_NOT_VERIFIED")
    _require_ai(rt, user)
    _rate_limit(rt, user, "project", rt.settings.quotes_per_hour)
    now = utcnow()
    project = Project(
        id=f"prj_{secrets.token_hex(6)}",
        owner_uid=user.uid,
        owner_email=user.email,
        rulebook=rulebook.DEFAULT,
        citation=citation,
        inputs=inputs,
        title_page=title_page,
        chapters=[StoredChapterState(number=n) for n in (1, 2, 3)],
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=rt.settings.retention_days),
    )
    if not rt.store.create_project_if_open(project):
        raise Conflict(ACCOUNT_CLOSING, code="ACCOUNT_CLOSING")
    log(logger, logging.INFO, "project created", projectId=project.id)
    return view(rt, project)


def list_mine(rt: Runtime, user: User) -> list[ProjectView]:
    return [view(rt, p) for p in rt.store.list_projects(user.uid) if not p.deleting]


def get(rt: Runtime, user: User, project_id: str) -> ProjectView:
    return view(rt, _owned(rt, user, project_id))


def update_details(rt: Runtime, user: User, project_id: str, inputs: ProposalInputs, title_page: TitlePage, citation: CitationStyle) -> ProjectView:
    """Study details, title page and citation style. The details feed the next plan; changing
    them never alters a plan or chapter already written."""

    def apply(p: Project) -> Project:
        p.inputs, p.title_page, p.citation = inputs, title_page, citation
        return p

    return view(rt, _change(rt, user, project_id, apply))


def save_plan(rt: Runtime, user: User, project_id: str, plan: ProposalPlan, base_version: int) -> ProjectView:
    """The student's edit of the plan. It must start from the current version; it needs approving
    again, and sections written from changed decisions show "needs review"."""

    def apply(p: Project) -> Project:
        if p.plan_version != base_version:
            raise Conflict("Your plan was changed elsewhere (another tab or a finished step). Reload it to see the latest version.", code="PLAN_CHANGED")
        if p.plan is not None and not decisions.changed(p.plan, plan) and plan.questions_for_student == p.plan.questions_for_student:
            return p  # nothing changed: keep the approval
        p.plan, p.plan_status, p.plan_version = plan, "DRAFT", p.plan_version + 1
        return p

    return view(rt, _change(rt, user, project_id, apply))


def approve_plan(rt: Runtime, user: User, project_id: str, base_version: int) -> ProjectView:
    def apply(p: Project) -> Project:
        if p.plan is None:
            raise AppError("Create a plan first.", code="NO_PLAN")
        if p.plan_version != base_version:
            raise Conflict("Your plan changed since you opened it. Review the latest version before approving it.", code="PLAN_CHANGED")
        problems = rulebook.plan_problems(p.rulebook, p.plan)
        if problems:
            raise AppError("Fix the plan before approving it: " + " ".join(problems), code="PLAN_INCOMPLETE")
        p.plan_status = "APPROVED"
        return p

    approved = _change(rt, user, project_id, apply)
    if not approved.auto_chapter_one:
        return view(rt, approved)
    return _start_chapter_one(rt, user, approved)


def _start_chapter_one(rt: Runtime, user: User, project: Project) -> ProjectView:
    """Start Chapter One right after the plan is approved, as agreed when the plan was started.
    Tried once: if it cannot start (not enough tokens, a figure only the student can give), the
    student sees why and starts it themselves."""

    def done(q: Project) -> Project:
        q.auto_chapter_one = False
        return q

    rt.store.update_project(project.id, done)
    notice = None
    try:
        quoted = quote_step(rt, user, project.id, "CHAPTER_1", "")
        submit_step(rt, user, project.id, quoted.job.id, quoted.quote.id)
    except AppError as exc:
        notice = f"Chapter One could not start automatically: {exc.message}"
    current = _owned(rt, user, project.id)
    out = view(rt, current)
    out.notice = notice
    return out


def take_candidate(rt: Runtime, user: User, project_id: str, accept: bool) -> ProjectView:
    """Use or discard a plan PaperAid produced while the student was editing theirs."""

    def apply(p: Project) -> Project:
        if p.candidate_plan is None:
            return p
        if accept:
            p.plan, p.plan_status, p.plan_version = p.candidate_plan, "DRAFT", p.plan_version + 1
        p.candidate_plan = None
        return p

    return view(rt, _change(rt, user, project_id, apply))


def set_chapter(rt: Runtime, user: User, project_id: str, number: int, version: int, approved: bool) -> ProjectView:
    """Show (and export) an earlier version, or approve the current one."""

    def apply(p: Project) -> Project:
        chapter = p.chapter(number)
        if not any(v.version == version for v in chapter.versions):
            raise NotFound("That version doesn't exist.")
        chapter.current, chapter.approved = version, approved
        return p

    if number not in (1, 2, 3):
        raise NotFound("That chapter doesn't exist.")
    return view(rt, _change(rt, user, project_id, apply))


class RenderedSection(BaseModel):
    number: str
    heading: str
    paragraphs: list[str]
    table: list[list[str]] | None = None
    table_caption: str = ""
    needs_review: bool = False


class ChapterView(BaseModel):
    number: int
    title: str
    version: int
    plan_version: int
    sections: list[RenderedSection]
    readiness: list[ReadinessItem]
    warnings: list[str]
    words: int
    references: list[str]


def _citer(rt: Runtime, p: Project) -> evidence.Citer:
    return evidence.Citer(load_library(rt.files, p.evidence_files), p.citation)


def _render(doc: ChapterDocument, citer: evidence.Citer, plan: ProposalPlan | None) -> list[RenderedSection]:
    stale = set(decisions.stale(doc, plan)) if plan else set()
    return [
        RenderedSection(
            number=s.number, heading=s.heading, paragraphs=[citer.render(par) for par in s.paragraphs],
            table=[[citer.render(cell) for cell in row] for row in s.table] if s.table else None,
            table_caption=citer.render(s.table_caption), needs_review=f"{s.number} {s.heading}" in stale,
        )
        for s in doc.sections
    ]


def chapter(rt: Runtime, user: User, project_id: str, number: int, version: int | None = None) -> ChapterView:
    p = _owned(rt, user, project_id)
    if number not in (1, 2, 3):
        raise NotFound("That chapter doesn't exist.")
    stored = p.chapter(number)
    doc = _chapter_doc(rt, stored, version)
    if doc is None:
        raise NotFound("This chapter hasn't been written yet.")
    citer = _citer(rt, p)
    for earlier in (1, 2):  # APA 6 names three to five authors in full at their first citation in the proposal
        if earlier < number and (prior := _chapter_doc(rt, p.chapter(earlier))):
            _render(prior, citer, None)
    sources = [citer.library[i].source for i in doc.cited if i in citer.library]
    return ChapterView(
        number=number, title=doc.title, version=version or stored.current, plan_version=doc.plan_version, sections=_render(doc, citer, p.plan),
        readiness=doc.readiness, warnings=doc.warnings, words=doc.words,
        references=evidence.reference_list(sources, p.citation),
    )


def export_docx(rt: Runtime, user: User, project_id: str, final: bool) -> tuple[bytes, str]:
    """The proposal in the UCU layout. A draft leaves out what is missing; a final export first
    requires every blocker resolved. Downloading counts as the student's action (renews expiry)."""
    p = _owned(rt, user, project_id)
    chapters = {n: doc for n in (1, 2, 3) if (doc := _chapter_doc(rt, p.chapter(n))) is not None}
    if not chapters:
        raise AppError("Write at least one chapter before downloading the proposal.", code="NOTHING_TO_EXPORT")
    if final:
        blockers = proposal_export.final_blockers(p, chapters)
        if blockers:
            raise AppError("Before the complete proposal can be downloaded: " + " ".join(blockers), code="NOT_READY")
    data = proposal_export.build(p, chapters, load_library(rt.files, p.evidence_files), draft=not final)
    _change(rt, user, project_id, lambda q: q)
    title = (p.plan.title if p.plan else p.inputs.topic)[:80]
    safe = "".join(c for c in title if c.isalnum() or c in " -_").strip() or "Proposal"
    return data, f"{safe}{'' if final else ' – draft'}.docx"


def library(rt: Runtime, user: User, project_id: str) -> list[EvidenceItem]:
    p = _owned(rt, user, project_id)
    return sorted(load_library(rt.files, p.evidence_files).values(), key=lambda i: (not i.usable, i.chapter, i.source.title.lower()))


# --- steps ------------------------------------------------------------------------------------


class StepQuote(BaseModel):
    job: JobView
    quote: Quote
    blockers: list[str] = []
    # The plan's price is shown with Chapter One, which starts automatically when the plan is
    # approved (owner request 2026-09-28): its own quote is issued then, from the approved plan.
    then: list[QuoteLine] = []


def chapter_one_estimate(settings, level: str) -> QuoteLine:
    """What Chapter One can cost for this level, shown with the plan before any plan exists."""
    if settings.pricing_mode == "fixed":
        return QuoteLine(label="Chapter 1, started when you approve the plan", amount=fixed_price(settings, "CHAPTER_1", None), service="CHAPTER_1")
    words = round(rulebook.target_words(rulebook.DEFAULT, level) * rulebook.chapter_spec(rulebook.DEFAULT, 1)["share"])
    return QuoteLine(label="Chapter 1, started when you approve the plan (up to)", amount=with_margin(proposal_usd(settings, "CHAPTER_1", words), settings), service="CHAPTER_1")


def quote_step(rt: Runtime, user: User, project_id: str, step: Step, note: str) -> StepQuote:
    """Freeze the project's input for a step, price it and return the quote. Nothing is held until
    the student submits."""
    _require_ai(rt, user)
    p = _owned(rt, user, project_id)
    if step_running(rt, p):
        raise Conflict("A step is already running for this proposal. Wait for it to finish.", code="STEP_RUNNING")
    note = note.strip()[:1000]
    chapter = 0 if step == "PLAN" else int(step[-1])
    if chapter:
        if p.plan is None or p.plan_status != "APPROVED":
            raise AppError("Approve your plan before writing chapters.", code="PLAN_NOT_APPROVED")
        blockers = rulebook.chapter_blockers(p.plan, chapter)
        if blockers:
            raise AppError(" ".join(blockers), code="AUTHOR_INPUT_NEEDED")
    _rate_limit(rt, user, "quote", rt.settings.quotes_per_hour)
    inp = StepInput(
        project_id=p.id,
        step="PLAN" if chapter == 0 else "CHAPTER",
        chapter=chapter,
        note=note,
        rulebook=p.rulebook,
        inputs=p.inputs,
        plan=p.plan if chapter else None,
        plan_version=p.plan_version,
        evidence_files=list(p.evidence_files),
        chapters={c.number: next(v.path for v in c.versions if v.version == c.current) for c in p.chapters if c.current and c.number != chapter},
        private=[w for w in " ".join([p.title_page.student_name, p.title_page.reg_number, p.title_page.supervisor]).split() if len(w) > 2],
    )
    data = inp.model_dump_json(by_alias=True).encode()
    sha = hashlib.sha256(data).hexdigest()
    now = utcnow()
    words = 0
    if chapter:
        assert p.plan is not None
        words = sum(s.words for s in rulebook.sections(p.rulebook, chapter, p.inputs.level, p.plan))
    selection = ServiceSelection(proposal=step)
    job = Job(
        id=f"job_{secrets.token_hex(6)}",
        status=JobStatus.DRAFT,
        owner_uid=user.uid,
        owner_email=user.email,
        project_id=p.id,
        input_sha256=sha,
        selection=selection,
        created_at=now,
        expires_at=now + timedelta(days=rt.settings.retention_days),
        events=[JobEvent(at=now, label=f"{'Plan' if chapter == 0 else f'Chapter {chapter}'} step priced for proposal {p.id}")],
    )
    rt.files.put(f"{job.storage_prefix()}/internal/{INPUT}", data, "application/json")
    job.quote = bound_quote(rt.settings, selection, sha, words, current_engine(rt.settings))
    state.transition(job, JobStatus.QUOTED, "Quote issued")
    if not rt.store.create_if_open(job):
        rt.files.delete_prefix(job.storage_prefix())
        raise Conflict(ACCOUNT_CLOSING, code="ACCOUNT_CLOSING")
    current = rt.store.get_project(p.id)
    if current is None or current.deleting:  # deleted while this step was being priced: leave nothing behind
        rt.files.delete_prefix(job.storage_prefix())
        rt.store.delete(job.id)
        raise NotFound("We couldn't find this proposal.")
    then = [chapter_one_estimate(rt.settings, p.inputs.level)] if chapter == 0 and not p.chapter(1).versions else []
    return StepQuote(job=job.view(), quote=Quote.model_validate(job.quote.model_dump()), then=then)


def submit_step(rt: Runtime, user: User, project_id: str, job_id: str, quote_id: str) -> JobView:
    """Accept a step's quote. The project is checked and claimed in the same transaction that
    holds the credits (Codex audit 2026-09-28 #4): still the student's, not being deleted, on the
    plan version the step was priced on, and with no other step claimed since it was looked at."""
    p = _owned(rt, user, project_id)
    job = rt.store.get(job_id)
    if job is None or job.owner_uid != user.uid or job.project_id != p.id:
        raise NotFound("We couldn't find this step.")
    inp = StepInput.model_validate_json(rt.files.get(f"{job.storage_prefix()}/internal/{INPUT}"))
    if job.status not in state.SUBMITTED:
        if p.plan_version != inp.plan_version:
            raise Conflict("Your plan changed after this step was priced. Price it again so it uses your latest plan.", code="QUOTE_MISMATCH")
        if p.active_job != job_id and step_running(rt, p):
            raise Conflict("A step is already running for this proposal. Wait for it to finish.", code="STEP_RUNNING")
    seen_active = p.active_job  # finished (or none): the claim may replace only this value

    def gate(j: Job, q: Project | None) -> Project | None:
        if q is None or q.deleting or q.owner_uid != j.owner_uid or q.plan_version != inp.plan_version:
            return None
        if q.active_job not in (seen_active, j.id):
            return None  # another step was claimed after we looked
        q.active_job = j.id
        q.jobs = q.jobs if j.id in q.jobs else (q.jobs + [j.id])[-100:]
        if inp.step == "PLAN" and not q.chapter(1).versions:
            q.auto_chapter_one = True  # agreed with the plan's price: starts when the plan is approved
        return _renew(rt, q)

    return submit(rt, user, job_id, quote_id, project_gate=gate)


# --- deletion -------------------------------------------------------------------------------------


def delete(rt: Runtime, user: User, project_id: str) -> None:
    """Delete a project, its chapters, versions and evidence. Refused while a step runs."""
    p = rt.store.get_project(project_id) if _valid_id(project_id) else None
    if p is None or p.owner_uid != user.uid:
        return  # already gone (or never the user's): idempotent, and reveals nothing
    if not _erase_project(rt, p) and rt.store.get_project(p.id) is not None:
        raise Conflict("A step is running for this proposal. Delete it when the step finishes.", code="STEP_RUNNING")
    log(logger, logging.INFO, "project deleted", projectId=project_id)



def sample_size_preview(sample: SampleSize) -> dict[str, object]:
    """What PaperAid will calculate from the student's figures, shown while they edit the plan."""
    result = sampling.calculate(sample)
    return {"size": result.size, "steps": result.steps, "missing": result.missing}

