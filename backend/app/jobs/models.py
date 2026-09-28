"""Job contracts. Field names serialise to camelCase to match web/src/lib/types.ts exactly."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.formatting.presets import CustomLayout


def utcnow() -> datetime:
    return datetime.now(UTC)


class Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ServiceId(StrEnum):
    AI_CHECK = "AI_CHECK"
    REFINE = "REFINE"
    FORMAT = "FORMAT"
    TEMPLATE_FORMAT = "TEMPLATE_FORMAT"
    REDRAFT = "REDRAFT"
    LATEX = "LATEX"
    SOURCE_CHECK = "SOURCE_CHECK"
    PROPOSAL = "PROPOSAL"


class JobStatus(StrEnum):
    DRAFT = "DRAFT"
    QUOTED = "QUOTED"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Stage(StrEnum):
    EXTRACTING = "EXTRACTING"
    ANALYSING = "ANALYSING"
    RESEARCHING = "RESEARCHING"
    PLANNING = "PLANNING"
    REFINING = "REFINING"
    REDRAFTING = "REDRAFTING"
    FORMATTING = "FORMATTING"
    CONVERTING = "CONVERTING"
    DRAFTING = "DRAFTING"
    AUDITING = "AUDITING"
    EXPORTING = "EXPORTING"


class PaymentStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


Band = Literal["LOW", "MODERATE", "HIGH"]
Confidence = Literal["LOW", "MEDIUM", "HIGH"]
ReasonCode = Literal[
    # AI-like writing (the band is computed from these alone)
    "GENERIC_PHRASING", "UNIFORM_STRUCTURE", "LOW_SPECIFICITY", "FORMULAIC_TRANSITIONS", "OVER_HEDGING", "UNSUPPORTED_SUMMARY", "REPETITION", "STYLE_SHIFT",
    # academic writing
    "OVERCLAIMING", "EXCESSIVE_HEDGING", "VAGUE_WORDING", "UNSUPPORTED_INTERPRETATION", "TENSE_INCONSISTENCY", "WEAK_FLOW",
    # evidence and claims
    "CLAIM_WITHOUT_EVIDENCE", "CAUSAL_OVERSTATEMENT", "CONFLICTING_NUMBERS", "CURRENT_STATISTIC",
    # methodology
    "OBJECTIVE_METHOD_MISMATCH", "DESIGN_MISMATCH", "SAMPLE_INCONSISTENCY", "MISSING_VALIDITY",
    # formatting (found by code)
    "HEADING_AS_TEXT", "HEADING_LEVEL_SKIP", "CAPTION_NUMBERING",
]
FindingCategory = Literal["AI_LIKE", "ACADEMIC", "EVIDENCE", "METHOD", "FORMATTING"]


WritingStyle = Literal["PRESERVE_VOICE", "STANDARD_ACADEMIC", "CONCISE_ACADEMIC", "TECHNICAL"]


class ServiceSelection(Camel):
    writing: Literal["NONE", "AI_CHECK", "REFINE", "REDRAFT"] = "NONE"
    intensity: Literal["LIGHT", "STANDARD"] = "STANDARD"
    style: WritingStyle = "PRESERVE_VOICE"  # part of the priced selection: changing it needs a new quote
    source_check: bool = False  # check the paper's factual claims against live sources (AI Check or Refine)
    formatting: Literal["NONE", "FORMAT", "TEMPLATE_FORMAT"] = "NONE"
    preset: str = "apa7"
    latex: bool = False
    academic: bool = True  # academic or research work: adds the academic, evidence and methodology review
    custom: CustomLayout | None = None  # the student's own font, size, spacing, margins or alignment over the preset
    logo: Literal["NONE", "CENTER", "LEFT"] = "NONE"  # an institution logo at the top of the first page
    only_blocks: list[str] = Field(default=[], max_length=300)  # "Fix selected": refine exactly these passages
    # A step of a proposal project, or REVIEW: an uploaded proposal checked against the rulebook.
    proposal: Literal["NONE", "PLAN", "CHAPTER_1", "CHAPTER_2", "CHAPTER_3", "REVIEW"] = "NONE"
    level: Literal["BACHELORS", "PGD", "MASTERS", "PHD"] = "MASTERS"  # the proposal's level (REVIEW only)

    def services(self) -> list[ServiceId]:
        ids = []
        if self.writing != "NONE":
            ids.append(ServiceId(self.writing))
        if self.formatting != "NONE":
            ids.append(ServiceId(self.formatting))
        if self.latex:
            ids.append(ServiceId.LATEX)
        if self.source_check:
            ids.append(ServiceId.SOURCE_CHECK)
        if self.proposal != "NONE":
            ids.append(ServiceId.PROPOSAL)
        return ids


class ImageMeta(Camel):
    """An uploaded logo: a layout asset only, never proof of affiliation (master context §17)."""

    name: str
    format: Literal["PNG", "JPEG"]
    size_bytes: int
    width_px: int
    height_px: int


class StoredImage(ImageMeta):
    path: str
    sha256: str


class FileMeta(Camel):
    name: str
    format: Literal["DOCX", "PDF"]
    size_bytes: int
    word_count: int
    page_estimate: int
    heading_count: int


class StoredFile(FileMeta):
    path: str
    sha256: str


class QuoteLine(Camel):
    label: str
    amount: int
    service: str = ""  # which service the line prices (settlement charges each line for what was delivered)


class Quote(Camel):
    """`amount` is the most the student can pay for this job, everything included. `paid` is the
    part already charged (the AI estimate), so accepting holds `amount - paid` from the wallet."""

    id: str
    currency: Literal["UGX"] = "UGX"
    lines: list[QuoteLine]
    amount: int
    paid: int = 0
    pricing_version: str
    expires_at: datetime


class Engine(Camel):
    """What a run executes with, frozen when it is priced: the two models and the prompt version of
    every algorithm step. A job runs with its quote's engine even if PaperAid is updated meanwhile,
    so the calls its estimate made replay from the cache instead of being paid for again."""

    lead_model: str
    writer_model: str
    prompts: dict[str, str]  # step → prompt version (released prompt files never change)


class Passage(Camel):
    """A passage the refinement plan covers: its size and whether the plan rewrites it."""

    model_config = ConfigDict(frozen=True)

    chars: int
    words: int
    rewrite: bool
    instruction_chars: int = 200


class BoundQuote(Quote):
    """The server copy of a quote, bound to the exact file and selection that were priced."""

    selection: ServiceSelection
    source_sha256: str
    guideline_sha256: str | None = None
    word_count: int
    fixed_ugx: int = 0  # the part not priced from AI cost (APA/Harvard formatting)
    ugx_per_usd: float = 0.0  # frozen with the quote so a later rate change can't alter it
    multiplier: float = 0.0
    engine: Engine | None = None  # None only on quotes issued before engines were recorded
    estimate_id: str | None = None  # the estimate this quote was priced from; the job reuses its saved analysis and draft plan
    budget_usd: float = 0.0  # fixed prices: the job's provider-spend cap (the worst-case projection)


# --- credits ---------------------------------------------------------------------------------


class EstimateView(Camel):
    """The paid AI scan that sizes a refinement job before it is quoted."""

    status: Literal["RUNNING", "READY", "FAILED"]
    fee_cap: int  # held while the scan runs; the most it can cost
    fee: int = 0  # what it actually cost, charged when it finishes
    message: str | None = None
    intervention: float | None = None  # share of the paper's words the plan will rewrite (0-1)


class EstimateRun(EstimateView):
    id: str
    selection: ServiceSelection
    source_sha256: str
    guideline_sha256: str | None = None
    budget_usd: float
    cost_base_usd: float = 0.0  # the job's estimate spend before this run; the run's cost is the rise from here
    held: bool = True  # False in testing mode: nothing was held, so nothing is charged
    engine: Engine | None = None
    passages: list[Passage] = []  # the result, kept so an expired quote is repriced without a new scan
    guide_words: int = 0
    attempts: int = 0
    lease_until: datetime | None = None
    requested_at: datetime = Field(default_factory=utcnow)


class Billing(Camel):
    """Where this job's credits stand. Every amount is UGX."""

    state: Literal["NONE", "HELD", "SETTLED", "RELEASED"] = "NONE"
    fee_paid: int = 0  # every estimate charged on this job and not refunded; counts toward its quote
    held: int = 0
    charged: int = 0  # final charge for the job itself, excluding the fee
    refunded: int = 0


