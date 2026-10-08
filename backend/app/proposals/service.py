"""Proposal project rules. Like app.jobs.service, every function takes the runtime and the verified
user, so ownership, versions and state rules can be tested directly.

- Every change to the plan names the version it started from; a stale edit is refused, never
  silently merged (Codex review: two tabs must not overwrite each other).
- A step (the plan, a chapter) is an ordinary priced job linked to the project. Its input is frozen
  when it is priced and bound to the quote; submitting checks the plan has not changed since.
- One step runs at a time per project: the claim is taken on the project record before the quote is
  accepted, and a claim whose job is no longer queued or running is free again.
- Genuine actions renew the project's expiry (30 days); reading it does not."""

import difflib
import hashlib
import json
import logging
import secrets
import threading
from datetime import timedelta
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel

from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.logging import log
from app.documents.intake import inspect_upload
from app.formatting.guideline import MAX_GUIDE_WORDS
from app.jobs import state
from app.jobs.models import Job, JobEvent, JobStatus, JobView, Quote, QuoteLine, ReadinessItem, ServiceSelection, utcnow
from app.jobs.service import (
    ACCOUNT_CLOSING,
    User,
    _erase_project,
    _rate_limit,
    availability,
    priced_engine,
    require_terms,
    step_running,
    submit,
)
from app.latex.convert import convert as to_latex
from app.latex.package import compile_pdf
from app.latex.package import project as latex_project
from app.pricing.quote import bound_quote, fixed_price, proposal_usd, with_margin
from app.proposals import decisions, evidence, feedback, framework, profile, rulebook, sampling
from app.proposals import export as proposal_export
from app.proposals.models import (
    Acknowledgment,
    ChapterDocument,
    CitationStyle,
    EvidenceItem,
    FeedbackComment,
    FeedbackStatus,
    GuideFile,
    PlanReview,
    Project,
    ProjectView,
    ProposalInputs,
    ProposalPlan,
    SampleSize,
    StepInput,
    StoredChapterState,
    TitlePage,
    WrittenSection,
    moved_path,
)
from app.proposals.pipeline import INPUT, _confirmed_gap, load_library
from app.proposals.structure import guide_read as _guide_read
from app.proposals.structure import structure_current as _structure_current
from app.runtime import Runtime

logger = logging.getLogger("paperaid.proposals")
Step = Literal["PLAN", "CHAPTER_1", "CHAPTER_2", "CHAPTER_3", "CONCEPT", "REVISE_1", "REVISE_2", "REVISE_3", "REVISE_4", "COMPLETE_1", "COMPLETE_2", "COMPLETE_3", "COMPLETE_4", "PROFILE"]
CONCEPT = 4  # the concept paper is stored like a chapter, as number 4
PDF_SLOTS = threading.BoundedSemaphore(2)  # PDF compilations at once on one API instance (Codex audit 56c4f83 M27)


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
    if entry is None:
        return None
    path = entry.path if rt.files.exists(entry.path) else moved_path(entry.path)
    if not rt.files.exists(path):
        return None
    return ChapterDocument.model_validate_json(rt.files.get(path))


def plan_problems(p: Project) -> list[str]:
    """What blocks the plan's approval, under the project's guide, level and the student's choice of four objectives."""
    assert p.plan is not None
    return rulebook.plan_problems(p.rulebook, p.plan, p.inputs.level, p.inputs.four_objectives, p.goal == "CONCEPT")


def view(rt: Runtime, p: Project) -> ProjectView:
    """The browser's view, with what is computed from the current plan: what blocks approval and
    which written sections were built on decisions that have since changed."""
    out = p.view()
    docs = {c.number: doc for c in p.chapters if c.current and (doc := _chapter_doc(rt, c)) is not None}
    out.written = [WrittenSection(chapter=n, key=s.key, number=s.number, heading=s.heading) for n, doc in sorted(docs.items()) if n != CONCEPT for s in doc.sections]
    out.guide_name = p.guide.name if p.guide else None
    try:
        book = rulebook.load(p.rulebook)
    except AppError as exc:
        if exc.code != "PROFILE_MISSING":
            raise
        out.institution_notes, out.blockers, out.profile_missing = [rulebook.PROFILE_MISSING], [rulebook.PROFILE_MISSING], True
        out.active_job = p.active_job if step_running(rt, p) else None
        return out
    out.blockers = proposal_export.final_blockers(p, docs)
    out.institution = book["institution"] if book.get("custom") else "Standard guide"  # the default is "the standard guide" (owner decision 2026-10-04)
    out.guide_questions = open_guide_questions(p, book)
    out.institution_notes = list(book.get("unclear", []))
    out.guide_name = p.guide.name if p.guide else None
    out.guide_read = p.guide is not None and book.get("guide_sha256") == p.guide.sha256
    if p.plan is not None:
        out.plan_problems = plan_problems(p)
        for chapter in out.chapters:
            doc = docs.get(chapter.number)
            if doc is None:
                continue
            written = {s.key for s in doc.sections}
            expected = rulebook.sections(p.rulebook, chapter.number, p.inputs.level, p.plan)
            missing = [f"{s.number} {s.heading} (not written yet)" for s in expected if s.key not in written]
            chapter.needs_review = decisions.stale(doc, p.plan) + missing
    out.active_job = p.active_job if step_running(rt, p) else None
    out.framework = framework.describe(p.plan.variables) if p.plan else ""
    first = CONCEPT if p.goal == "CONCEPT" else 1
    if p.auto and not p.chapter(first).versions and out.active_job is None and not p.auto_failure and p.jobs:
        last = rt.store.get(p.jobs[-1])
        if last is not None and last.status == JobStatus.FAILED and last.failure is not None:
            out.auto_failure = last.failure.user_message
        elif last is not None and last.status == JobStatus.CANCELLED:
            out.auto_failure = "Stopped at your request. Nothing was delivered and you were not charged."
    return out


