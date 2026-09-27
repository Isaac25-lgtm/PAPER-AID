"""PaperAid's permanent two-model algorithm.

Two fixed roles (models are configuration; the roles and their order are not):
  lead   (GPT-6 Sol)       analyses, drafts the plan, finalises it, reviews the result
  writer (Claude Opus 5.5) critiques the draft plan, writes the result, fixes what the review raises

Refinement (the revised algorithm, adopted 2026-09-27):
  1. code measures writing signals; lead confirms or rejects each in context,
     finds what the rules missed and marks passages to preserve                    (ANALYSING)
  2. lead drafts a refinement plan in the student's chosen style                    (PLANNING)
  3. writer critiques the draft plan, passage by passage                          (PLANNING)
  4. lead weighs the critique and writes the final plan                           (PLANNING)
  5. writer rewrites the passages following the final plan                        (REFINING)
  6. code rechecks every rewrite (locked items, numbers, notes) and re-measures
     its signals; lead reviews each rewrite with that post-scan and the passages
     linked to it, grading PASS / PASS_WITH_WARNINGS / REPAIR; writer fixes what
     is raised and the lead reviews the fix again (bounded rounds)                  (AUDITING)

Source check (optional, with AI Check or Refine):
  a. lead picks the paper's important factual claims and a safe search query for each (RESEARCHING)
  b. code drops any claim built on the paper's own results and any unsafe query
  c. lead searches the live web for each claim; code keeps only sources the search opened
  d. writer checks, without searching, whether each quoted passage supports its claim
     (population, place, period); disagreement makes the claim UNCERTAIN              (RESEARCHING)

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

from pydantic import BaseModel, Field, StrictBool, ValidationError

from app.ai import costs
from app.ai.providers import UNAVAILABLE, ModelResult, parse, provider_for
from app.analysis import research
from app.core.config import Settings
from app.core.errors import PermanentStageError, RetryableStageError
from app.documents import protect
from app.formatting.guideline import SPEC_SCHEMA
from app.jobs.models import Engine, ModelCall, Stage

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
    "analyse": Step("lead", Stage.ANALYSING, "analyse-v2", 12000),
    "plan": Step("lead", Stage.PLANNING, "plan-v2", 12000),
    "critique": Step("writer", Stage.PLANNING, "critique-v2", 8000),
    "finalise": Step("lead", Stage.PLANNING, "finalise-v2", 12000),
    "refine": Step("writer", Stage.REFINING, "refine-v3", 16000),
    "review": Step("lead", Stage.AUDITING, "review-v2", 8000),
    "repair": Step("writer", Stage.AUDITING, "repair-v3", 16000),
    "claims": Step("lead", Stage.RESEARCHING, "claims-v1", 6000),
    "research": Step("lead", Stage.RESEARCHING, "research-v1", 4000),
    "verify": Step("writer", Stage.RESEARCHING, "verify-v1", 6000),
    "spec_plan": Step("lead", Stage.FORMATTING, "spec-plan-v1", 8000),
    "spec_critique": Step("writer", Stage.FORMATTING, "spec-critique-v1", 6000),
    "spec_finalise": Step("lead", Stage.FORMATTING, "spec-finalise-v1", 8000),
    "spec_review": Step("lead", Stage.FORMATTING, "spec-review-v1", 6000),
    "spec_fix": Step("writer", Stage.FORMATTING, "spec-fix-v1", 8000),
}



def current_engine(settings: Settings) -> Engine:
    """The engine a run priced now will execute with (see `Engine`)."""
    return Engine(lead_model=settings.lead_model, writer_model=settings.writer_model, prompts={task: step.prompt for task, step in STEPS.items()})


REASONS = ["GENERIC_PHRASING", "UNIFORM_STRUCTURE", "LOW_SPECIFICITY", "FORMULAIC_TRANSITIONS", "OVER_HEDGING", "UNSUPPORTED_SUMMARY", "REPETITION", "STYLE_SHIFT"]
GRADES = ["PASS", "PASS_WITH_WARNINGS", "REPAIR"]
BANDS = ["low", "moderate", "high"]
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
                    "riskBand": {"type": "string", "enum": BANDS},
                    "reasons": _list_of({"type": "string", "enum": REASONS}),
                    "explanation": _STR,
                    "suggestion": _STR,
                    "excerpt": _STR,
                    "confirmed": _list_of(_STR),
                    "rejected": _list_of(_STR),
                    "preserve": _BOOL,
                    "risk": _STR,
                }
            )
        )
    }
)
_PLAN = _obj({"blocks": _list_of(_obj({"id": _STR, "action": {"type": "string", "enum": ["rewrite", "leave"]}, "instruction": _STR, "preserve": _STR}))})
_CRITIQUE = _obj({"blocks": _list_of(_obj({"id": _STR, "agree": _BOOL, "comment": _STR})), "overall": _STR})
_REVIEW = _obj(
    {
        "results": _list_of(
            _obj(
                {
                    "id": _STR,
                    "grade": {"type": "string", "enum": GRADES},
                    "issues": _list_of({"type": "string", "enum": REVIEW_ISSUES}),
                    "note": _STR,
                    "riskBand": {"type": "string", "enum": BANDS},
                }
            )
        )
    }
)
SUPPORT = ["SUPPORTED", "PARTLY_SUPPORTED", "CONTRADICTED", "NOT_FOUND"]
_CLAIMS = _obj(
    {
        "claims": _list_of(
            _obj({"id": _STR, "claim": _STR, "cited": _BOOL, "query": _STR, "importance": {"type": "string", "enum": ["high", "medium", "low"]}})
        )
    }
)
_RESEARCH = _obj(
    {
        "support": {"type": "string", "enum": SUPPORT},
        "note": _STR,
        "sources": _list_of(
            _obj(
                {
                    "url": _STR,
                    "title": _STR,
                    "publisher": _STR,
                    "published": _STR,
                    "access": {"type": "string", "enum": ["FULL_TEXT", "ABSTRACT", "SNIPPET"]},
                    "passage": _STR,
                    "scope": _STR,
                    "supports": {"type": "string", "enum": SUPPORT},
                }
            )
        ),
    }
)
_VERIFY = _obj({"results": _list_of(_obj({"id": _STR, "support": {"type": "string", "enum": SUPPORT}, "note": _STR}))})
_SPEC_CRITIQUE = _obj({"items": _list_of(_obj({"field": _STR, "current": _STR, "proposed": _STR, "quote": _STR})), "overall": _STR})
_SPEC_REVIEW = _obj({"pass": _BOOL, "problems": _list_of(_obj({"field": _STR, "problem": _STR, "fix": _STR}))})


class _TextBlock(BaseModel):
    id: str
    text: str


class _TextBlocks(BaseModel):
    blocks: list[_TextBlock]


class _AnalysisBlock(BaseModel):
    id: str
    riskBand: Literal["low", "moderate", "high"]
    reasons: list[Literal["GENERIC_PHRASING", "UNIFORM_STRUCTURE", "LOW_SPECIFICITY", "FORMULAIC_TRANSITIONS", "OVER_HEDGING", "UNSUPPORTED_SUMMARY", "REPETITION", "STYLE_SHIFT"]]
    explanation: str
    suggestion: str
    excerpt: str
    confirmed: list[str]  # PaperAid rule ids the lead stands behind
    rejected: list[str]  # PaperAid rule ids the lead judged false positives in context
    preserve: StrictBool  # the passage should not be rewritten
    risk: str  # what a rewrite could get wrong here


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


class _ReviewItem(BaseModel):
    id: str
    grade: Literal["PASS", "PASS_WITH_WARNINGS", "REPAIR"]
    issues: list[Literal["MEANING_DRIFT", "NUMBER_CHANGED", "CITATION_LOST", "INVENTED_CLAIM", "BROKEN_TRANSITION", "VOICE_SHIFT", "INSTRUCTION_NOT_FOLLOWED"]]
    note: str
    riskBand: Literal["low", "moderate", "high"]


class _Review(BaseModel):
    results: list[_ReviewItem]


SupportAnswer = Literal["SUPPORTED", "PARTLY_SUPPORTED", "CONTRADICTED", "NOT_FOUND"]


class ClaimCandidate(BaseModel):
    id: str  # the passage it comes from
    claim: str
    cited: StrictBool
    query: str
    importance: Literal["high", "medium", "low"]


class _Claims(BaseModel):
    claims: list[ClaimCandidate]


class FoundSource(BaseModel):
    url: str
    title: str
    publisher: str
    published: str
    access: Literal["FULL_TEXT", "ABSTRACT", "SNIPPET"]
    passage: str
    scope: str
    supports: SupportAnswer


class ResearchAnswer(BaseModel):
    support: SupportAnswer
    note: str
    sources: list[FoundSource]


class VerifyItem(BaseModel):
    id: str
    support: SupportAnswer
    note: str


class _Verify(BaseModel):
    results: list[VerifyItem]


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
    risk: str = ""  # the lead's note on what a rewrite could get wrong


@dataclass
class Revision:
    id: str
    original: str
    revised: str
    problems: list[str]


@dataclass
class ReviewOutcome:
    """The lead's grades for a set of rewrites."""

    issues: dict[str, list[str]] = field(default_factory=dict)  # REPAIR or not reviewed: what to fix
    warnings: dict[str, str] = field(default_factory=dict)  # PASS_WITH_WARNINGS: a note for the student
    risk: dict[str, str] = field(default_factory=dict)  # how machine-like each reviewed rewrite reads now


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
        engine: Engine | None = None,
    ):
        self.settings = settings
        self._engine = engine or current_engine(settings)
        self._phase = phase
        self._record = record
        self._spent = spent
        self._budget = budget
        self._cache = cache
        # Called before every paid call: renews the stage's lease and may hand the rest of the stage
        # to a fresh delivery (which replays the calls already made from the cache, at no cost).
        self._heartbeat = heartbeat or (lambda: None)

    def model_for(self, task: str) -> str:
        return self._engine.lead_model if STEPS[task].role == "lead" else self._engine.writer_model

    def _prompt_for(self, task: str) -> str:
        return self._engine.prompts.get(task, STEPS[task].prompt)  # a step added after pricing uses its current prompt

    def _call[T: BaseModel](
        self,
        task: str,
        payload: dict[str, Any],
        schema: dict[str, Any],
        shape: type[T],
        max_searches: int = 0,
        accept: Callable[[T, list[str]], T] | None = None,
    ) -> T | None:
        """Returns the schema-validated answer, or None when the response was cut off. Only answers
        that passed validation are cached, so a retry never replays a bad response. With
        `max_searches`, the model may search the web that many times; `accept` then sees the
        answer with the URLs the searches opened and returns what may be kept (and cached)."""
        step = STEPS[task]
        model_ref = self.model_for(task)
        prompt = self._prompt_for(task)
        system = PROMPTS[prompt]
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
        prompt_chars = len(system) + len(json.dumps(payload))
        fee = 0.0
        if max_searches:  # the pages the searches read arrive as input, and each search has a fee
            prompt_chars += costs.SEARCH_INPUT_TOKENS_WORST * 3 * max_searches
            fee = costs.search_fee_usd(provider.name, max_searches)
        spent = self._spent()
        costs.ensure_within_budget(spent, costs.estimate_usd(provider.name, model, prompt_chars, step.max_tokens, prices) + fee, self._budget)
        # Hard ceiling: never allow more output than the remaining budget can pay for in the worst case.
        max_tokens = costs.affordable_output_tokens(provider.name, model, prompt_chars, step.max_tokens, self._budget - spent - fee, prices)
        if max_tokens < min(costs.MIN_OUTPUT_TOKENS, step.max_tokens):
            costs.ensure_within_budget(spent, float("inf"), self._budget)  # raises BUDGET_EXCEEDED
        if max_searches:
            result: ModelResult = provider.search_json(task, model, system, payload, schema, max_tokens, max_searches)
        else:
            result = provider.json(task, model, system, payload, schema, max_tokens)
        u = result.usage
        self._record(
            ModelCall(
                stage=step.stage,
                phase=self._phase,
                provider=result.provider,
                model=result.model,
                prompt_version=prompt,
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cached_tokens=u.cached_tokens,
                cache_write_tokens=u.cache_write_tokens,
                search_calls=u.search_calls,
                latency_ms=u.latency_ms,
                cost_usd=costs.cost_usd(result.provider, result.model, u.input_tokens, u.output_tokens, u.cached_tokens, prices, u.cache_write_tokens, u.search_calls),
            )
        )
        if result.stop == "refusal":
            raise PermanentStageError("MODEL_REFUSED", "We couldn't process this document with our AI provider.", f"{result.provider} refusal on {task}")
        if result.stop == "max_tokens":
            return None
        validated = self._validated(shape, parse(result.text, task), task)
        text = result.text
        if accept is not None:
            validated = accept(validated, result.sources)
            text = validated.model_dump_json()
        if self._cache:
            self._cache.put(key, text)
        return validated

    def _batched[T: BaseModel](
        self, task: str, items: list[dict[str, Any]], wrap: Callable[[list[dict[str, Any]]], dict[str, Any]], schema: dict[str, Any], shape: type[T]
    ) -> list[T]:
        return [answer for _, answer in self._batched_with_items(task, items, wrap, schema, shape)]

    def _batched_with_items[T: BaseModel](
        self, task: str, items: list[dict[str, Any]], wrap: Callable[[list[dict[str, Any]]], dict[str, Any]], schema: dict[str, Any], shape: type[T]
    ) -> list[tuple[list[dict[str, Any]], T]]:
        """Run `items` in word-bounded batches; halve any batch whose answer was cut off. Each
        answer comes with the items it covered."""
        responses: list[tuple[list[dict[str, Any]], T]] = []
        pending = _batches(items)
        while pending:
            batch = pending.pop(0)
            answer = self._call(task, wrap([{k: v for k, v in i.items() if k != "_words"} for i in batch]), schema, shape)
            if answer is not None:
                responses.append((batch, answer))
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

    def analyse(self, passages: list[dict[str, Any]], outline: list[str], evidence: dict[str, Any]) -> tuple[dict[str, _AnalysisBlock], set[str]]:
        """The lead's judgement per passage, given PaperAid's measurements (each passage carries its
        "signals"; `evidence` is the document-level bundle). Returns ({block_id: result}, the ids
        the lead actually saw): a seen passage it did not return has no problem in its view."""
        if not passages:
            return {}, set()
        known = {p["id"] for p in passages}
        items = [{**p, "_words": p["text"]} for p in passages]
        results: dict[str, _AnalysisBlock] = {}
        seen: set[str] = set()
        for batch, answer in self._batched_with_items("analyse", items, lambda b: {"outline": outline, "document": evidence, "blocks": b}, _ANALYSIS, _Analysis):
            seen.update(i["id"] for i in batch)
            for item in answer.blocks:
                if item.id in known:  # unknown IDs from a model are discarded, never trusted
                    results[item.id] = item
        return results, seen

    # --- 2–4. plan: lead drafts, writer critiques, lead finalises -----------------------

    @staticmethod
    def _plan_base(targets: list[Target]) -> list[dict[str, Any]]:
        return [{"id": t.id, "section": t.section, "text": t.masked, "findings": t.findings, "risk": t.risk, "_words": t.masked} for t in targets]

    def draft_plan(self, targets: list[Target], outline: list[str], brief: dict[str, str]) -> dict[str, PlanItem]:
        """Step 2 alone: the lead's draft plan. The refinement estimate runs exactly this call, so
        the job that follows replays it from the cache instead of paying for it again. `brief`
        is the student's style and intervention level (app.ai.styles.writing_brief)."""
        known = {t.id for t in targets}
        draft: dict[str, PlanItem] = {}
        for answer in self._batched("plan", self._plan_base(targets), lambda b: {**brief, "outline": outline, "passages": b}, _PLAN, _Plan):
            draft.update({p.id: p for p in answer.blocks if p.id in known})
        return draft

    def negotiate_plan(self, targets: list[Target], outline: list[str], brief: dict[str, str]) -> Negotiation:
        base = self._plan_base(targets)
        draft = self.draft_plan(targets, outline, brief)

        # The whole plan is critiqued, "leave" decisions included: the writer may argue a passage
        # the lead left alone does need work. A passage the lead omitted has no plan and is left.
        with_draft = [{**item, "draft": draft[item["id"]].model_dump(exclude={"id"})} for item in base if item["id"] in draft]
        planned = {item["id"] for item in with_draft}
        critique: dict[str, CritiqueItem] = {}
        overall = []
        for answer in self._batched("critique", with_draft, lambda b: {**brief, "passages": b}, _CRITIQUE, _Critique):
            critique.update({c.id: c for c in answer.blocks if c.id in planned})
            overall.append(answer.overall)

        with_critique = [
            {**item, "critique": critique[item["id"]].model_dump(exclude={"id"}) if item["id"] in critique else None} for item in with_draft
        ]
        final: dict[str, PlanItem] = {}
        for answer in self._batched("finalise", with_critique, lambda b: {**brief, "outline": outline, "passages": b}, _PLAN, _Plan):
            final.update({p.id: p for p in answer.blocks if p.id in planned})  # only passages the writer saw
        for item in with_draft:  # a passage the lead dropped from the final plan keeps its draft instruction
            final.setdefault(item["id"], draft[item["id"]])
        return Negotiation(draft=draft, critique=critique, final=final, critique_overall=" ".join(o for o in overall if o))

    # --- 5. write (writer) -------------------------------------------------------------

    def refine(self, targets: list[Target], outline: list[str], brief: dict[str, str]) -> list[Revision]:
        by_id = {t.id: t for t in targets}
        items = [
            {"id": t.id, "section": t.section, "instruction": t.instruction, "preserve": t.preserve, "before": t.before, "text": t.masked, "after": t.after, "_words": t.masked}
            for t in targets
        ]
        returned: dict[str, str] = {}
        for answer in self._batched("refine", items, lambda b: {**brief, "outline": outline, "blocks": b}, _TEXT_BLOCKS, _TextBlocks):
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

    def review(
        self, revisions: list[Revision], instructions: dict[str, str], brief: dict[str, str], context: dict[str, dict[str, Any]] | None = None
    ) -> ReviewOutcome:
        """The lead's review of changed passages, each with its neighbours, linked passages and
        PaperAid's post-scan (`context`, by block id)."""
        changed = [r for r in revisions if r.revised != r.original and not r.problems]
        context = context or {}
        items = []
        for r in changed:
            extra = context.get(r.id, {})
            linked = [str(item.get("text", "")) for item in extra.get("linked", [])]
            words = " ".join([r.original, r.revised, *(str(v) for v in extra.get("context", {}).values()), *linked])
            items.append({"id": r.id, "original": r.original, "revised": r.revised, "instruction": instructions.get(r.id, ""), **extra, "_words": words})
        outcome = ReviewOutcome()
        ids = {r.id for r in changed}
        for answer in self._batched("review", items, lambda b: {**brief, "pairs": b}, _REVIEW, _Review):
            for result in answer.results:
                if result.id not in ids:
                    continue
                outcome.risk[result.id] = result.riskBand
                if result.grade == "REPAIR":
                    issues: list[str] = list(result.issues) or ["MEANING_DRIFT"]
                    outcome.issues[result.id] = issues + ([f"NOTE: {result.note}"] if result.note else [])
                elif result.grade == "PASS_WITH_WARNINGS" and result.note:
                    outcome.warnings[result.id] = result.note
        for r in changed:  # a passage the reviewer skipped (or that could not fit) is not a pass
            if r.id not in outcome.risk:
                outcome.issues[r.id] = ["NOT_REVIEWED"]
        return outcome

    def repair(self, failed: list[tuple[Revision, list[str]]], instructions: dict[str, str], brief: dict[str, str]) -> list[Revision]:
        items = [
            {"id": r.id, "original": r.original, "rejected": r.revised, "instruction": instructions.get(r.id, ""), "objections": issues, "_words": r.original}
            for r, issues in failed
        ]
        returned: dict[str, str] = {}
        for answer in self._batched("repair", items, lambda b: {**brief, "blocks": b}, _TEXT_BLOCKS, _TextBlocks):
            returned.update({b.id: b.text for b in answer.blocks if b.id in {r.id for r, _ in failed}})
        out = []
        for r, _ in failed:
            revised = returned.get(r.id, r.original)
            out.append(Revision(r.id, r.original, revised, protect.check_rewrite(r.original, revised) if revised != r.original else []))
        return out

    # --- source check: lead finds and researches claims, writer checks the evidence -------------

    def find_claims(self, passages: list[dict[str, Any]], outline: list[str], limit: int) -> list[ClaimCandidate]:
        """The paper's important, publicly checkable factual claims, each with a search query.
        Returns candidates from known passages only; code then decides which may be searched."""
        known = {p["id"] for p in passages}
        items = [{**p, "_words": p["text"]} for p in passages]
        found: list[ClaimCandidate] = []
        for answer in self._batched("claims", items, lambda b: {"outline": outline, "limit": limit, "passages": b}, _CLAIMS, _Claims):
            found.extend(c for c in answer.claims if c.id in known)
        return found

    def research_claim(self, claim: str, query: str, cited: bool, max_searches: int) -> ResearchAnswer | None:
        """Live web research for one claim. Only the claim and a checked query are sent, never
        the paper. Sources the searches did not open are removed; without any left, the claim is
        NOT_FOUND. Returns None when the answer was cut off."""

        def accept(answer: ResearchAnswer, opened: list[str]) -> ResearchAnswer:
            kept = [s for s in answer.sources if research.opened(s.url, opened)][:3]
            if not kept and answer.support != "NOT_FOUND":
                return ResearchAnswer(support="NOT_FOUND", note="No source that the search actually opened could be confirmed for this claim.", sources=[])
            return answer.model_copy(update={"sources": kept})

        return self._call("research", {"claim": claim, "query": query, "citedInPaper": cited}, _RESEARCH, ResearchAnswer, max_searches=max_searches, accept=accept)

    def verify_claims(self, items: list[dict[str, Any]]) -> dict[str, VerifyItem]:
        """The writer's independent check, without searching: does each quoted passage support
        its claim for the same population, place and period?"""
        known = {i["id"] for i in items}
        batch = [{**i, "_words": i["claim"] + " " + i.get("context", "") + " " + " ".join(s.get("passage", "") for s in i.get("sources", []))} for i in items]
        results: dict[str, VerifyItem] = {}
        for answer in self._batched("verify", batch, lambda b: {"claims": b}, _VERIFY, _Verify):
            results.update({r.id: r for r in answer.results if r.id in known})
        return results

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
