"""The Gemini workflow (owner decision 2026-10-07): which stage each AI step belongs to, which
verified Vertex model and thinking level each stage uses, and what each model can do.

PaperAid's pipelines decide what happens; this module only says who executes each step. A quote
freezes the resolved routes (orchestration.freeze_vertex), so changing a model or a thinking level
here or in Settings never changes a job that was already priced.
"""

import math
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.errors import PermanentStageError

if TYPE_CHECKING:
    from app.core.config import Settings


class Capability(StrEnum):
    JSON = "structured_json"
    WRITING = "long_form_generation"
    REASONING = "reasoning"
    SEARCH = "google_search_grounding"
    LARGE_CONTEXT = "large_context"
    DOCUMENTS = "multimodal_documents"
    IMAGES = "image_understanding"
    AUDIO = "audio_understanding"
    TOOLS = "function_calling"


IMPLEMENTED = frozenset({Capability.JSON, Capability.WRITING, Capability.REASONING, Capability.SEARCH, Capability.LARGE_CONTEXT})

Thinking = Literal["MINIMAL", "LOW", "MEDIUM", "HIGH"]
# Gemini counts thinking against max_output_tokens (live check 2026-10-07: 111 thinking + 5 visible
# tokens hit a 120-token limit). Each step keeps its visible allowance and gets this much more: a live
# academic review at HIGH thought 30,721 tokens for a 292-token answer. Only what is used is billed.
THINKING_ROOM: dict[str, int] = {"MINIMAL": 2_000, "LOW": 6_000, "MEDIUM": 16_000, "HIGH": 32_000}

# The stages of the Gemini workflow. second_check is the independent second opinion the AI check
# has always had (two assessors per passage): a different model, so it is not the same view twice.
STAGES = ("intake", "planner", "research", "execution", "first_audit", "second_check", "premium_audit", "fix", "final_signoff",
          "topics", "final_editor")
Stage = Literal["intake", "planner", "research", "execution", "first_audit", "second_check", "premium_audit", "fix", "final_signoff",
                "topics", "final_editor"]

TASK_STAGES: dict[str, str] = {}
for _stage, _tasks in {
    "intake": "w_read claims",
    "planner": "plan finalise p_plan p_brief p_finalise p_needs w_needs w_plan w_results spec_plan spec_finalise p_profile p_profile_finalise",
    "research": "research p_search w_search p_extract w_extract",
    "execution": "refine redraft p_draft w_draft w_compress d_report d_chapter4 q_code q_themes",
    "first_audit": ("analyse analyse_after academic verify w_verify w_integrity w_evaluate w_flag p_flag p_readiness critique p_critique spec_critique "
                    "p_profile_critique review_peer spec_review_peer p_plan_review_peer p_review_peer p_profile_review_peer"),
    "second_check": "analyse_peer analyse_after_peer",
    "premium_audit": ("review p_review p_plan_review p_profile_review spec_review w_plan_review w_results_review w_final d_report_review q_review "
                      "p_audit w_adjudicate guide spec_guide p_guide p_profile_guide"),
    "fix": "repair redraft_fix p_fix w_repair spec_fix",
    "final_editor": "w_edit w_resolve p_edit p_resolve",
}.items():
    TASK_STAGES.update(dict.fromkeys(_tasks.split(), _stage))

# Approval reviews that run in PaperAid's bounded review → targeted repair → review loops. The first
# round is the premium audit; every later round (after a repair) is the lighter final sign-off,
# which checks the earlier findings were resolved and nothing broke (AIRunner.audit_rounds).
SIGNOFF_TASKS = frozenset({"review", "p_review", "p_plan_review", "p_profile_review", "spec_review",
                           "w_plan_review", "w_results_review", "w_final", "d_report_review", "q_review"})
SEARCH_TASKS = frozenset({"research", "p_search", "w_search"})


# Workflow 2 (algorithm revision 2026-10-09): choosing research topics is a stage of its own.
WORKFLOW_STAGES: dict[int, dict[str, str]] = {2: {"w_needs": "topics", "p_needs": "topics"}}