class LedgerEntry(Camel):
    id: str
    at: datetime = Field(default_factory=utcnow)
    kind: Literal["TOP_UP", "HOLD", "CHARGE", "RELEASE", "REFUND"]
    amount: int
    job_id: str | None = None
    note: str
    available_after: int
    held_after: int
    op_id: str | None = None  # a manual grant's operation id: repeating the request adds nothing
    actor: str | None = None  # who made a manual grant


class WalletView(Camel):
    currency: Literal["UGX"] = "UGX"
    available: int = 0
    held: int = 0
    entries: list[LedgerEntry] = []
    ugx_per_usd: float = 0.0
    test_credits: bool = False  # local mode: credits are for testing only and are not money


class Wallet(Camel):
    uid: str
    email: str
    available: int = 0
    held: int = 0
    entries: list[LedgerEntry] = []  # newest last; the most recent 300 are kept
    updated_at: datetime = Field(default_factory=utcnow)
    grant_ops: list[str] = []  # every manual grant's operation id, kept for good (not trimmed like entries)
    closing: bool = False  # the account is being deleted: nothing new may start or move credits


class QuoteResponse(Camel):
    """A price, or (for refinement) the estimate that is sizing the work before a price exists."""

    quote: Quote | None = None
    estimate: EstimateView | None = None
    estimate_fee_cap: int | None = None  # refinement: the most the estimate can cost, shown before it runs


