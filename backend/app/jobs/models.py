"""Job contracts. Field names serialise to camelCase to match web/src/lib/types.ts exactly."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


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
    PLANNING = "PLANNING"
    REFINING = "REFINING"
    REDRAFTING = "REDRAFTING"
    FORMATTING = "FORMATTING"
    AUDITING = "AUDITING"
    EXPORTING = "EXPORTING"


class PaymentStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    BETA_BYPASS = "BETA_BYPASS"
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


Band = Literal["LOW", "MODERATE", "HIGH"]
Confidence = Literal["LOW", "MEDIUM", "HIGH"]
ReasonCode = Literal[
    "GENERIC_PHRASING", "UNIFORM_STRUCTURE", "LOW_SPECIFICITY", "FORMULAIC_TRANSITIONS", "OVER_HEDGING", "UNSUPPORTED_SUMMARY"
]


class ServiceSelection(Camel):
    writing: Literal["NONE", "AI_CHECK", "REFINE", "REDRAFT"] = "NONE"
    intensity: Literal["LIGHT", "STANDARD"] = "STANDARD"
    formatting: Literal["NONE", "FORMAT", "TEMPLATE_FORMAT"] = "NONE"
    preset: str = "apa7"
    latex: bool = False

    def services(self) -> list[ServiceId]:
        ids = []
        if self.writing != "NONE":
            ids.append(ServiceId(self.writing))
        if self.formatting != "NONE":
            ids.append(ServiceId(self.formatting))
        if self.latex:
            ids.append(ServiceId.LATEX)
        return ids


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


class Quote(Camel):
    id: str
    currency: Literal["UGX"] = "UGX"
    lines: list[QuoteLine]
    amount: int
    pricing_version: str
    expires_at: datetime


class BoundQuote(Quote):
    """The server copy of a quote, bound to the exact file and selection that were priced."""

    selection: ServiceSelection
    source_sha256: str
    guideline_sha256: str | None = None
    word_count: int


class Finding(Camel):
    id: str
    block_id: str
    section: str
    reason: ReasonCode
    severity: Literal["minor", "moderate", "major"]
    excerpt: str
    explanation: str
    suggestion: str


class AnalysisResult(Camel):
    band: Band
    confidence: Confidence
    analysed_words: int
    excluded_words: int
    findings: list[Finding]
    algorithm_version: str
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
    targeted_blocks: int
    refined_blocks: int
    kept_original: int
    untouched_blocks: int
    changes: list[ChangedBlock]
    method: str = ""


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
    provider: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
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
    quote: Quote | None = None
    outcome: Literal["FULL", "PARTIAL"] | None = None
    warnings: list[str] = []
    analysis: AnalysisResult | None = None
    analysis_after: AnalysisResult | None = None
    refinement: RefinementResult | None = None
    formatting: FormattingResult | None = None
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
    quote: BoundQuote | None = None  # type: ignore[assignment]
    outputs: list[StoredOutput] = []  # type: ignore[assignment]
    completed_stages: list[Stage] = []
    generation: int = 0
    attempts: int = 0
    lease_until: datetime | None = None
    cost_usd: float = 0.0
    budget_usd: float = 0.0
    model_calls: list[ModelCall] = []
    events: list[JobEvent] = []
    admin_actions: list[AdminAction] = []
    failure_detail: str | None = None
    files_deleted: bool = False

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