def create(rt: Runtime, user: User, inputs: ProposalInputs, title_page: TitlePage, citation: CitationStyle, goal: Literal["FULL", "CONCEPT"] = "FULL") -> ProjectView:
    if not user.verified:
        raise Forbidden("Verify your email address before starting a proposal.", code="EMAIL_NOT_VERIFIED")
    _require_ai(rt, user)
    _rate_limit(rt, user, "project", rt.settings.quotes_per_hour)
    now = utcnow()
    if title_page.institution is None:  # a new project prints only the institution the student gives
        title_page = title_page.model_copy(update={"institution": ""})
    project = Project(
        id=f"prj_{secrets.token_hex(6)}",
        owner_uid=user.uid,
        owner_email=user.email,
        rulebook=rulebook.DEFAULT,
        citation=citation,
        inputs=inputs,
        title_page=title_page,
        goal=goal,
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


def open_guide_questions(p: Project, book: dict) -> list[dict[str, str]]:
    """The points where the student's guide departs a lot from the standard guide, not yet answered."""
    if not book.get("custom"):
        return []
    return [d for d in book.get("departures", []) if d["id"] not in p.guide_answers]


def answer_guide(rt: Runtime, user: User, project_id: str, departure_id: str, answer: Literal["KEEP", "STANDARD"]) -> ProjectView:
    """The student confirms a point where their guide departs from the standard guide, or takes the
    standard guide's version of it (a new profile: saved profiles never change)."""
    p = _owned(rt, user, project_id)
    book = rulebook.load(p.rulebook)
    if departure_id not in {d["id"] for d in open_guide_questions(p, book)}:
        raise Conflict("That question was already answered. Reload to see the latest.", code="ALREADY_ANSWERED")
    new_id = ""
    if answer == "STANDARD":
        if any(c.versions for c in p.chapters):
            raise Conflict("Chapters are already written to your guide's structure, so it can't change now.", code="CHAPTERS_WRITTEN")
        new = profile.with_standard(book, departure_id)
        rt.files.put(rulebook.stored_path(new["id"]), json.dumps(new).encode(), "application/json")
        new_id = new["id"]

    def apply(q: Project) -> Project:
        if q.rulebook != book["id"] or step_running(rt, q):
            raise Conflict("Your proposal changed meanwhile. Reload it and answer again.", code="PROJECT_CHANGED")
        q.guide_answers[departure_id] = {"answer": answer, "at": utcnow().isoformat()}
        if new_id:
            q.rulebook = new_id
            q.profiles = list(dict.fromkeys([*q.profiles, new_id]))
        return q

    return view(rt, _change(rt, user, project_id, apply))


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

    plan = _confirmed_gap(plan, {i for i, item in load_library(rt.files, _owned(rt, user, project_id).evidence_files).items() if item.usable})

    def apply(p: Project) -> Project:
        if p.plan_version != base_version:
            raise Conflict("Your plan was changed elsewhere (another tab or a finished step). Reload it to see the latest version.", code="PLAN_CHANGED")
        # Standard sampling settings PaperAid assumed stay to be acknowledged until the student sets
        # those settings themselves (never cleared by what the browser sends).
        assumed = p.plan.sampling_assumed if p.plan is not None else []
        if p.plan is not None and assumed:
            before, after = p.plan.sample_size, plan.sample_size
            if (before.margin, before.proportion, before.confidence) != (after.margin, after.proportion, after.confidence):
                assumed = []
        edited = plan.model_copy(update={"sampling_assumed": assumed})
        if p.plan is not None and not decisions.changed(p.plan, edited) and edited.questions_for_student == p.plan.questions_for_student:
            return p  # nothing changed: keep the approval
        p.plan, p.plan_status, p.plan_version = edited, "DRAFT", p.plan_version + 1
        if p.plan_review is not None:  # PaperAid reviewed the earlier version, not this one (Codex audit 2026-10-01)
            earlier = p.plan_review.objections if p.plan_review.outcome != "APPROVED" else []
            p.plan_review = PlanReview(outcome="NOT_REVIEWED", reason="EDITED", plan_version=p.plan_version,
                                       objections=[EDITED_NOTE, *[o for o in earlier if o != EDITED_NOTE]])
        return p

    return view(rt, _change(rt, user, project_id, apply))


EDITED_NOTE = "You changed this plan after PaperAid's final review, so PaperAid has not reviewed your version."


def needed_acknowledgments(p: Project) -> dict[str, str]:
    """What the student must explicitly acknowledge before approving the current plan, with the exact
    text: the final reviewer's remaining objections (or that its review could not complete), and
    standard sampling settings PaperAid assumed for a calculated sample (owner decision 2026-09-30)."""
    needed: dict[str, str] = {}
    if p.plan is None:
        return needed
    if p.plan_review is not None and p.plan_review.outcome != "APPROVED":
        needed["OBJECTIONS"] = "\n".join(p.plan_review.objections) or p.plan_review.outcome
    if p.plan.sampling_assumed:
        needed["SAMPLING"] = "; ".join(p.plan.sampling_assumed)
    return needed


def approve_plan(rt: Runtime, user: User, project_id: str, base_version: int, acknowledge: list[str] | None = None) -> ProjectView:
    given = set(acknowledge or [])

    def apply(p: Project) -> Project:
        if p.plan is None:
            raise AppError("Create a plan first.", code="NO_PLAN")
        if p.plan_version != base_version:
            raise Conflict("Your plan changed since you opened it. Review the latest version before approving it.", code="PLAN_CHANGED")
        problems = plan_problems(p)
        if problems:
            raise AppError("Fix the plan before approving it: " + " ".join(problems), code="PLAN_INCOMPLETE")
        needed = needed_acknowledgments(p)
        missing = [k for k in needed if k not in given]
        if missing:
            reasons = {"OBJECTIONS": "PaperAid's reviewer did not approve this plan: confirm you have checked its objections",
                       "SAMPLING": "confirm the sample size settings PaperAid assumed"}
            raise AppError("Before approving: " + "; ".join(reasons[k] for k in missing) + ".", code="ACKNOWLEDGMENT_NEEDED")
        for kind, text in needed.items():
            p.acknowledgments.append(Acknowledgment(kind=kind, plan_version=p.plan_version, text_sha256=hashlib.sha256(text.encode()).hexdigest()))  # type: ignore[arg-type]
        p.acknowledgments = p.acknowledgments[-50:]
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


def continue_to_full(rt: Runtime, user: User, project_id: str) -> ProjectView:
    """A concept-note project becomes a full proposal, keeping its plan, evidence and concept paper.
    Nothing starts by itself: the student prices Chapter One when ready."""

    def apply(p: Project) -> Project:
        p.goal = "FULL"
        return p

    return view(rt, _change(rt, user, project_id, apply))


def take_candidate(rt: Runtime, user: User, project_id: str, accept: bool) -> ProjectView:
    """Use or discard a plan PaperAid produced while the student was editing theirs."""

    def apply(p: Project) -> Project:
        if p.candidate_plan is None:
            return p
        if accept:
            p.plan, p.plan_status, p.plan_version = p.candidate_plan, "DRAFT", p.plan_version + 1
            p.plan_review = p.candidate_review.model_copy(update={"plan_version": p.plan_version}) if p.candidate_review else None
        p.candidate_plan, p.candidate_review = None, None
        return p

    return view(rt, _change(rt, user, project_id, apply))


def set_chapter(rt: Runtime, user: User, project_id: str, number: int, version: int, approved: bool) -> ProjectView:
    """Show (and export) an earlier version, or approve the current one."""

    if approved:  # a chapter with sections still to write is a workspace draft, not a chapter to approve
        chosen = next((v for v in _owned(rt, user, project_id).chapter(number).versions if v.version == version), None)
        doc = ChapterDocument.model_validate_json(rt.files.get(chosen.path if rt.files.exists(chosen.path) else moved_path(chosen.path))) if chosen else None
        if doc is not None and doc.missing:
            raise AppError("Finish this chapter before approving it: some sections are not written yet.", code="CHAPTER_INCOMPLETE")

    def apply(p: Project) -> Project:
        chapter = p.chapter(number)
        if not any(v.version == version for v in chapter.versions):
            raise NotFound("That version doesn't exist.")
        chapter.current, chapter.approved = version, approved
        return p

    if number not in (1, 2, 3, CONCEPT):
        raise NotFound("That chapter doesn't exist.")
    return view(rt, _change(rt, user, project_id, apply))


class RenderedSection(BaseModel):
    key: str
    number: str
    heading: str
    paragraphs: list[str]
    table: list[list[str]] | None = None
    table_caption: str = ""
    needs_review: bool = False


class FrameworkColumn(BaseModel):
    label: str
    items: list[str]


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
    framework: list[FrameworkColumn] = []  # Chapter One's conceptual framework figure, from the plan
    missing: list[str] = []  # sections not written yet ("1.3 Heading"): Finish chapter writes them


def _citer(rt: Runtime, p: Project) -> evidence.Citer:
    return evidence.Citer(load_library(rt.files, p.evidence_files), p.citation)


def _render(doc: ChapterDocument, citer: evidence.Citer, plan: ProposalPlan | None) -> list[RenderedSection]:
    stale = set(decisions.stale(doc, plan)) if plan else set()
    return [
        RenderedSection(
            key=s.key, number=s.number, heading=s.heading, paragraphs=[citer.render(par) for par in s.paragraphs],
            table=[[citer.render(cell) for cell in row] for row in s.table] if s.table else None,
            table_caption=citer.render(s.table_caption), needs_review=f"{s.number} {s.heading}" in stale,
        )
        for s in doc.sections
    ]


def chapter(rt: Runtime, user: User, project_id: str, number: int, version: int | None = None) -> ChapterView:
    p = _owned(rt, user, project_id)
    if number not in (1, 2, 3, CONCEPT):
        raise NotFound("That chapter doesn't exist.")
    stored = p.chapter(number)
    doc = _chapter_doc(rt, stored, version)
    if doc is None:
        raise NotFound("This chapter hasn't been written yet.")
    citer = _citer(rt, p)
    for earlier in (1, 2):  # APA 6 names three to five authors in full at their first citation in the proposal
        if earlier < number != CONCEPT and (prior := _chapter_doc(rt, p.chapter(earlier))):
            _render(prior, citer, None)
    sources = [citer.library[i].source for i in doc.cited if i in citer.library]
    return ChapterView(
        number=number, title=doc.title, version=version or stored.current, plan_version=doc.plan_version, sections=_render(doc, citer, p.plan),
        readiness=doc.readiness, warnings=doc.warnings, words=doc.words,
        references=evidence.reference_list(sources, p.citation),
        framework=[FrameworkColumn(label=label, items=items) for label, items in proposal_export.framework_columns(p.plan)]
        if number in (1, CONCEPT) and any(s.key == "framework" for s in doc.sections) else [],
        missing=[f"{s.number} {s.heading}" for s in rulebook.sections(p.rulebook, number, p.inputs.level, p.plan) if s.key in doc.missing] if p.plan and doc.missing else [],
    )


def export_docx(rt: Runtime, user: User, project_id: str, final: bool) -> tuple[bytes, str]:
    """The proposal in the UCU layout. A draft leaves out what is missing; a final export first
    requires every blocker resolved. Downloading counts as the student's action (renews expiry)."""
    return _export(rt, user, _owned(rt, user, project_id), final)


def _export(rt: Runtime, user: User, p: Project, final: bool) -> tuple[bytes, str]:
    project_id = p.id
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


def export_pdf(rt: Runtime, user: User, project_id: str, final: bool) -> tuple[bytes, str]:
    """The same proposal as a PDF for reading and sharing: the Word export converted to LaTeX and
    compiled offline (no AI). Word stays the file to submit, in the institution's layout."""
    p = _owned(rt, user, project_id)
    data, name = _export(rt, user, p, final)  # one snapshot for the document and its cache key (Codex re-check M27)
    converted = to_latex(data)
    if converted.omitted and final:
        raise AppError(
            f"{converted.omitted} part{'s' if converted.omitted != 1 else ''} of your proposal could not be converted to PDF. Download the Word file instead.",
            code="PDF_INCOMPLETE",
        )
    pdf_name = name.removesuffix(".docx") + (" (PDF, incomplete).pdf" if converted.omitted else ".pdf")
    # The same content always gives the same PDF: kept beside the project, keyed by what the document
    # is built from (the Word file itself carries its creation time), so a repeat costs nothing (M27).
    built_from = [
        final, p.plan_version, p.citation, p.rulebook, p.inputs.model_dump(mode="json"), p.title_page.model_dump(mode="json"),
        [(c.number, c.current) for c in p.chapters], p.evidence_files, utcnow().date().isoformat(),
    ]
    cached = f"{p.storage_prefix()}/pdf/{hashlib.sha256(json.dumps(built_from).encode()).hexdigest()[:24]}.pdf"
    if rt.files.exists(cached):
        return rt.files.get(cached), pdf_name
    _rate_limit(rt, user, "pdf", rt.settings.uploads_per_hour)
    if not PDF_SLOTS.acquire(blocking=False):  # compilers are bounded per instance
        raise AppError("PaperAid is making other PDFs right now. Try again in a minute, or download the Word file.", code="PDF_BUSY", status=503)
    try:
        pdf, problem = compile_pdf(converted)
    finally:
        PDF_SLOTS.release()
    if pdf is None:
        log(logger, logging.WARNING, "proposal pdf failed", projectId=project_id, problem=problem)
        raise AppError("The PDF could not be made this time. Download the Word file instead.", code="PDF_FAILED")
    rt.files.put(cached, pdf, "application/pdf")
    return pdf, pdf_name


def export_latex(rt: Runtime, user: User, project_id: str, final: bool) -> tuple[bytes, str]:
    """The proposal as a LaTeX project (owner decision 2026-09-29: LaTeX is a finishing choice, not
    a service of its own): the same Word export converted by code, no AI, nothing charged."""
    p = _owned(rt, user, project_id)
    data, name = _export(rt, user, p, final)
    _rate_limit(rt, user, "pdf", rt.settings.uploads_per_hour)
    archive, result = latex_project(data)
    if result.omitted:  # a complete proposal is never offered with content missing (Codex review #5)
        if final:
            raise AppError(
                f"{result.omitted} part{'s' if result.omitted != 1 else ''} of your proposal could not be converted to LaTeX. Download the Word file instead.",
                code="LATEX_INCOMPLETE",
            )
        return archive, name.removesuffix(".docx") + " (LaTeX, incomplete).zip"
    return archive, name.removesuffix(".docx") + " (LaTeX).zip"


def export_concept(rt: Runtime, user: User, project_id: str) -> tuple[bytes, str]:
    """The concept paper as its own Word file, with its annotated references."""
    p = _owned(rt, user, project_id)
    doc = _chapter_doc(rt, p.chapter(CONCEPT))
    if doc is None:
        raise AppError("Write the concept paper first.", code="NOTHING_TO_EXPORT")
    data = proposal_export.concept(p, doc, load_library(rt.files, p.evidence_files))
    _change(rt, user, project_id, lambda q: q)
    title = (p.plan.title if p.plan else p.inputs.topic)[:70]
    safe = "".join(c for c in title if c.isalnum() or c in " -_").strip() or "Proposal"
    return data, f"{safe} – concept paper.docx"


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


def quote_step(rt: Runtime, user: User, project_id: str, step: Step, note: str, comments: list[str] | None = None, bundled: bool = False) -> StepQuote:
    """Freeze the project's input for a step, price it and return the quote. Nothing is held until
    the student submits."""
    _require_ai(rt, user)
    p = _owned(rt, user, project_id)
    if step_running(rt, p):
        raise Conflict("A step is already running for this proposal. Wait for it to finish.", code="STEP_RUNNING")
    note = note.strip()[:1000]
    if step == "PROFILE":
        return _quote_profile(rt, user, p)
    if p.guide is not None and not any(c.versions for c in p.chapters) and not _guide_read(p):
        # the student decides which structure is written to: their guide, read, or the standard one
        raise AppError(GUIDE_UNREAD, code="GUIDE_UNREAD")
    chapter = 0 if step == "PLAN" else CONCEPT if step == "CONCEPT" else int(step[-1])
    revising = step.startswith("REVISE_")
    completing = step.startswith("COMPLETE_")
    base, revise, comment_ids, revised_words, base_version, base_sha = "", {}, [], 0, 0, ""
    only: list[str] = []
    remaining: int | None = None
    if completing:  # "Finish chapter": only the sections the current version is missing
        stored = p.chapter(chapter)
        doc = _chapter_doc(rt, stored)
        if doc is None or not doc.missing:
            raise AppError("Every section of this chapter is written.", code="NOTHING_TO_FINISH")
        if doc.plan_version != p.plan_version:
            raise AppError("Your plan changed after this draft was written. Write the chapter again so all of it follows your current plan.", code="PLAN_CHANGED")
        base = next(v.path for v in stored.versions if v.version == stored.current)
        base_version = stored.current
        base_sha = hashlib.sha256(rt.files.get(base if rt.files.exists(base) else moved_path(base))).hexdigest()
        only = list(doc.missing)
        remaining = max(0, doc.full_price - doc.paid) if doc.full_price else None
    if revising:
        stored = p.chapter(chapter)
        doc = _chapter_doc(rt, stored)
        if doc is None:
            raise AppError("Write this chapter before revising it.", code="NOTHING_TO_REVISE")
        base = next(v.path for v in stored.versions if v.version == stored.current)
        base_version = stored.current
        base_sha = hashlib.sha256(rt.files.get(base if rt.files.exists(base) else moved_path(base))).hexdigest()
        written = {s.key: s for s in doc.sections}
        # The student's own request is priced alone (Codex review #4); otherwise the open supervisor
        # comments on this chapter. An abandoned request never slips into a later price.
        wanted = set(comments or [])
        for comment in p.feedback:
            included = comment.id in wanted if wanted else comment.by == "SUPERVISOR"
            if included and comment.status == "OPEN" and comment.chapter == chapter:
                for key in comment.sections:
                    if key in written and len(revise.setdefault(key, [])) < 8:
                        from app.works.service import context_text  # the same storage for every service's context documents

                        context = context_text(rt, comment.context, comment.context_path)
                        revise[key].append(comment.text + (f" (The student added their document \"{comment.context_name}\" for context: {context})" if context else ""))
                        comment_ids.append(comment.id)
        revise = {k: v for k, v in revise.items() if v}
        if not revise:
            raise AppError(f"Place at least one open comment on a section of Chapter {chapter} first.", code="NO_FEEDBACK")
        revised_words = sum(len(evidence.ANY_TOKEN.sub(" ", par).split()) for k in revise for par in written[k].paragraphs)
    if chapter:
        if p.plan is None or p.plan_status != "APPROVED":
            raise AppError("Approve your plan before writing chapters.", code="PLAN_NOT_APPROVED")
        if p.goal == "CONCEPT" and chapter != CONCEPT:
            raise AppError("This is a concept note. Continue to the full proposal before writing chapters.", code="CONCEPT_ONLY")
        blockers = rulebook.chapter_blockers(p.plan, chapter)
        if blockers:
            raise AppError(" ".join(blockers), code="AUTHOR_INPUT_NEEDED")
    _rate_limit(rt, user, "quote", rt.settings.quotes_per_hour)
    inp = StepInput(
        project_id=p.id,
        chapter=chapter,
        note=note,
        rulebook=p.rulebook,
        guide_sha256=p.guide.sha256 if p.guide else "",
        inputs=p.inputs,
        goal=p.goal,
        plan=p.plan if chapter else None,
        plan_version=p.plan_version,
        evidence_files=list(p.evidence_files),
        # the other proposal chapters, for consistency checks (the concept paper is a separate document)
        chapters={c.number: next(v.path for v in c.versions if v.version == c.current) for c in p.chapters if c.current and c.number not in (chapter, CONCEPT) and chapter != CONCEPT},
        private=[w for w in " ".join([p.title_page.student_name, p.title_page.reg_number, p.title_page.supervisor]).split() if len(w) > 2],
        step="REVISE" if revising else "COMPLETE" if completing else "PLAN" if chapter == 0 else "CHAPTER",
        base=base,
        base_version=base_version,
        base_sha=base_sha,
        revise=revise,
        comment_ids=list(dict.fromkeys(comment_ids)),
        comment_signatures={c.id: c.signature() for c in p.feedback if c.id in set(comment_ids)},
        only=only,
    )
    data = inp.model_dump_json(by_alias=True).encode()
    sha = hashlib.sha256(data).hexdigest()
    now = utcnow()
    words, part = revised_words, 1.0
    if chapter and not revising:
        assert p.plan is not None
        planned = rulebook.sections(p.rulebook, chapter, p.inputs.level, p.plan)
        words = sum(s.words for s in planned)
        if completing:  # priced as the missing share of the chapter: with the first draft, never more than one chapter
            finish = sum(s.words for s in planned if s.key in only)
            part, words = (finish / words if words else 1.0), finish
    # a finish is its chapter's step with the finish flag: a record the released code can still read
    selection = (ServiceSelection(proposal="CONCEPT" if chapter == CONCEPT else f"CHAPTER_{chapter}", finish=True) if completing
                 else ServiceSelection(proposal=step, bundled=bundled and step in ("PLAN", "CHAPTER_1", "CONCEPT")))
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
        events=[JobEvent(at=now, label=f"{'Plan' if chapter == 0 else 'Concept paper' if chapter == CONCEPT else f'Chapter {chapter} revision' if revising else f'Chapter {chapter} finish' if completing else f'Chapter {chapter}'} step priced for proposal {p.id}")],
    )
    rt.files.put(f"{job.storage_prefix()}/internal/{INPUT}", data, "application/json")
    job.quote = bound_quote(rt.settings, selection, sha, words, priced_engine(rt.settings), part=part, cap=remaining)
    state.transition(job, JobStatus.QUOTED, "Quote issued")
    if not rt.store.create_if_open(job):
        rt.files.delete_prefix(job.storage_prefix())
        raise Conflict(ACCOUNT_CLOSING, code="ACCOUNT_CLOSING")
    current = rt.store.get_project(p.id)
    if current is None or current.deleting:  # deleted while this step was being priced: leave nothing behind
        rt.files.delete_prefix(job.storage_prefix())
        rt.store.delete(job.id)
        raise NotFound("We couldn't find this proposal.")
    then = [chapter_one_estimate(rt.settings, p.inputs.level)] if chapter == 0 and not p.chapter(1).versions and p.goal == "FULL" else []
    return StepQuote(job=job.view(), quote=Quote.model_validate(job.quote.model_dump()), then=then)