class WalletSummary(Camel):
    email: str
    available: int
    held: int
    updated_at: datetime


class Finding(Camel):
    id: str
    block_id: str
    section: str
    reason: ReasonCode
    severity: Literal["minor", "moderate", "major"]
    excerpt: str
    explanation: str
    suggestion: str
    category: FindingCategory = "AI_LIKE"
    safe: bool = True  # PaperAid may fix it without the student's judgement (never figures, citations, methods or facts)


class AnalysisResult(Camel):
    band: Band
    confidence: Confidence
    analysed_words: int
    excluded_words: int
    findings: list[Finding]
    algorithm_version: str
    method: str = ""
    review: list[Finding] = []  # academic, evidence, methodology and formatting findings (not in the band)


class ReferenceCheck(Camel):
    """One reference-list entry matched against registered bibliographic records."""

    entry: str  # as written in the paper
    status: Literal["VERIFIED", "PROBABLE", "MISMATCH", "NOT_VERIFIED"]
    doi: str = ""
    matched_title: str = ""
    matched_year: str = ""
    retracted: bool = False
    note: str = ""


class ReferenceVerification(Camel):
    items: list[ReferenceCheck]
    checked: int
    total: int  # entries in the list; more than `checked` when the list was very long
    retrieved_on: str


class ProtectedSummary(Camel):
    """What refinement locks in this paper, counted by PaperAid."""

    numbers: int
    citations: int
    quotations: int
    links: int
    word_items: int  # fields, footnotes, equations and other Word elements


class PaperCheck(Camel):
    """One citation/reference or consistency result. `certainty` says how sure PaperAid is."""

    kind: Literal["CITED_NOT_LISTED", "LISTED_NOT_CITED", "UNREADABLE_CITATION", "UNREADABLE_REFERENCE", "NO_REFERENCE_LIST", "SPELLING_MIXED"]
    certainty: Literal["CONFIRMED", "POSSIBLE", "UNDETERMINED"]
    item: str  # the citation or reference as written in the paper
    detail: str


class PaperChecks(Camel):
    """Paper-quality results, kept separate from AI-likeness (owner decision 2026-09-27)."""

    citations_found: int
    references_found: int
    style: Literal["AUTHOR_DATE", "NUMERIC", "UNKNOWN"]
    items: list[PaperCheck]
    method: str = ""


# UNCONFIRMED: sources were found but PaperAid could not open them to confirm the quotations.
SupportLevel = Literal["SUPPORTED", "PARTLY_SUPPORTED", "CONTRADICTED", "NOT_FOUND", "UNCERTAIN", "UNCONFIRMED"]