def stage_for(task: str, tier: str = "STANDARD", workflow: int = 1) -> str:
    """A premium works tier has its section evaluation done by the premium auditor."""
    if task not in TASK_STAGES:
        raise PermanentStageError("AI_TASK_UNCONFIGURED", "This AI task is not configured.", f"unknown task {task}")
    if workflow >= 2 and task in WORKFLOW_STAGES[2]:
        return WORKFLOW_STAGES[2][task]
    return "premium_audit" if task == "w_evaluate" and tier == "PREMIUM" else TASK_STAGES[task]


class GeminiModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    capabilities: frozenset[Capability]
    evidence: str = Field(min_length=1)
    max_output_tokens: int = Field(gt=0)
    context_tokens: int = Field(gt=0)
    thinking_levels: frozenset[str] = frozenset()
    thinking_budget_range: tuple[int, int] | None = None


class GroundingPrice(BaseModel):
    """Google Search grounding, as published. PaperAid charges every query at the rate above the free
    monthly allowance: the allowance is shared by the whole billing account, so no job can count on it."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    source: str = Field(min_length=1)
    free_queries_per_month: int = Field(ge=0)
    allowance_scope: str
    excess_usd_per_1000_queries: float = Field(ge=0, allow_inf_nan=False)
    billing_unit: Literal["individual_query"] = "individual_query"
    grounding_input_tokens_charged: Literal[False] = False

    @property
    def per_query_usd(self) -> float:
        return self.excess_usd_per_1000_queries / 1000


def pricing_date() -> date:
    """Effective dates use UTC, independent of a developer machine's time zone."""
    return datetime.now(UTC).date()