def _quote_profile(rt: Runtime, user: User, p: Project) -> StepQuote:
    """Price reading the student's guide into an institution profile. Only before any chapter is
    written: chapters follow one structure from start to finish."""
    if p.guide is None:
        raise AppError("Upload your institution's research guide first.", code="NO_GUIDE")
    if any(c.versions for c in p.chapters):
        raise AppError("Your chapters already follow the current structure. Start a new proposal to use your institution's guide.", code="CHAPTERS_WRITTEN")
    _rate_limit(rt, user, "quote", rt.settings.quotes_per_hour)
    inp = StepInput(
        project_id=p.id, step="PROFILE", chapter=0, rulebook=p.rulebook, inputs=p.inputs, plan_version=p.plan_version,
        guide=p.guide.path, guide_name=p.guide.name, guide_sha256=p.guide.sha256,
    )
    data = inp.model_dump_json(by_alias=True).encode()
    sha = hashlib.sha256(data).hexdigest()
    now = utcnow()
    selection = ServiceSelection(proposal="PROFILE")
    job = Job(
        id=f"job_{secrets.token_hex(6)}", status=JobStatus.DRAFT, owner_uid=user.uid, owner_email=user.email, project_id=p.id, input_sha256=sha,
        selection=selection, created_at=now, expires_at=now + timedelta(days=rt.settings.retention_days),
        events=[JobEvent(at=now, label=f"Institution profile step priced for proposal {p.id}")],
    )
    rt.files.put(f"{job.storage_prefix()}/internal/{INPUT}", data, "application/json")
    job.quote = bound_quote(rt.settings, selection, sha, 0, priced_engine(rt.settings), guide_words=p.guide.words)
    state.transition(job, JobStatus.QUOTED, "Quote issued")
    if not rt.store.create_if_open(job):
        rt.files.delete_prefix(job.storage_prefix())
        raise Conflict(ACCOUNT_CLOSING, code="ACCOUNT_CLOSING")
    return StepQuote(job=job.view(), quote=Quote.model_validate(job.quote.model_dump()))