class Source(Camel):
    """Where evidence for a claim was read. The URL is always one the search actually opened."""

    url: str
    title: str
    publisher: str = ""
    published: str = ""  # as the source states it (year, or a fuller date)
    access: Literal["FULL_TEXT", "ABSTRACT", "SNIPPET"]  # how much of the source was read
    passage: str  # the words in the source that bear on the claim, quoted
    scope: str = ""  # population, place and period the source covers
    supports: Literal["SUPPORTED", "PARTLY_SUPPORTED", "CONTRADICTED", "NOT_FOUND"]
    verified: bool = False  # PaperAid found the quoted passage on the page itself, or in the article's abstract
    readable: bool = False  # PaperAid could open the page or the abstract (False: blocked, paywalled, unreachable)


class CheckedClaim(Camel):
    """One important factual claim from the paper, checked against live sources and then by a
    second model. The paper itself is never changed because of it (owner decision 2026-09-27)."""

    id: str
    block_id: str
    section: str
    claim: str  # as the paper states it
    cited: bool  # the paper already cites a source for it
    support: SupportLevel
    note: str  # why, including any mismatch of population, place or period
    sources: list[Source] = []


class ResearchResult(Camel):
    claims: list[CheckedClaim]
    checked: int
    candidates: int  # important claims found; more than `checked` when the budget ran out
    retrieved_on: str  # the date the sources were read
    method: str = ""


class ChangedBlock(Camel):
    block_id: str
    section: str
    before: str
    after: str
    kept: bool = False
    note: str | None = None
    reason: str | None = None  # the agreed plan's instruction for this passage


class RefinementResult(Camel):
    mode: Literal["REFINE", "REDRAFT"] = "REFINE"  # REDRAFT: each "block" is a group of paragraphs
    targeted_blocks: int
    refined_blocks: int
    kept_original: int
    untouched_blocks: int
    changes: list[ChangedBlock]
    method: str = ""
    trimmed: bool = False  # long passages are shortened here to keep the record small; the change report has every word


class FormattingRule(Camel):
    label: str
    value: str


class RuleEvidence(Camel):
    rule: str
    quote: str


class FormattingResult(Camel):
    preset: str
    rules: list[FormattingRule]
    body_text_unchanged: bool
    warnings: list[str]
    evidence: list[RuleEvidence] = []  # where each rule was found in an uploaded guide
    method: str = ""


class LatexResult(Camel):
    """The LaTeX conversion (no AI). `compiled`: PaperAid compiled main.tex into main.pdf."""

    compiled: bool
    equations: int
    equations_converted: int
    figures: int
    warnings: list[str] = []


ReadinessStatus = Literal["PASS", "NEEDS_REVIEW", "MISSING", "NOT_APPLICABLE", "BLOCKED"]


class ReadinessItem(Camel):
    """One proposal requirement, answered. `basis` says who settled it: a PaperAid check, the AI's
    judgement, or a fact the student confirmed (Codex review, milestone 5)."""

    id: str
    question: str
    status: ReadinessStatus
    basis: Literal["CODE", "AI", "AUTHOR"]
    note: str = ""
    where: str = ""  # the section it concerns, when there is one
    chapter: int = 0


class ReviewFinding(Camel):
    where: str  # the section heading, or the start of the paragraph
    kind: Literal["ALIGNMENT", "EVIDENCE", "METHOD", "STRUCTURE", "TENSE", "WRITING"]
    severity: Literal["major", "moderate", "minor"]
    issue: str
    suggestion: str


class ProposalReview(Camel):
    """An uploaded proposal checked against the institution's rulebook. Nothing in it is changed."""

    rulebook: str
    level: str
    words: int
    items: list[ReadinessItem]
    findings: list[ReviewFinding]
    method: str = ""


class OutputFile(Camel):
    id: str
    label: str
    name: str
    size_bytes: int


class StoredOutput(OutputFile):
    path: str
    content_type: str


class JobFailure(Camel):
    code: str
    user_message: str
    retryable: bool


class ModelCall(Camel):
    stage: Stage
    phase: Literal["estimate", "job"] = "job"
    provider: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cache_write_tokens: int = 0
    search_calls: int = 0  # web searches made during the call (billed per search)
    latency_ms: int
    cost_usd: float
    at: datetime = Field(default_factory=utcnow)


