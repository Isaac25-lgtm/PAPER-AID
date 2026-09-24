"""PaperAid's permanent two-model algorithm.

Two fixed roles (models are configuration; the roles and their order are not):
  lead   (GPT-6 Sol)       analyses, drafts the plan, finalises it, reviews the result
  writer (Claude Opus 5.5) critiques the draft plan, writes the result, fixes what the review raises

Refinement:
  1. lead analyses the paper and flags passages that read as AI-generated        (ANALYSING)
  2. lead drafts a refinement plan for the flagged passages                        (PLANNING)
  3. writer critiques the draft plan, passage by passage                          (PLANNING)
  4. lead weighs the critique and writes the final plan                           (PLANNING)
  5. writer rewrites the passages following the final plan                        (REFINING)
  6. lead reviews the rewrite once; writer fixes anything raised (bounded rounds) (AUDITING)

University template formatting follows the same loop, with the formatting rules as the thing
being planned: lead drafts rules from the guide → writer critiques → lead finalises → code
applies them to the paper (wording can never change) → lead reviews the applied rules → writer
fixes the rules → code re-applies. See app/jobs/pipeline.py.

Deterministic checks run alongside the models and cost nothing: locked citations and numbers
are verified on every rewrite, and formatting is proven not to change a word.

Spend guarantees:
- Usage is recorded the moment a response arrives, before it is parsed, so a malformed or
  truncated reply is still costed.
- Every response that passes schema validation is saved under a fingerprint of its request. A
  retry after a crash reuses it instead of paying for the same call again; an invalid response is
  never saved, so a retry asks the model again. The remaining window is the network call itself.
- A response cut off by the output limit is not retried as-is: the batch is split in half; a
  single passage that still does not fit is left unchanged.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

from app.ai import costs
from app.ai.providers import UNAVAILABLE, ModelResult, parse, provider_for
from app.core.config import Settings
from app.core.errors import PermanentStageError, RetryableStageError
from app.documents import protect
from app.formatting.guideline import SPEC_SCHEMA
from app.jobs.models import ModelCall, Stage

PROMPTS = {p.stem: p.read_text(encoding="utf-8") for p in (Path(__file__).parent / "prompts").glob("*.md")}
BATCH_WORDS = 1500
NOT_RETURNED = "NOT_RETURNED"  # the writer gave no rewrite for a planned passage

Role = Literal["lead", "writer"]


@dataclass(frozen=True)
class Step:
    role: Role
    stage: Stage
    prompt: str
    max_tokens: int


# The algorithm, in one place: which role performs each step.
STEPS: dict[str, Step] = {
    "analyse": Step("lead", Stage.ANALYSING, "analyse-v1", 12000),
    "plan": Step("lead", Stage.PLANNING, "plan-v1", 12000),
    "critique": Step("writer", Stage.PLANNING, "critique-v1", 8000),
    "finalise": Step("lead", Stage.PLANNING, "finalise-v1", 12000),
    "refine": Step("writer", Stage.REFINING, "refine-v2", 16000),
    "review": Step("lead", Stage.AUDITING, "review-v1", 8000),
    "repair": Step("writer", Stage.AUDITING, "repair-v2", 16000),
    "spec_plan": Step("lead", Stage.FORMATTING, "spec-plan-v1", 8000),
    "spec_critique": Step("writer", Stage.FORMATTING, "spec-critique-v1", 6000),
    "spec_finalise": Step("lead", Stage.FORMATTING, "spec-finalise-v1", 8000),
    "spec_review": Step("lead", Stage.FORMATTING, "spec-review-v1", 6000),
    "spec_fix": Step("writer", Stage.FORMATTING, "spec-fix-v1", 8000),
}

REASONS = ["GENERIC_PHRASING", "UNIFORM_STRUCTURE", "LOW_SPECIFICITY", "FORMULAIC_TRANSITIONS", "OVER_HEDGING", "UNSUPPORTED_SUMMARY"]
REVIEW_ISSUES = ["MEANING_DRIFT", "NUMBER_CHANGED", "CITATION_LOST", "INVENTED_CLAIM", "BROKEN_TRANSITION", "VOICE_SHIFT", "INSTRUCTION_NOT_FOLLOWED"]


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _list_of(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item}


_STR, _BOOL = {"type": "string"}, {"type": "boolean"}
_TEXT_BLOCKS = _obj({"blocks": _list_of(_obj({"id": _STR, "text": _STR}))})
_ANALYSIS = _obj(
    {
        "blocks": _list_of(
            _obj(
                {
                    "id": _STR,
                    "riskBand": {"type": "string", "enum": ["low", "moderate", "high"]},
                    "reasons": _list_of({"type": "string", "enum": REASONS}),
                    "explanation": _STR,
                    "suggestion": _STR,
                    "excerpt": _STR,
                }
            )
        )
    }
)
_PLAN = _obj({"blocks": _list_of(_obj({"id": _STR, "action": {"type": "string", "enum": ["rewrite", "leave"]}, "instruction": _STR, "preserve": _STR}))})
_CRITIQUE = _obj({"blocks": _list_of(_obj({"id": _STR, "agree": _BOOL, "comment": _STR})), "overall": _STR})
_REVIEW = _obj({"results": _list_of(_obj({"id": _STR, "pass": _BOOL, "issues": _list_of({"type": "string", "enum": REVIEW_ISSUES}), "note": _STR}))})
_SPEC_CRITIQUE = _obj({"items": _list_of(_obj({"field": _STR, "current": _STR, "proposed": _STR, "quote": _STR})), "overall": _STR})
_SPEC_REVIEW = _obj({"pass": _BOOL, "problems": _list_of(_obj({"field": _STR, "problem": _STR, "fix": _STR}))})


class _TextBlock(BaseModel):
    id: str
    text: str


class _TextBlocks(BaseModel):
    blocks: list[_TextBlock]


class _AnalysisBlock(BaseModel):
    id: str
    riskBand: str
    reasons: list[str]
    explanation: str
    suggestion: str
    excerpt: str


class _Analysis(BaseModel):
    blocks: list[_AnalysisBlock]


class PlanItem(BaseModel):
    id: str
    action: Literal["rewrite", "leave"]
    instruction: str
    preserve: str = ""


class _Plan(BaseModel):
    blocks: list[PlanItem]


class CritiqueItem(BaseModel):
    id: str
    agree: bool
    comment: str


class _Critique(BaseModel):
    blocks: list[CritiqueItem]
    overall: str = ""


class _ReviewResult(BaseModel):
    id: str
    passed: bool
    issues: list[str]
    note: str


class _Review(BaseModel):
    results: list[dict[str, Any]]


class _Margins(BaseModel):
    top: float
    bottom: float
    left: float
    right: float


class _Heading(BaseModel):
    size_pt: float
    bold: bool
    italic: bool
    align: Literal["left", "center"]


class _SpecAnswer(BaseModel):
    """Mirrors SPEC_SCHEMA exactly, so an incomplete answer is a retryable malformed response."""

    margins_cm: _Margins
    font: str
    size_pt: float
    line_spacing: float
    first_line_indent_cm: float
    space_after_pt: float
    alignment: Literal["left", "justify"]
    paper_size: Literal["A4", "Letter"]
    heading1: _Heading
    heading2: _Heading
    heading3: _Heading
    page_numbers: Literal["top-right", "top-center", "bottom-center", "bottom-right"]
    roman_preliminary_pages: bool
    references_hanging_cm: float
    references_line_spacing: float
    insert_toc: bool
    evidence: list[dict[str, str]]
    conflicts: list[str]
    assumptions: list[str]
    unsupported: list[str]


class _SpecCritique(BaseModel):
    items: list[dict[str, str]]
    overall: str = ""


class _SpecReview(BaseModel):
    model_config = {"populate_by_name": True}

    passed: bool = Field(alias="pass")
    problems: list[dict[str, str]] = []


class ResponseCache(Protocol):
    def get(self, key: str) -> str | None: ...
    def put(self, key: str, text: str) -> None: ...


@dataclass
class Target:
    id: str
    section: str
    masked: str  # ⟦Xn⟧ and ⟦Pn⟧ tokens in place
    before: str = ""  # neighbouring text, context only
    after: str = ""
    findings: list[str] = field(default_factory=list)
    instruction: str = ""
    preserve: str = ""


@dataclass
class Revision:
    id: str
    original: str
    revised: str
    problems: list[str]


@dataclass
class Negotiation:
    """The full plan trail, kept for the change report and admin diagnostics."""

    draft: dict[str, PlanItem]
    critique: dict[str, CritiqueItem]
    final: dict[str, PlanItem]
    critique_overall: str = ""


class AIRunner:
    """One per job stage. `record` persists each paid call immediately; `spent` reads the job's
    running total, so retries count against the same budget."""

    def __init__(
        self,
        settings: Settings,
        record: Callable[[ModelCall], None],
        spent: Callable[[], float],
        budget: float,
        cache: ResponseCache | None = None,
        heartbeat: Callable[[], None] | None = None,
        phase: Literal["estimate", "job"] = "job",
    ):
        self.settings = settings
        self._phase = phase
        self._record = record
        self._spent = spent
        self._budget = budget
        self._cache = cache
        # Called before every paid call: renews the stage's lease and may hand the rest of the stage
        # to a fresh delivery (which replays the calls already made from the cache, at no cost).
        self._heartbeat = heartbeat or (lambda: None)

    def model_for(self, task: str) -> str:
        return self.settings.lead_model if STEPS[task].role == "lead" else self.settings.writer_model

    def _call[T: BaseModel](self, task: str, payload: dict[str, Any], schema: dict[str, Any], shape: type[T]) -> T | None:
        """Returns the schema-validated answer, or None when the response was cut off. Only answers
        that passed validation are cached, so a retry never replays a bad response."""
        step = STEPS[task]
        model_ref = self.model_for(task)
        system = PROMPTS[step.prompt]
        key = hashlib.sha256(json.dumps([task, model_ref, system, payload], sort_keys=True).encode()).hexdigest()[:40]
        cached = self._cache.get(key) if self._cache else None
        if cached is not None:
            try:
                return shape.model_validate(parse(cached, task))
            except (RetryableStageError, ValidationError):
                pass  # an unusable saved answer is ignored and the call is made again

        self._heartbeat()
        provider, model = provider_for(model_ref, self.settings)
        prices = self.settings.model_prices
        estimate = costs.estimate_usd(provider.name, model, len(system) + len(json.dumps(payload)), step.max_tokens, prices)
        costs.ensure_within_budget(self._spent(), estimate, self._budget)
        result: ModelResult = provider.json(task, model, system, payload, schema, step.max_tokens)
        u = result.usage
        self._record(
            ModelCall(
                stage=step.stage,
                phase=self._phase,
                provider=result.provider,
                model=result.model,
                prompt_version=step.prompt,
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cached_tokens=u.cached_tokens,
                latency_ms=u.latency_ms,
                cost_usd=costs.cost_usd(result.provider, result.model, u.input_tokens, u.output_tokens, u.cached_tokens, prices),
            )
        )
        if result.stop == "refusal":
            raise PermanentStageError("MODEL_REFUSED", "We couldn't process this document with our AI provider.", f"{result.provider} refusal on {task}")
        if result.stop == "max_tokens":
            return None
        validated = self._validated(shape, parse(result.text, task), task)
        if self._cache:
            self._cache.put(key, result.text)
        return validated

    def _batched[T: BaseModel](
        self, task: str, items: list[dict[str, Any]], wrap: Callable[[list[dict[str, Any]]], dict[str, Any]], schema: dict[str, Any], shape: type[T]
    ) -> list[T]:
        """Run `items` in word-bounded batches; halve any batch whose answer was cut off."""
        responses: list[T] = []
        pending = _batches(items)
        while pending:
            batch = pending.pop(0)
            answer = self._call(task, wrap([{k: v for k, v in i.items() if k != "_words"} for i in batch]), schema, shape)
            if answer is not None:
                responses.append(answer)
            elif len(batch) > 1:
                middle = len(batch) // 2
                pending[:0] = [batch[:middle], batch[middle:]]
            # A single item that cannot fit is skipped; callers treat a missing answer safely.
        return responses

    @staticmethod
    def _validated[T: BaseModel](model: type[T], data: dict[str, Any], task: str) -> T:
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise RetryableStageError("MALFORMED_OUTPUT", UNAVAILABLE, f"schema mismatch on {task}") from exc

    # --- 1. analysis (lead) ------------------------------------------------------------

    def analyse(self, blocks: list[tuple[str, str]], outline: list[str]) -> dict[str, _AnalysisBlock]:
        """The lead's judgement per passage. Returns {block_id: result}."""
        if not blocks:
            return {}
        known = {bid for bid, _ in blocks}
        items = [{"id": bid, "text": text, "_words": text} for bid, text in blocks]
        results: dict[str, _AnalysisBlock] = {}
        for answer in self._batched("analyse", items, lambda b: {"outline": outline, "blocks": b}, _ANALYSIS, _Analysis):
            for item in answer.blocks:
                if item.id in known:  # unknown IDs from a model are discarded, never trusted
                    results[item.id] = item
        return results

    # --- 2–4. plan: lead drafts, writer critiques, lead finalises -----------------------

    @staticmethod
    def _plan_base(targets: list[Target]) -> list[dict[str, Any]]:
        return [{"id": t.id, "section": t.section, "text": t.masked, "findings": t.findings, "_words": t.masked} for t in targets]

    def draft_plan(self, targets: list[Target], outline: list[str]) -> dict[str, PlanItem]:
        """Step 2 alone: the lead's draft plan. The refinement estimate runs exactly this call, so
        the job that follows replays it from the cache instead of paying for it again."""
        known = {t.id for t in targets}
        draft: dict[str, PlanItem] = {}
        for answer in self._batched("plan", self._plan_base(targets), lambda b: {"outline": outline, "passages": b}, _PLAN, _Plan):
            draft.update({p.id: p for p in answer.blocks if p.id in known})
        return draft

    def negotiate_plan(self, targets: list[Target], outline: list[str]) -> Negotiation:
        base = self._plan_base(targets)
        draft = self.draft_plan(targets, outline)

        # The whole plan is critiqued, "leave" decisions included: the writer may argue a passage
        # the lead left alone does need work. A passage the lead omitted has no plan and is left.
        with_draft = [{**item, "draft": draft[item["id"]].model_dump(exclude={"id"})} for item in base if item["id"] in draft]
        planned = {item["id"] for item in with_draft}
        critique: dict[str, CritiqueItem] = {}
        overall = []
        for answer in self._batched("critique", with_draft, lambda b: {"passages": b}, _CRITIQUE, _Critique):
            critique.update({c.id: c for c in answer.blocks if c.id in planned})
            overall.append(answer.overall)

        with_critique = [
            {**item, "critique": critique[item["id"]].model_dump(exclude={"id"}) if item["id"] in critique else None} for item in with_draft
        ]
        final: dict[str, PlanItem] = {}
        for answer in self._batched("finalise", with_critique, lambda b: {"outline": outline, "passages": b}, _PLAN, _Plan):
            final.update({p.id: p for p in answer.blocks if p.id in planned})  # only passages the writer saw
        for item in with_draft:  # a passage the lead dropped from the final plan keeps its draft instruction
            final.setdefault(item["id"], draft[item["id"]])
        return Negotiation(draft=draft, critique=critique, final=final, critique_overall=" ".join(o for o in overall if o))

    # --- 5. write (writer) -------------------------------------------------------------

    def refine(self, targets: list[Target], outline: list[str]) -> list[Revision]:
        by_id = {t.id: t for t in targets}
        items = [
            {"id": t.id, "section": t.section, "instruction": t.instruction, "preserve": t.preserve, "before": t.before, "text": t.masked, "after": t.after, "_words": t.masked}
            for t in targets
        ]
        returned: dict[str, str] = {}
        for answer in self._batched("refine", items, lambda b: {"outline": outline, "blocks": b}, _TEXT_BLOCKS, _TextBlocks):
            returned.update({b.id: b.text for b in answer.blocks if b.id in by_id})
        revisions = []
        for t in targets:
            if t.id not in returned:  # omitted, or did not fit even alone: reported as kept original
                revisions.append(Revision(t.id, t.masked, t.masked, [NOT_RETURNED]))
                continue
            revised = returned[t.id]
            revisions.append(Revision(t.id, t.masked, revised, protect.check_rewrite(t.masked, revised) if revised != t.masked else []))
        return revisions

    # --- 6. review (lead) and fix (writer) --------------------------------------------------

    def review(self, revisions: list[Revision], instructions: dict[str, str]) -> dict[str, list[str]]:
        """The lead's review of changed passages. Returns {block_id: issues}; empty list = pass."""
        changed = [r for r in revisions if r.revised != r.original and not r.problems]
        items = [
            {"id": r.id, "original": r.original, "revised": r.revised, "instruction": instructions.get(r.id, ""), "_words": r.original + " " + r.revised}
            for r in changed
        ]
        verdicts: dict[str, list[str]] = {}
        ids = {r.id for r in changed}
        for answer in self._batched("review", items, lambda b: {"pairs": b}, _REVIEW, _Review):
            for raw in answer.results:
                result = _ReviewResult(id=str(raw.get("id")), passed=bool(raw.get("pass")), issues=list(raw.get("issues") or []), note=str(raw.get("note") or ""))
                if result.id in ids:
                    verdicts[result.id] = [] if result.passed else (result.issues or ["MEANING_DRIFT"]) + ([f"NOTE: {result.note}"] if result.note else [])
        for r in changed:  # a passage the reviewer skipped (or that could not fit) is not a pass
            verdicts.setdefault(r.id, ["NOT_REVIEWED"])
        return verdicts

    def repair(self, failed: list[tuple[Revision, list[str]]], instructions: dict[str, str]) -> list[Revision]:
        items = [
            {"id": r.id, "original": r.original, "rejected": r.revised, "instruction": instructions.get(r.id, ""), "objections": issues, "_words": r.original}
            for r, issues in failed
        ]
        returned: dict[str, str] = {}
        for answer in self._batched("repair", items, lambda b: {"blocks": b}, _TEXT_BLOCKS, _TextBlocks):
            returned.update({b.id: b.text for b in answer.blocks if b.id in {r.id for r, _ in failed}})
        out = []
        for r, _ in failed:
            revised = returned.get(r.id, r.original)
            out.append(Revision(r.id, r.original, revised, protect.check_rewrite(r.original, revised) if revised != r.original else []))
        return out

    # --- template formatting: the same loop over formatting rules --------------------------

    def _spec(self, task: str, payload: dict[str, Any], shape: type[BaseModel], schema: dict[str, Any]) -> dict[str, Any]:
        answer = self._call(task, payload, schema, shape)
        if answer is None:
            raise RetryableStageError("OUTPUT_TRUNCATED", UNAVAILABLE, f"formatting rules did not fit on {task}")
        return answer.model_dump(by_alias=True)

    def negotiate_spec(self, guide: str) -> dict[str, Any]:
        """Lead drafts rules from the guide → writer critiques → lead finalises. Returns the final
        spec answer (SPEC_SCHEMA shape) plus the trail under '_trail'."""
        draft = self._spec("spec_plan", {"guide": guide}, _SpecAnswer, SPEC_SCHEMA)
        critique = self._spec("spec_critique", {"guide": guide, "draft": draft}, _SpecCritique, _SPEC_CRITIQUE)
        final = self._spec("spec_finalise", {"guide": guide, "draft": draft, "review": critique}, _SpecAnswer, SPEC_SCHEMA)
        return {**final, "_trail": {"draft": draft, "critique": critique}}

    def review_spec(self, guide: str, applied: dict[str, Any]) -> list[dict[str, str]]:
        """Lead reviews the rules as actually applied. Returns problems; empty = pass."""
        answer = self._call("spec_review", {"guide": guide, "applied": applied}, _SPEC_REVIEW, _SpecReview)
        if answer is None:
            return [{"field": "review", "problem": "The review could not be completed.", "fix": ""}]
        return [] if answer.passed else (answer.problems or [{"field": "review", "problem": "Rejected without details.", "fix": ""}])

    def fix_spec(self, guide: str, spec: dict[str, Any], problems: list[dict[str, str]]) -> dict[str, Any]:
        return self._spec("spec_fix", {"guide": guide, "spec": spec, "problems": problems}, _SpecAnswer, SPEC_SCHEMA)


def _batches(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    words = 0
    for item in items:
        n = len(str(item.get("_words", item.get("text", ""))).split())
        if current and words + n > BATCH_WORDS:
            batches.append(current)
            current, words = [], 0
        current.append(item)
        words += n
    if current:
        batches.append(current)
    return batches