def upload_guide(rt: Runtime, user: User, project_id: str, filename: str, data: bytes) -> ProjectView:
    """The institution's research guide (Word or PDF), kept as text for the profile step."""
    _require_ai(rt, user)
    p = _owned(rt, user, project_id)
    if step_running(rt, p):
        raise Conflict("A proposal step is running. Upload the guide after it finishes.", code="STEP_RUNNING")
    if any(c.versions for c in p.chapters):
        raise AppError("Your chapters already follow the current structure. Start a new proposal to use your institution's guide.", code="CHAPTERS_WRITTEN")
    _rate_limit(rt, user, "guide", rt.settings.uploads_per_hour)
    model = inspect_upload(data, filename, rt.settings.max_upload_bytes, MAX_GUIDE_WORDS, rt.settings.max_pdf_pages, min_words=300)
    text = "\n".join(b.text for b in model.blocks if b.text.strip())
    sha = hashlib.sha256(text.encode()).hexdigest()
    # A path of its own per attempt (a priced profile step may still read an earlier one), attached
    # in a transaction; if the project was deleted meanwhile the file is removed again, so a late
    # upload never leaves a private copy behind (Codex audit 56c4f83 H03).
    # Under users/: the bucket's 31-day rule removes any copy an interrupted upload leaves behind
    # (Codex re-check H03); a guide is needed only until it is read into a profile.
    path = f"users/{p.owner_uid}/guides/{p.id}/{sha[:16]}-{secrets.token_hex(4)}.txt"
    rt.files.put(path, text.encode("utf-8"), "text/plain")
    guide = GuideFile(name=PurePosixPath(filename).name[:120] or "guide", words=model.word_count, sha256=sha, path=path)

    def apply(q: Project) -> Project:
        if step_running(rt, q):
            raise Conflict("A proposal step is running. Upload the guide after it finishes.", code="STEP_RUNNING")
        if any(c.versions for c in q.chapters):
            raise AppError("Your chapters already follow the current structure. Start a new proposal to use your institution's guide.", code="CHAPTERS_WRITTEN")
        q.guide = guide
        return q

    attached: Project | None = None
    try:
        attached = _change(rt, user, project_id, apply)
    finally:
        if attached is None:  # refused or failed for any reason: the copy must not outlive the attempt
            rt.files.delete(path)
    return view(rt, attached)