class VertexPrice(BaseModel):
    """Verified rates (USD per million tokens) or a dated schedule. Freezing selects one flat record.

    Output rates include thinking tokens. Models priced in two context tiers (Gemini Pro) carry the
    rates for requests above `long_context_tokens` input tokens; the whole request is billed at them.
    Additional units are USD per unit, e.g. google_search_query (not per thousand).
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: Literal["UNVERIFIED", "VERIFIED"] = "UNVERIFIED"
    source: str = ""
    input: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    cached: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    long_context_tokens: int | None = Field(default=None, gt=0)
    long_input: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    long_output: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    long_cached: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    units: dict[str, float] = {}
    effective_from: date | None = None
    effective_until: date | None = None  # inclusive
    verified_on: date | None = None
    location: str = ""
    service_tier: Literal["standard"] = "standard"
    output_includes_thinking: Literal[True] = True
    pricing_note: str = ""
    grounding: GroundingPrice | None = None
    schedule: tuple["VertexPrice", ...] = ()

    def covers(self, on: date | None = None) -> bool:
        today = on or pricing_date()
        return ((self.effective_from is None or self.effective_from <= today) and
                (self.effective_until is None or today <= self.effective_until))

    def at(self, on: date | None = None) -> "VertexPrice":
        # A flat record is already frozen; never reprice it at execution time.
        if not self.schedule:
            return self
        today = on or pricing_date()
        for record in self.schedule:
            if record.covers(today):
                return record
        return VertexPrice(source=self.source)

    @model_validator(mode="after")
    def verified(self) -> "VertexPrice":
        if any(not math.isfinite(v) or v < 0 for v in self.units.values()):
            raise ValueError("Vertex unit prices must be finite and non-negative")
        if self.status == "VERIFIED" and (not self.source.strip() or None in (self.input, self.output, self.cached)):
            raise ValueError("VERIFIED Vertex pricing needs a source and all three token rates")
        long = (self.long_context_tokens, self.long_input, self.long_output, self.long_cached)
        if any(v is not None for v in long) and None in long:
            raise ValueError("A long-context tier needs its threshold and all three rates")
        if self.effective_until and (not self.effective_from or self.effective_until < self.effective_from):
            raise ValueError("Invalid Vertex price period")
        previous = None
        for record in self.schedule:
            if record.schedule or not record.effective_from or record.status != "VERIFIED":
                raise ValueError("Vertex schedules need flat, verified, dated records")
            if previous and (previous.effective_until is None or record.effective_from <= previous.effective_until):
                raise ValueError("Vertex price periods overlap or are unordered")
            previous = record
        return self


_TEXT_MODEL = frozenset({Capability.JSON, Capability.WRITING, Capability.REASONING, Capability.SEARCH,
                         Capability.LARGE_CONTEXT, Capability.DOCUMENTS, Capability.IMAGES, Capability.AUDIO, Capability.TOOLS})
_CARDS = "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/"

# Models verified in project `paperaid` (publisher model lookup) and on Google's model cards,
# 2026-10-07. Thinking levels are the ones each card documents and a live call accepted.
CONFIRMED_MODELS = {
    "gemini-3.8-flash": GeminiModel(capabilities=_TEXT_MODEL, evidence=_CARDS + "3-8-flash", max_output_tokens=65_536,
                                    context_tokens=1_048_576, thinking_levels=frozenset({"LOW", "MEDIUM", "HIGH"})),
    "gemini-3.5-flash-lite": GeminiModel(capabilities=_TEXT_MODEL, evidence=_CARDS + "3-5-flash-lite", max_output_tokens=65_536,
                                         context_tokens=1_048_576, thinking_levels=frozenset({"MINIMAL", "LOW", "MEDIUM", "HIGH"})),
    # Public preview: the premium auditor stays configurable (PREMIUM_AUDIT_MODEL). gemini-3.5-pro answers
    # in Vertex but has no published price, so it cannot be priced or used (2026-10-07).
    "gemini-3.1-pro-preview": GeminiModel(capabilities=_TEXT_MODEL, evidence=_CARDS + "3-1-pro", max_output_tokens=65_536,
                                          context_tokens=1_048_576, thinking_levels=frozenset({"LOW", "MEDIUM", "HIGH"})),
}


def required(task: str, search: bool = False) -> frozenset[Capability]:
    stage = stage_for(task)
    needs = {Capability.JSON}
    if stage in ("execution", "fix", "planner"):
        needs.add(Capability.WRITING)
    if stage in ("planner", "first_audit", "second_check", "premium_audit", "final_signoff"):
        needs.add(Capability.REASONING)
    if search or task in SEARCH_TASKS:
        needs.add(Capability.SEARCH)
    return frozenset(needs)


def check_model(model: str, needs: frozenset[Capability], models: dict[str, GeminiModel], *,
                implemented: frozenset[Capability] = IMPLEMENTED) -> GeminiModel:
    spec = models.get(model)
    if spec is None:
        raise PermanentStageError("GEMINI_MODEL_UNVERIFIED", "This AI model has not been configured.", f"vertex model {model} absent from registry")
    missing = needs - spec.capabilities
    if missing:
        raise PermanentStageError("AI_CAPABILITY_UNSUPPORTED", "The configured AI model cannot perform this task.", ",".join(sorted(missing)))
    if needs - implemented:
        raise PermanentStageError("AI_SERVICE_UNIMPLEMENTED", "This AI capability is not available yet.", ",".join(sorted(needs - implemented)))
    return spec


def stage_route(settings: "Settings", stage: str, task: str) -> tuple[list[str], str]:
    """The stage's model, then its configured fallback stages' models (deduplicated), each checked for
    the task's capabilities and the stage's thinking level. Returns (vertex refs, thinking level)."""
    if stage not in STAGES:
        raise PermanentStageError("AI_ROLE_UNCONFIGURED", "This AI role is not configured.", stage)
    thinking = getattr(settings, stage + "_thinking")
    models = [getattr(settings, s + "_model") for s in (stage, *settings.gemini_fallbacks.get(stage, []))]
    if not all(models):
        raise PermanentStageError("AI_ROLE_UNCONFIGURED", "This AI role is not configured.", stage)
    models = list(dict.fromkeys(models))
    for name in models:
        spec = check_model(name, required(task), settings.paperaid_gemini_models)
        if thinking not in spec.thinking_levels:
            raise PermanentStageError("AI_CAPABILITY_UNSUPPORTED", "The configured AI model cannot perform this task.",
                                      f"thinking {thinking} not verified for {name}")
    return ["vertex:" + name for name in models], thinking
