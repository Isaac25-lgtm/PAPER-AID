"""Work contracts (owner decision 2026-09-30, rulebook v1.0): concept notes, coursework and funding
proposals. A work is a persistent record like a proposal project: the student's inputs, the
documents they uploaded, the requirement set read from them (versioned), the plan, and for funding
the Results Model and budget. Every paid step (reading the documents, the plan, the draft, a
revision) is an ordinary job linked by `work_id`, frozen when it is priced.

Firestore keeps this record (metadata and short structured text, capped so it stays small). Each
requirement-set version and each document version is an immutable file in storage; the record only
moves its pointer, inside a transaction (Codex review 2026-09-30). Works live in their own
collection, so a rollback to a release that does not know them never reads one."""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from app.jobs.models import Camel, ReadinessItem, utcnow
from app.proposals.ai import Figure

WorkKind = Literal["CONCEPT_NOTE", "COURSEWORK", "FUNDING_PROPOSAL"]
Variant = Literal[
    "FUNDING_CONCEPT", "PROJECT_CONCEPT",
    "ESSAY", "ACADEMIC_REPORT", "CASE_STUDY_ANALYTICAL", "CASE_STUDY_PROBLEM", "LITERATURE_REVIEW",
    "RESEARCH_PAPER_EMPIRICAL", "RESEARCH_PAPER_NON_EMPIRICAL", "REFLECTIVE",
    "NGO_PROJECT", "RESEARCH_GRANT",
]
KIND_VARIANTS: dict[str, tuple[str, ...]] = {
    "CONCEPT_NOTE": ("FUNDING_CONCEPT", "PROJECT_CONCEPT"),
    "COURSEWORK": ("ESSAY", "ACADEMIC_REPORT", "CASE_STUDY_ANALYTICAL", "CASE_STUDY_PROBLEM", "LITERATURE_REVIEW", "RESEARCH_PAPER_EMPIRICAL", "RESEARCH_PAPER_NON_EMPIRICAL", "REFLECTIVE"),
    "FUNDING_PROPOSAL": ("NGO_PROJECT", "RESEARCH_GRANT"),
}
Mode = Literal["", "BRIEF", "STANDARD", "EXTENDED", "COMPACT", "COMPREHENSIVE"]
KIND_MODES: dict[str, tuple[str, ...]] = {"CONCEPT_NOTE": ("BRIEF", "STANDARD", "EXTENDED"), "COURSEWORK": ("",), "FUNDING_PROPOSAL": ("COMPACT", "STANDARD", "COMPREHENSIVE")}
Level = Literal["", "FIRST_YEAR_UG", "LATER_UG", "POSTGRADUATE"]
SourceRole = Literal["CALL", "TEMPLATE", "ADDENDUM", "BRIEF", "RUBRIC", "READING", "GUIDE", "OTHER"]
CitationStyle = Literal["APA7", "APA6", "HARVARD"]
AiPolicy = Literal["UNKNOWN", "BANNED", "ALLOWED_WITH_DISCLOSURE", "ALLOWED"]
Authority = Literal["EXTERNAL_MANDATORY", "USER_EXPLICIT", "DOCUMENT_VARIANT", "PAPERAID_BASELINE", "QUALITY_GUIDANCE", "MODEL_PREFERENCE"]
AUTHORITY_ORDER: tuple[str, ...] = ("EXTERNAL_MANDATORY", "USER_EXPLICIT", "DOCUMENT_VARIANT", "PAPERAID_BASELINE", "QUALITY_GUIDANCE", "MODEL_PREFERENCE")
Readiness = Literal["NOT_READY", "READY_WITH_WARNINGS", "READY"]
# The note a coursework draft carries on its last page when the brief bans AI (owner decision 2026-09-30).
AI_NOTE = "This document was drafted by an AI-assisted third party."
# Shown on screen, never printed in the document (owner decision 2026-10-08), when the assignment itself bans AI tools.
AI_BANNED_NOTICE = "Your assignment says AI tools are not allowed. Check your institution's rules before you submit this."