def use_default_rulebook(rt: Runtime, user: User, project_id: str) -> ProjectView:
    """Go back to the standard structure (before any chapter is written). This is also the
    student's confirmation when their guide could not be used: the unread guide is removed, so
    writing can continue (Codex plan review 2026-09-29)."""
    removed: list[str] = []

    def apply(q: Project) -> Project:
        if step_running(rt, q):
            raise Conflict("A proposal step is running. Change the structure after it finishes.", code="STEP_RUNNING")
        # always allowed when the profile is gone: the proposal must stay usable (Codex audit 56c4f83 M17)
        if any(c.versions for c in q.chapters) and rulebook.available(q.rulebook):
            raise AppError("Your chapters already follow the current structure.", code="CHAPTERS_WRITTEN")
        q.rulebook = rulebook.DEFAULT
        if q.guide is not None and not any(c.versions for c in q.chapters):
            removed[:] = [q.guide.path]
            q.guide = None
        return q

    changed = _change(rt, user, project_id, apply)
    for path in removed:  # a priced profile step reading it fails with GUIDE_EXPIRED and is not charged
        rt.files.delete(path)
    return view(rt, changed)


GUIDE_UNREAD = "Your institution's guide is uploaded but not read yet. Read it, or choose the standard structure, before PaperAid writes your proposal."


def _revision_current(p: Project, inp: StepInput) -> bool:
    """A revision runs only on the version and comments it was priced for; finishing a chapter only on
    the version whose missing sections it was priced for (a second tab cannot buy it twice)."""
    if inp.step == "COMPLETE":
        return p.chapter(inp.chapter).current == inp.base_version
    if inp.step != "REVISE":
        return True
    comments = {c.id: c for c in p.feedback}
    return p.chapter(inp.chapter).current == inp.base_version and all(
        cid in comments and comments[cid].status == "OPEN" and comments[cid].signature() == sig for cid, sig in inp.comment_signatures.items()
    )