class JobEvent(Camel):
    at: datetime = Field(default_factory=utcnow)
    label: str


class AdminAction(Camel):
    at: datetime = Field(default_factory=utcnow)
    actor: str
    action: str


class JobView(Camel):
    """What the owner's browser sees."""

    id: str
    status: JobStatus
    stage: Stage | None = None
    payment_status: PaymentStatus = PaymentStatus.NOT_REQUIRED
    selection: ServiceSelection = Field(default_factory=ServiceSelection)
    services: list[ServiceId] = []
    pipeline: list[Stage] = []
    source: FileMeta | None = None
    guideline: FileMeta | None = None
    logo: ImageMeta | None = None
    quote: Quote | None = None
    estimate: EstimateView | None = None
    billing: Billing = Field(default_factory=Billing)
    outcome: Literal["FULL", "PARTIAL"] | None = None
    warnings: list[str] = []
    analysis: AnalysisResult | None = None
    analysis_after: AnalysisResult | None = None
    protected: ProtectedSummary | None = None
    references: ReferenceVerification | None = None
    dismissed: list[str] = []  # finding ids the student dismissed in the workspace
    rejected_changes: list[str] = []  # refined passages the student chose to keep in their own words
    source_job: str | None = None  # "Fix selected": the AI Check this job fixes
    paper_checks: PaperChecks | None = None
    research: ResearchResult | None = None
    latex: LatexResult | None = None
    refinement: RefinementResult | None = None
    formatting: FormattingResult | None = None
    proposal_review: ProposalReview | None = None
    scope_words: int | None = None  # "Fix selected": the words in the chosen passages (priced by these)
    fix_notes: dict[str, list[str]] = {}  # "Fix selected": the AI Check's findings on each chosen passage
    project_id: str | None = None  # a step of a proposal project: its result is saved to the project
    outputs: list[OutputFile] = []
    failure: JobFailure | None = None
    created_at: datetime = Field(default_factory=utcnow)
    queued_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime


class Job(JobView):
    """The full server record. Never returned to browsers directly."""

    owner_uid: str
    owner_email: str
    source: StoredFile | None = None  # type: ignore[assignment]  # narrower stored variant of FileMeta
    guideline: StoredFile | None = None  # type: ignore[assignment]
    logo: StoredImage | None = None  # type: ignore[assignment]
    quote: BoundQuote | None = None  # type: ignore[assignment]
    estimate: EstimateRun | None = None  # type: ignore[assignment]
    outputs: list[StoredOutput] = []  # type: ignore[assignment]
    completed_stages: list[Stage] = []
    generation: int = 0
    attempts: int = 0
    lease_until: datetime | None = None
    cost_usd: float = 0.0  # every model call, estimate included
    estimate_cost_usd: float = 0.0
    refine_cost_usd: float = 0.0  # job-phase spend on planning, refining and auditing (scaled for partial results)
    budget_usd: float = 0.0  # provider-spend cap for the job phase: the quote's AI part / rate / multiplier
    model_calls: list[ModelCall] = []
    events: list[JobEvent] = []
    admin_actions: list[AdminAction] = []
    failure_detail: str | None = None
    files_deleted: bool = False
    deleting: bool = False  # set atomically before deletion: no new work may start on the job
    retiring: bool = False  # claimed by retention cleanup: its files are being deleted, nothing new may start
    input_sha256: str | None = None  # a proposal step: the frozen project input it was priced on

    def view(self) -> JobView:
        return JobView.model_validate(self.model_dump())

    def storage_prefix(self) -> str:
        return f"users/{self.owner_uid}/jobs/{self.id}"


class AdminJob(Camel):
    job: JobView
    owner_email: str
    cost_usd: float
    duration_sec: int | None
    model_calls: list[ModelCall]
    events: list[JobEvent]
    admin_actions: list[AdminAction]
    failure_detail: str | None


class AdminSummary(Camel):
    jobs24h: int = Field(alias="jobs24h")
    active: int
    queued: int
    completion_rate: float
    failures24h: int = Field(alias="failures24h")
    spend24h_usd: float = Field(alias="spend24hUsd")
    processing_enabled: bool = True


class Page[T](Camel):
    items: list[T]
    next_cursor: str | None = None