def _one_line(value: str) -> str:
    return " ".join(value.split())


# --- what the student gives --------------------------------------------------------------------------


class WorkInputs(Camel):
    """The student's own description. Sent to AI models, so never their name or registration number."""

    title: str = Field(min_length=3, max_length=300)  # the topic, project name or assignment title
    description: str = Field(default="", max_length=8000)  # the idea, the problem, or the assignment question as given
    # Answers to the ask-once questions (question id → answer), the student's own facts: locked once given.
    answers: dict[str, str] = {}
    experience: str = Field(default="", max_length=8000)  # reflective work: the student's own experience, never invented

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _one_line(value)

    @field_validator("answers")
    @classmethod
    def _answers(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 60:
            raise ValueError("too many answers")
        return {k[:60]: v.strip()[:3000] for k, v in value.items() if v.strip()}


class SourceView(Camel):
    """A document the student uploaded or pasted: the call, template, brief, rubric or a reading."""

    id: str
    name: str
    role: SourceRole
    words: int
    uploaded_at: datetime = Field(default_factory=utcnow)


class SourceFile(SourceView):
    sha256: str
    path: str  # its extracted text in storage (never shown to browsers)
    # A reading's bibliographic details, as read from its first pages (title, authors, year, ...).
    bibliography: dict[str, Any] = {}


# --- the requirement set -------------------------------------------------------------------------------


class Requirement(Camel):
    """One requirement, with where it came from. An external requirement keeps its exact quote and
    location; code checks the quote is really in the document before it can lock (rulebook §5.2)."""

    id: str
    key: str  # vocabulary: app.rules.extract.KEYS
    label: str  # plain wording for the student
    value: str = ""
    number: float | None = None
    unit: str = ""
    hard: bool = True  # a mandatory instruction (False: guidance or a preference)
    authority: Authority = "EXTERNAL_MANDATORY"
    source: str = ""  # the file's name, "Your answer" or "PaperAid's standard"
    source_id: str = ""
    quote: str = ""
    location: str = ""
    verified: bool = False  # PaperAid found the quote in the source
    confirmed: bool = False  # the student confirmed it on the "PaperAid understood" screen
    high_stakes: bool = False  # deadline, eligibility, ceiling, cost share, banned costs, hard limits, AI policy
    weight: float | None = None  # a scoring or rubric criterion's weight
    counts_toward: list[str] = []  # the parts a limit counts (rulebook §6.2)
    in_conflict: bool = False
    amends: bool = False  # the source says it changes an earlier instruction (an addendum or clarification)

    @property
    def locked(self) -> bool:
        """Only a confirmed quote without a conflict locks; a high-stakes one also needs the student."""
        if self.authority != "EXTERNAL_MANDATORY":
            return True
        return self.verified and not self.in_conflict and (self.confirmed or not self.high_stakes)


class RequirementConflict(Camel):
    key: str
    requirement_ids: list[str]
    note: str
    chosen: str | None = None  # the requirement the student chose


class Limit(Camel):
    type: Literal["WORD", "CHARACTER", "FIELD", "PAGE"]
    max: float
    min: float | None = None
    scope: list[str] = ["core"]  # "core" (the main text), a section key, or a field id
    field: str = ""
    includes_spaces: bool = True
    tolerance: float = 0.0  # only when the instructions state one (CW-007)
    blocking: bool = True
    requirement: str = ""  # the requirement it comes from ("" = PaperAid's plan)


class FormField(Camel):
    """One box of an online application form (rulebook §18)."""

    id: str
    label: str
    required: bool = True
    max_words: int | None = None
    max_characters: int | None = None
    includes_spaces: bool = True


class Criterion(Camel):
    """A published scoring criterion or rubric row (rulebook §16, Appendix H)."""

    id: str
    name: str
    weight: float | None = None
    descriptor: str = ""  # the top-band description, as quoted
    mandatory: bool = False  # the rubric says it must be met to pass
    requirement: str = ""


class CoverageItem(Camel):
    """One part of the task that must be answered (CW-003): a directive or sub-question."""

    id: str
    text: str
    directive: str = ""
    requirement: str = ""


class Question(Camel):
    """An ask-once question, or a blocking one (rulebook §9.1, Appendix C)."""

    id: str
    label: str
    help: str = ""
    kind: Literal["TEXT", "LONG", "NUMBER", "CHOICE", "BOOL"] = "TEXT"
    choices: list[str] = []
    gate: Literal["BLOCK", "ASK_ONCE"] = "ASK_ONCE"
    answered: bool = False
    fallback: str = ""  # what PaperAid assumes if the student skips it (ASK_ONCE only)


class ResolvedSpec(Camel):
    """Everything a step runs on, resolved centrally (app.rules.resolve) and versioned: models get
    this compact specification, never the whole rule library (rulebook §7, §23)."""

    version: int
    kind: WorkKind
    variant: Variant
    mode: Mode = ""
    level: Level = ""
    rules_version: str
    target_words: int
    limits: list[Limit] = []
    fields: list[FormField] = []
    template_headings: list[str] = []  # an official template's headings, in its order
    citation_style: CitationStyle = "APA7"
    ai_policy: AiPolicy = "UNKNOWN"
    source_policy: Literal["INDEPENDENT", "CLOSED", "NONE"] = "INDEPENDENT"
    required_readings: list[str] = []
    scoring: list[Criterion] = []
    directives: list[str] = []  # command-word ids (app.works.directives)
    directive_groups: list[str] = []
    subject: str = ""
    limiting: list[str] = []
    coverage: list[CoverageItem] = []
    priorities: list[str] = []  # a funder's priority areas, as quoted
    eligibility: list[str] = []  # eligibility criteria, as quoted (the student confirms each is met)
    ceiling: float | None = None
    minimum_request: float | None = None
    currency: str = ""
    duration_months: int | None = None
    deadline: str = ""
    cost_share: float | None = None  # percent
    cost_share_base: str = ""
    indirect_rate: float | None = None  # percent
    indirect_base: str = ""
    prohibited_costs: list[str] = []
    overlays: list[str] = []  # SAFEGUARDING, DATA_PROTECTION, GENDER, ...
    annexes: list[str] = []
    flags: dict[str, bool] = {}
    requirements: list[Requirement] = []
    conflicts: list[RequirementConflict] = []
    assumptions: list[str] = []
    questions: list[Question] = []
    gate: Literal["PASS", "ASK_ONCE", "BLOCK"] = "PASS"
    blockers: list[str] = []
    active_rules: list[str] = []
    overridden: list[str] = []  # "key: what won, over what"
    exploratory: bool = False  # eligibility failed and the student chose an exploratory draft


# --- the plan --------------------------------------------------------------------------------------------


class PlanSection(Camel):
    key: str
    heading: str = Field(max_length=200)
    words: int = Field(ge=0, le=20000)
    min_words: int = Field(default=0, ge=0, le=20000)
    max_words: int = Field(default=0, ge=0, le=20000)
    required: bool = True
    locked: bool = False  # an external mandatory heading: it cannot be removed or renamed
    brief: str = Field(default="", max_length=1500)  # what the section will cover
    criteria: list[str] = []  # scoring or rubric criteria it answers
    coverage: list[str] = []  # coursework: the parts of the question it answers
    field_id: str = ""  # form mode: the application box it fills


class WorkPlan(Camel):
    """What will be written, section by section. Drafted by PaperAid, then edited and approved by
    the student; the draft is written only from an approved plan."""

    title: str = Field(max_length=300)
    position: str = Field(default="", max_length=2000)  # the central argument, judgement or idea
    sections: list[PlanSection]
    questions_for_student: list[str] = []
    notes: list[str] = []

    @property
    def total_words(self) -> int:
        return sum(s.words for s in self.sections)


# --- funding: the Results Model and budget (rulebook §12.6, Appendices A2, E) ------------------------


class Goal(Camel):
    id: str = "G1"
    statement: str = Field(default="", max_length=600)


class Objective(Camel):
    id: str
    statement: str = Field(max_length=600)


class Outcome(Camel):
    id: str
    statement: str = Field(max_length=600)
    objective_id: str = ""
    assumptions: list[str] = []


class Output(Camel):
    id: str
    statement: str = Field(max_length=600)
    outcome_id: str = ""


class Activity(Camel):
    id: str
    statement: str = Field(max_length=600)
    output_id: str = ""
    owner_role: str = Field(default="", max_length=120)
    start_month: int | None = Field(default=None, ge=1, le=120)
    end_month: int | None = Field(default=None, ge=1, le=120)
    costed: bool = True  # an activity that costs nothing (a meeting within staff time) needs no budget line
    major: bool = True


class Indicator(Camel):
    id: str
    result_id: str  # the goal, outcome or output it measures
    level: Literal["goal", "outcome", "output"]
    definition: str = Field(default="", max_length=600)
    unit: str = Field(default="", max_length=60)
    baseline: float | None = None
    baseline_year: int | None = None
    baseline_plan: str = Field(default="", max_length=400)  # how and when the baseline will be established
    target: float | None = None
    target_date: str = Field(default="", max_length=20)
    disaggregation: list[str] = []
    means_of_verification: str = Field(default="", max_length=300)
    frequency: str = Field(default="", max_length=60)
    responsible_role: str = Field(default="", max_length=120)


class Risk(Camel):
    id: str
    statement: str = Field(max_length=600)
    likelihood: Literal["low", "medium", "high"] = "medium"
    impact: Literal["low", "medium", "high"] = "medium"
    mitigation: str = Field(default="", max_length=600)
    owner_role: str = Field(default="", max_length=120)


class ResultsModel(Camel):
    """The single source of truth for goal, results, indicators and timing: the logframe, workplan
    and M&E table are rendered from it by code, never written separately (FP-073 to FP-075)."""

    goal: Goal = Field(default_factory=Goal)
    objectives: list[Objective] = Field(default=[], max_length=10)
    outcomes: list[Outcome] = Field(default=[], max_length=15)
    outputs: list[Output] = Field(default=[], max_length=40)
    activities: list[Activity] = Field(default=[], max_length=80)
    indicators: list[Indicator] = Field(default=[], max_length=80)
    risks: list[Risk] = Field(default=[], max_length=20)
    assumptions: list[str] = []


class BudgetLine(Camel):
    id: str
    category: str = Field(max_length=80)
    description: str = Field(max_length=300)
    quantity: float = Field(ge=0)
    unit: str = Field(default="", max_length=40)
    unit_cost: float = Field(ge=0)
    entered_total: float | None = None  # what the student typed as the line's total, if anything
    year: int = Field(default=1, ge=1, le=10)
    activity_ids: list[str] = []
    support: bool = False  # a declared support or administrative cost (not tied to one activity)
    role: str = Field(default="", max_length=120)  # a staff line's role (level-of-effort checks)


class Budget(Camel):
    """Money as structured numbers: code does every sum (Appendix E); the writer only refers to them."""

    currency: str = Field(default="USD", max_length=8)
    lines: list[BudgetLine] = Field(default=[], max_length=200)
    requested: float | None = None  # the amount the application asks for
    cost_share_provided: float | None = None
    indirect_amount: float | None = None
    exchange_rate: float | None = None  # when converting from another currency
    exchange_from: str = Field(default="", max_length=8)
    exchange_date: str = Field(default="", max_length=20)


# --- the document ----------------------------------------------------------------------------------------


class WorkSection(Camel):
    key: str
    heading: str
    paragraphs: list[str]  # evidence tokens ⟦E…⟧ and number tokens ⟦N:…⟧ stay as tokens until rendered
    table: list[list[str]] | None = None
    table_caption: str = ""
    table_illustrative: bool = False  # a worked example: its caption says "illustrative values" (code)
    figure: Figure | None = None  # a graph PaperAid draws from the writer's data
    field_id: str = ""
    reviewed: bool = True


class WorkDocument(Camel):
    """One version of the work as written, with its compliance report (readiness)."""

    kind: WorkKind
    variant: Variant
    title: str
    spec_version: int
    plan_version: int
    results_version: int = 0
    budget_version: int = 0
    sections: list[WorkSection]
    cited: list[str] = []
    readiness: list[ReadinessItem] = []
    warnings: list[str] = []
    words: int = 0
    status: Readiness = "NOT_READY"
    exploratory: bool = False
    ai_note: str = ""  # the last-page note, when it applies
    revised: list[str] = []  # a revision: the sections it delivered new text for
    # What it was written from, kept with it so every later download renders exactly this version.
    spec_snapshot: ResolvedSpec | None = None
    results_snapshot: ResultsModel | None = None
    budget_snapshot: Budget | None = None
    number_values: dict[str, list[str]] = {}  # number token → [how it prints, what it means]
    cover: dict[str, str] = {}  # the student's cover-page details (owner decision 2026-10-01), printed under the title


class DocVersion(Camel):
    version: int
    job_id: str
    created_at: datetime = Field(default_factory=utcnow)
    words: int
    status: Readiness
    note: str = ""


class StoredDocVersion(DocVersion):
    path: str
    docx_path: str = ""  # the Word file built and checked before the step completed ("" for older versions)


class ChangeRequest(Camel):
    """The student's own request for changes ("Ask for changes"), applied by a revision step."""

    id: str
    text: str = Field(max_length=1500)
    sections: list[str] = []
    status: Literal["OPEN", "APPLIED", "DECLINED"] = "OPEN"
    applied_in: int | None = None
    # A document the student added for context ("Add documents for more context"): its name and text,
    # given to the writer with the request.
    context_name: str = Field(default="", max_length=120)
    context: str = Field(default="", max_length=8000)  # older requests only: the text is now kept in file storage
    context_path: str = ""  # where the document's text (its first CONTEXT_WORDS words) is kept


Status = Literal["NONE", "DRAFT", "APPROVED"]


class ReviewDecision(Camel):
    """The one accountable final reviewer's decision (owner decision 2026-09-30) on a plan or Results
    Model PaperAid delivered: approved, still objecting after two targeted repairs, or not reviewed (the
    review could not complete). Anything not approved is kept for the student to edit, never charged,
    and approved only with the student's explicit acknowledgment of what is shown."""

    outcome: Literal["APPROVED", "OBJECTIONS", "NOT_REVIEWED"]
    reason: str = ""  # REVIEW_OBJECTION, REVIEW_UNAVAILABLE, SPEND_CAP or CODE_RULE
    objections: list[str] = []
    version: int = 0  # the plan or Results Model version it was given for
    # What would make it stronger without blocking it (live funding runs 2026-10-03: every improvement
    # counted as an objection, so the review never settled). Kept for admins and diagnosis, never repaired for: they
    # name internal parts (indicator ids) the student does not see.
    suggestions: list[str] = []


class WorkAcknowledgment(Camel):
    kind: Literal["PLAN_OBJECTIONS", "RESULTS_OBJECTIONS"]
    version: int
    text_sha256: str
    at: datetime = Field(default_factory=utcnow)


class WorkView(Camel):
    """What the owner's browser sees."""

    id: str
    kind: WorkKind
    variant: Variant
    mode: Mode = ""
    level: Level = ""
    citation: CitationStyle = "APA7"
    inputs: WorkInputs
    sources: list[SourceView] = []
    spec: ResolvedSpec | None = None  # the current requirement set (loaded for the view)
    spec_version: int = 0
    spec_status: Literal["NONE", "DRAFT", "CONFIRMED"] = "NONE"
    plan: WorkPlan | None = None
    plan_status: Status = "NONE"
    plan_version: int = 0
    candidate_plan: WorkPlan | None = None
    plan_review: ReviewDecision | None = None  # None: planned before one final reviewer, or never reviewed
    candidate_review: ReviewDecision | None = None
    results: ResultsModel | None = None
    results_status: Status = "NONE"
    results_version: int = 0
    results_review: ReviewDecision | None = None
    acknowledgments: list[WorkAcknowledgment] = []
    budget: Budget | None = None
    budget_version: int = 0
    documents: list[DocVersion] = []
    current: int = 0
    requests: list[ChangeRequest] = []
    ai_note: bool = True  # before 2026-10-08: the last-page note for an unknown AI policy (kept so older releases can read the record)
    # The student asked for the last-page note (owner decision 2026-10-08: nothing about AI is asked or printed unless
    # the student asks; an assignment that bans AI tools is told to the student on screen, never in the document).
    ai_note_asked: bool = False
    exploratory: bool = False  # the student chose an exploratory draft although an eligibility criterion is not met
    readiness: list[ReadinessItem] = []  # the current document's compliance report (computed for the view)
    status: Readiness | None = None  # (computed for the view)
    checks: list[ReadinessItem] = []  # code checks on the plan, Results Model and budget before drafting (computed)
    needs_read: bool = False  # documents were added since PaperAid last read them (computed)
    budget_totals: dict[str, Any] | None = None  # the budget's sums, worked out by the server (computed)
    notice: str | None = None
    active_job: str | None = None
    jobs: list[str] = []
    # Started with one Start (owner decision 2026-10-01): PaperAid reads, plans and drafts by itself
    # and the student sees only the document. `auto_failure` says why it stopped without one.
    auto: bool = False
    auto_failure: str = ""
    # The one-Start plan step whose next step is still to happen (Codex audit 2026-10-01): set in the
    # transaction that publishes the plan, cleared in the one that submits the draft or by a stop;
    # maintenance finishes it if a worker stopped in between.
    auto_next: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime


class Work(WorkView):
    """The full server record."""

    owner_uid: str
    owner_email: str
    sources: list[SourceFile] = []  # type: ignore[assignment]
    documents: list[StoredDocVersion] = []  # type: ignore[assignment]
    spec_path: str = ""  # the current requirement-set version in storage
    requirements_path: str = ""  # what the READ step found in the student's documents (immutable, per job)
    read_sources: list[str] = []  # the documents that READ step read
    evidence_files: list[str] = []
    published: list[str] = []  # jobs whose results were published here (a retried publish adds nothing)
    deleting: bool = False
    spec: None = None  # type: ignore[assignment]  # never stored on the record: it lives in storage

    def view(self) -> WorkView:
        data = self.model_dump(exclude={"spec"})
        return WorkView.model_validate(data)

    def storage_prefix(self) -> str:
        # Outside users/ like proposal projects: kept while the work is renewed, removed by the app's cleanup.
        return f"works/{self.owner_uid}/{self.id}"


# --- a step's frozen input ---------------------------------------------------------------------------------


class WorkStepInput(Camel):
    """What a work step runs on, frozen when it is priced; its hash binds the quote."""

    work_id: str
    step: Literal["READ", "PLAN", "DRAFT", "REVISE"]
    kind: WorkKind
    variant: Variant
    mode: Mode = ""
    level: Level = ""
    citation: CitationStyle = "APA7"
    inputs: WorkInputs
    sources: list[SourceFile] = []
    spec: ResolvedSpec | None = None
    plan: WorkPlan | None = None
    plan_version: int = 0
    results: ResultsModel | None = None
    results_version: int = 0
    budget: Budget | None = None
    budget_version: int = 0
    evidence_files: list[str] = []
    note: str = ""
    ai_note: bool = True  # before 2026-10-08 (read by steps priced then)
    ai_note_asked: bool = False  # the student asked for the last-page note
    exploratory: bool = False
    private: list[str] = []  # words that must never reach a search
    # REVISE: the version being revised and the requests by section key; every other section is kept.
    base: str = ""
    base_version: int = 0
    base_sha: str = ""
    revise: dict[str, list[str]] = {}
    request_ids: list[str] = []