def submit_step(rt: Runtime, user: User, project_id: str, job_id: str, quote_id: str, start: bool = False, reservation: tuple[str, int] | None = None) -> JobView:
    """Accept a step's quote. The project is checked and claimed in the same transaction that
    holds the credits (Codex audit 2026-09-28 #4): still the student's, not being deleted, on the
    plan version the step was priced on, and with no other step claimed since it was looked at.
    `start` and `reservation`: one Start, in the same transaction (see app.works.service.submit_step)."""
    p = _owned(rt, user, project_id)
    job = rt.store.get(job_id)
    if job is None or job.owner_uid != user.uid or job.project_id != p.id:
        raise NotFound("We couldn't find this step.")
    inp = StepInput.model_validate_json(rt.files.get(f"{job.storage_prefix()}/internal/{INPUT}"))
    if job.status not in state.SUBMITTED:
        if p.plan_version != inp.plan_version:
            raise Conflict("Your plan changed after this step was priced. Price it again so it uses your latest plan.", code="QUOTE_MISMATCH")
        if not _revision_current(p, inp):
            raise Conflict("Your chapter or your supervisor's comments changed after this revision was priced. Price it again.", code="QUOTE_MISMATCH")
        if not _structure_current(p, inp):
            raise Conflict("Your institution's guide or proposal structure changed after this step was priced. Price it again.", code="QUOTE_MISMATCH")
        if p.active_job != job_id and step_running(rt, p):
            raise Conflict("A step is already running for this proposal. Wait for it to finish.", code="STEP_RUNNING")
    seen_active = p.active_job  # finished (or none): the claim may replace only this value

    def gate(j: Job, q: Project | None) -> Project | None:
        if q is None or q.deleting or q.owner_uid != j.owner_uid or q.plan_version != inp.plan_version:
            return None
        if q.active_job not in (seen_active, j.id):
            return None  # another step was claimed after we looked
        if not _revision_current(q, inp) or not _structure_current(q, inp):
            return None  # the chapter version, a comment, the guide or the structure changed after pricing
        q.active_job = j.id
        q.jobs = q.jobs if j.id in q.jobs else (q.jobs + [j.id])[-100:]
        if inp.step == "CHAPTER":
            q.auto_next = ""  # the plan's next step happens here, in the same transaction
        if inp.step == "PLAN" and not q.chapter(1).versions and q.goal == "FULL":
            q.auto_chapter_one = True  # agreed with the plan's price: starts when the plan is approved (never for a concept note)
        if start:
            q.auto, q.auto_failure = True, ""
        return _renew(rt, q)

    return submit(rt, user, job_id, quote_id, project_gate=gate, reservation=reservation)


# --- supervisor feedback (V2) -------------------------------------------------------------------


def _written(rt: Runtime, p: Project) -> list[feedback.Written]:
    out = []
    for stored in p.chapters:
        doc = _chapter_doc(rt, stored) if stored.current else None
        out += [feedback.Written(stored.number, s.key, s.number, s.heading) for s in doc.sections] if doc else []
    return out


def add_feedback(rt: Runtime, user: User, project_id: str, text: str, filename: str = "", data: bytes = b"") -> ProjectView:
    """A round of supervisor comments, pasted or from a file, each placed where code suggests."""
    p = _owned(rt, user, project_id)
    _rate_limit(rt, user, "feedback", rt.settings.uploads_per_hour)
    read = feedback.read_file(filename, data) if data else feedback.split(text)
    if not read:
        raise AppError("No comments were found. Paste them one per line or paragraph, or upload the marked-up file.", code="NO_FEEDBACK")
    written = _written(rt, p)

    def apply(q: Project) -> Project:
        if len(q.feedback) + len(read) > feedback.MAX_COMMENTS:
            raise AppError(f"A proposal keeps up to {feedback.MAX_COMMENTS} comments. Remove ones already dealt with first.", code="TOO_MANY_COMMENTS")
        round_ = max((c.round for c in q.feedback), default=0) + 1
        for r in read:
            chapter, sections = feedback.suggest(r, written)
            q.feedback.append(FeedbackComment(id=f"fb_{secrets.token_hex(4)}", round=round_, text=r.text, anchor=r.anchor, chapter=chapter, sections=sections))
        return q

    return view(rt, _change(rt, user, project_id, apply))


def update_feedback(
    rt: Runtime, user: User, project_id: str, comment_id: str, chapter: int | None, sections: list[str], status: FeedbackStatus, response: str
) -> ProjectView:
    """The student places a comment, marks it handled or declined, or writes their reply."""
    if chapter not in (None, 1, 2, 3, CONCEPT):
        raise NotFound("That chapter doesn't exist.")
    p = _owned(rt, user, project_id)
    keys = {w.key for w in _written(rt, p) if w.chapter == chapter}
    if any(k not in keys for k in sections):
        raise AppError("Choose sections that are in that chapter.", code="UNKNOWN_SECTION")

    def apply(q: Project) -> Project:
        comment = next((c for c in q.feedback if c.id == comment_id), None)
        if comment is None:
            raise NotFound("We couldn't find that comment.")
        if status == "APPLIED" and comment.status != "APPLIED":
            raise AppError("A comment is marked applied when a revision answers it.", code="NOT_APPLIED")
        comment.chapter, comment.status, comment.response = chapter, status, response.strip()[:1000]
        comment.sections = list(dict.fromkeys(sections))[:12] if chapter else []
        return q

    return view(rt, _change(rt, user, project_id, apply))


def request_changes(rt: Runtime, user: User, project_id: str, number: int, instruction: str, sections: list[str], context_name: str = "", context: str = "") -> ProjectView:
    """The student's own request for changes to a chapter or the concept paper, on the sections they
    chose (or all of them). It is revised like a supervisor comment; the price comes next."""
    if number not in (1, 2, 3, CONCEPT):
        raise NotFound("That chapter doesn't exist.")
    text = " ".join(instruction.split())[:1500]
    if len(text) < 3:
        raise AppError("Say what you would like changed.", code="NO_FEEDBACK")
    p = _owned(rt, user, project_id)
    _rate_limit(rt, user, "feedback", rt.settings.uploads_per_hour)
    written = [w for w in _written(rt, p) if w.chapter == number]
    keys = [w.key for w in written]
    if not keys:
        raise AppError("Write this chapter before asking for changes.", code="NOTHING_TO_REVISE")
    picked = [k for k in dict.fromkeys(sections) if k in set(keys)]
    chosen = picked or keys
    # Nothing picked: the whole chapter goes to the writer, and the sections the request names must all change.
    required = [] if picked else feedback.named(text, written)
    from app.works.service import save_context  # the same storage for every service's context documents

    comment_id = f"fb_{secrets.token_hex(4)}"
    path = save_context(rt, p.storage_prefix(), comment_id, context)

    def apply(q: Project) -> Project:
        if len(q.feedback) >= feedback.MAX_COMMENTS:
            raise AppError(f"A proposal keeps up to {feedback.MAX_COMMENTS} comments. Remove ones already dealt with first.", code="TOO_MANY_COMMENTS")
        round_ = max((c.round for c in q.feedback), default=0) + 1
        q.feedback.append(FeedbackComment(id=comment_id, round=round_, text=text, anchor="Your request", chapter=number, sections=chosen, by="STUDENT",
                                          required=required, context_name=context_name[:120] if path else "", context_path=path))
        return q

    saved: Project | None = None
    try:
        saved = _change(rt, user, project_id, apply)
    finally:
        if saved is None and path:
            rt.files.delete(path)
    return view(rt, saved)


def delete_feedback(rt: Runtime, user: User, project_id: str, comment_id: str) -> ProjectView:
    removed: list[str] = []

    def apply(q: Project) -> Project:
        removed[:] = [c.context_path for c in q.feedback if c.id == comment_id and c.context_path]
        q.feedback = [c for c in q.feedback if c.id != comment_id]
        return q

    changed = _change(rt, user, project_id, apply)
    for path in removed:
        rt.files.delete(path)
    return view(rt, changed)


def response_report(rt: Runtime, user: User, project_id: str) -> tuple[bytes, str]:
    """Every comment with where it applied and what was done, as a Word table."""
    p = _owned(rt, user, project_id)
    if not p.feedback:
        raise AppError("Add your supervisor's comments first.", code="NO_FEEDBACK")
    headings = {(w.chapter, w.key): f"{w.number} {w.heading}" for w in _written(rt, p)}
    default = {"DONE_BY_STUDENT": "Addressed.", "DECLINED": "Not changed.", "OPEN": "Not yet addressed."}
    rows = []
    for c in (c for c in p.feedback if c.by == "SUPERVISOR"):  # the student's own requests are not answers to the supervisor
        if c.chapter and c.sections:
            where = f"Chapter {c.chapter}: " + "; ".join(headings.get((c.chapter, k), k) for k in c.sections)
        else:
            where = f"Chapter {c.chapter}" if c.chapter else "The whole proposal"
        reply = c.response or default.get(c.status) or f"Revised in Chapter {c.chapter} (version {c.applied_in})."
        rows.append((c.text, where, reply))
    data = proposal_export.response_report(p, rows, draft=any(c.status == "OPEN" for c in p.feedback))
    _change(rt, user, project_id, lambda q: q)
    return data, "Response to supervisor comments.docx"


# --- comparing versions (V2) ----------------------------------------------------------------------


class DiffPiece(BaseModel):
    op: Literal["same", "added", "removed"]
    text: str


class SectionDiff(BaseModel):
    number: str
    heading: str
    status: Literal["SAME", "CHANGED", "ADDED", "REMOVED"]
    pieces: list[DiffPiece]


class Comparison(BaseModel):
    number: int
    older: int
    newer: int
    changed: int
    sections: list[SectionDiff]


BREAK = "\n"  # a paragraph break, compared like a word


def _words(paragraphs: list[str]) -> list[str]:
    out: list[str] = []
    for i, paragraph in enumerate(paragraphs):
        out += ([BREAK] if i else []) + paragraph.split()
    return out


def _joined(words: list[str]) -> str:
    return " ".join(words).replace(f" {BREAK} ", BREAK).replace(f"{BREAK} ", BREAK).replace(f" {BREAK}", BREAK)


def _pieces(old: list[str], new: list[str]) -> list[DiffPiece]:
    pieces: list[DiffPiece] = []
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if op == "equal":
            pieces.append(DiffPiece(op="same", text=_joined(old[a1:a2])))
            continue
        if a2 > a1:
            pieces.append(DiffPiece(op="removed", text=_joined(old[a1:a2])))
        if b2 > b1:
            pieces.append(DiffPiece(op="added", text=_joined(new[b1:b2])))
    return pieces


def compare(rt: Runtime, user: User, project_id: str, number: int, older: int, newer: int) -> Comparison:
    """Two versions of a chapter, section by section and word by word, citations as they print."""
    p = _owned(rt, user, project_id)
    if number not in (1, 2, 3, CONCEPT):
        raise NotFound("That chapter doesn't exist.")
    stored = p.chapter(number)
    a, b = _chapter_doc(rt, stored, older), _chapter_doc(rt, stored, newer)
    if a is None or b is None:
        raise NotFound("That version doesn't exist.")
    library = load_library(rt.files, p.evidence_files)

    def rendered(doc: ChapterDocument) -> dict[str, tuple[str, str, list[str]]]:
        """What the student sees of each section: its prose, then its table's caption and rows, so a
        changed schedule or budget is a change (Codex audit 56c4f83 M18)."""
        citer = evidence.Citer(library, p.citation)  # its own: APA 6 names all authors only at a first citation
        out = {}
        for s in doc.sections:
            lines = [citer.render(par) for par in s.paragraphs]
            if s.table:
                lines.append(f"Table: {citer.render(s.table_caption)}".rstrip())
                lines += [" | ".join(citer.render(cell) for cell in row) for row in s.table]
            out[s.key] = (s.number, s.heading, lines)
        return out

    before, after = rendered(a), rendered(b)
    sections = []
    for key in [*after, *[k for k in before if k not in after]]:
        if key not in before:
            num, heading, pars = after[key]
            sections.append(SectionDiff(number=num, heading=heading, status="ADDED", pieces=[DiffPiece(op="added", text=BREAK.join(pars))]))
        elif key not in after:
            num, heading, pars = before[key]
            sections.append(SectionDiff(number=num, heading=heading, status="REMOVED", pieces=[DiffPiece(op="removed", text=BREAK.join(pars))]))
        else:
            num, heading, pars = after[key]
            renamed = before[key][:2] != (num, heading)
            same = before[key][2] == pars and not renamed
            pieces = [DiffPiece(op="same", text=BREAK.join(pars))] if same else _pieces(_words(before[key][2]), _words(pars))
            if renamed:
                pieces.insert(0, DiffPiece(op="removed", text=f"{before[key][0]} {before[key][1]}{BREAK}"))
            sections.append(SectionDiff(number=num, heading=heading, status="SAME" if same else "CHANGED", pieces=pieces))
    return Comparison(number=number, older=older, newer=newer, changed=sum(1 for s in sections if s.status != "SAME"), sections=sections)


# --- deletion -------------------------------------------------------------------------------------


def delete(rt: Runtime, user: User, project_id: str) -> None:
    """Delete a project, its chapters, versions and evidence. Refused while a step runs."""
    p = rt.store.get_project(project_id) if _valid_id(project_id) else None
    if p is None or p.owner_uid != user.uid:
        return  # already gone (or never the user's): idempotent, and reveals nothing
    if not _erase_project(rt, p) and rt.store.get_project(p.id) is not None:
        raise Conflict("A step is running for this proposal. Delete it when the step finishes.", code="STEP_RUNNING")
    from app.works.service import unreserve

    unreserve(rt, user, f"project:{project_id}", "Reserved for a deleted proposal: returned")
    log(logger, logging.INFO, "project deleted", projectId=project_id)



def sample_size_preview(sample: SampleSize) -> dict[str, object]:
    """What PaperAid will calculate from the student's figures, shown while they edit the plan."""
    result = sampling.calculate(sample)
    return {"size": result.size, "steps": result.steps, "missing": result.missing}


# --- one Start (owner decision 2026-10-01) ------------------------------------------------------------------
# The student gives their topic and study details and presses Start: PaperAid plans, and once its own
# final review approves the plan, writes Chapter One (or the concept paper) by itself. The plan is never
# approved in the student's name otherwise (Codex 2026-10-01). One charge: the plan is part of the first
# document's price.

NOT_FINISHED = "We couldn't finish this one: PaperAid could not make a plan it was satisfied with. You were not charged. Please try again."
SAMPLING_NEEDED = "PaperAid needs one answer to continue: may it use the standard sample-size settings where you gave no figures?"
SAMPLING_CONSENT = "Standard sample-size settings (95% confidence, 5% margin, 50% proportion) where the student gave none, as stated when they started."


def start(rt: Runtime, user: User, project_id: str, accept_sampling: bool = False) -> ProjectView:
    """Start, or continue after a stop: plan (bundled) if there is no approved plan, otherwise write the
    first document."""
    from app.works.service import check_credits  # the same credit checks for every service

    require_terms(rt, user)
    p = _owned(rt, user, project_id)
    if open_guide_questions(p, rulebook.load(p.rulebook)):
        raise AppError("Your guide differs from the standard guide in a few places. Answer the questions about them on your proposal's page first.",
                       code="GUIDE_QUESTIONS")
    _require_ai(rt, user)
    if step_running(rt, p):
        raise Conflict("PaperAid is already working on this.", code="STEP_RUNNING")
    first: Step = "CONCEPT" if p.goal == "CONCEPT" else "CHAPTER_1"
    price = 0
    if rt.settings.pricing_mode == "fixed":
        price = fixed_price(rt.settings, "PLAN", None) + fixed_price(rt.settings, "CONCEPT" if first == "CONCEPT" else "CHAPTER_1", None)
    check_credits(rt, user, "CONCEPT_PAPER" if p.goal == "CONCEPT" else "PROPOSAL", price)
    from app.jobs.service import resumable, resume_step

    last = rt.store.get(p.jobs[-1]) if p.jobs else None
    if p.auto and last is not None and last.selection.proposal in ("PLAN", "CHAPTER_1", "CONCEPT") and resumable(rt, last):
        # Stopped for a temporary reason: resume that step where it stopped (see app.works.service.start).
        reservation = (f"project:{project_id}:{secrets.token_hex(4)}", price) if last.selection.proposal == "PLAN" else None
        if resume_step(rt, user, last.id, reservation):
            return view(rt, _owned(rt, user, project_id))

    if accept_sampling and not p.sampling_consent:
        def consent(q: Project) -> Project:
            q.sampling_consent = True
            return q

        p = _change(rt, user, project_id, consent)
    if p.plan is not None and p.plan_status != "APPROVED" and p.plan_review is not None and p.plan_review.outcome == "APPROVED" \
            and p.plan.sampling_assumed and p.sampling_consent and p.jobs:
        # Stopped only for the sample-size settings, now confirmed: continue from the plan already made.
        # Nothing is reserved (Codex's second look at 9239dd0): the plan is done, so the chapter starts
        # now and holds its own price in its own transaction. Only one Start marks it pending; a second
        # one, or one after the chapter started, is refused, so it can never reserve or stop anything.
        plan_job = p.jobs[-1]

        def pending(q: Project) -> Project:
            if q.auto_next == plan_job or q.plan_status == "APPROVED":
                raise Conflict("PaperAid is already working on this.", code="STEP_RUNNING")
            q.auto, q.auto_failure, q.auto_next = True, "", plan_job
            return q

        _change(rt, user, project_id, pending)
        continue_after_plan(rt, project_id, plan_job)
        return view(rt, _owned(rt, user, project_id))
    step: Step = first if p.plan is not None and p.plan_status == "APPROVED" else "PLAN"
    # One transaction (see works): submitted, started and reserved together, or none of them.
    key = f"project:{project_id}:{secrets.token_hex(4)}"  # this attempt's own reservation (see works)
    quoted = quote_step(rt, user, project_id, step, "", bundled=True)
    submit_step(rt, user, project_id, quoted.job.id, quoted.quote.id, start=True, reservation=(key, price) if step == "PLAN" else None)
    return view(rt, _owned(rt, user, project_id))


def continue_after_plan(rt: Runtime, project_id: str, plan_job: str) -> None:
    """Run by the worker once a plan started with one Start is published: approved by PaperAid's final
    review and complete, it is approved and the first document starts; otherwise it stops and says so.
    At most once per plan (only while that plan step is the project's last step)."""
    p = rt.store.get_project(project_id)
    if p is None or p.deleting or not p.auto or p.auto_next != plan_job:
        return  # nothing pending for this plan
    owner = User(uid=p.owner_uid, email=p.owner_email, is_admin=False, verified=True)

    def stop(message: str) -> None:
        from app.works.service import unreserve

        unreserve(rt, owner, f"project:{project_id}")  # first: a half-finished stop stays pending and is repeated

        def apply(q: Project) -> Project:
            q.auto_failure, q.auto_next = message, ""
            return q

        _change(rt, owner, project_id, apply)
        from app import notify

        notify.stopped(rt, plan_job)  # recorded on the plan's job and delivered like any other message

    approved = (p.plan is not None and p.plan_review is not None and p.plan_review.outcome == "APPROVED"
                and not plan_problems(p))
    if not approved:
        objections = list(p.plan_review.objections) if p.plan_review is not None else []
        problems = plan_problems(p) if p.plan is not None else []
        why = [*problems, *objections][:2]
        stop(NOT_FINISHED + (f" What it could not settle: {' '.join(why)[:400]}" if why else ""))
        return
    assert p.plan is not None
    if p.plan.sampling_assumed and not p.sampling_consent:
        stop(SAMPLING_NEEDED + " " + "; ".join(p.plan.sampling_assumed))
        return

    def approve(q: Project) -> Project:
        assert q.plan is not None
        if q.plan.sampling_assumed:  # the student was told the standard settings when they started
            q.acknowledgments.append(Acknowledgment(kind="SAMPLING", plan_version=q.plan_version, text_sha256=hashlib.sha256(SAMPLING_CONSENT.encode()).hexdigest()))
        q.plan_status = "APPROVED"
        q.auto_chapter_one = False  # started here, never again by an approval
        return q

    try:
        _change(rt, owner, project_id, approve)
        quoted = quote_step(rt, owner, project_id, "CONCEPT" if p.goal == "CONCEPT" else "CHAPTER_1", "", bundled=True)
        submit_step(rt, owner, project_id, quoted.job.id, quoted.quote.id)
    except AppError as exc:  # credits ran out meanwhile, a figure only the student can give: say why
        current = rt.store.get_project(project_id)
        if current is not None and step_running(rt, current):
            return  # another continuation started it at the same moment (maintenance): nothing to stop
        log(logger, logging.WARNING, "auto chapter did not start", projectId=project_id, code=exc.code)
        stop(f"Your first chapter could not start: {exc.message}")


def request_changes_with_document(rt: Runtime, user: User, project_id: str, number: int, instruction: str, sections: list[str], filename: str, data: bytes) -> ProjectView:
    """A change request with a document for context: its text is read here and goes to the writer with
    the request; the document itself is not kept."""

    _rate_limit(rt, user, "upload", rt.settings.uploads_per_hour)
    model = inspect_upload(data, filename, rt.settings.max_upload_bytes, 60000, rt.settings.max_pdf_pages, min_words=5)
    context = "\n".join(b.text for b in model.blocks if b.text.strip())
    return request_changes(rt, user, project_id, number, instruction, sections, filename.rsplit("/", 1)[-1], context)


def framework_png(rt: Runtime, user: User, project_id: str) -> bytes:
    """The conceptual framework figure drawn from the plan's variables (none for a study without
    independent and dependent variables)."""
    p = _owned(rt, user, project_id)
    png = framework.draw(p.plan.variables) if p.plan else None
    if png is None:
        raise NotFound("This study has no conceptual framework figure.")
    return png
