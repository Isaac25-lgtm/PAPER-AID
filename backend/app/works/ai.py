"""The works steps of the algorithm (roles in app.ai.orchestration.STEPS, owner decision 2026-09-30).
Every call goes through AIRunner._call, so each keeps the same guarantees as the rest of PaperAid:
usage recorded before parsing, answers cached by request fingerprint, the step's spend cap
enforced before each call (with the price table frozen in its quote), cut-off batches halved, and
malformed answers never accepted. Schemas are strict: every field required, nothing extra."""

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, field_validator

from app.ai.orchestration import _VERIFY, SEARCH_DECLINED, AIRunner, VerifyItem, _Verify
from app.ai.providers import UNAVAILABLE, ModelResult
from app.analysis import research
from app.core.errors import PermanentStageError, RetryableStageError
from app.proposals.ai import (
    EXTRACT_SCHEMA,
    NEEDS_SCHEMA,
    SEARCH_SCHEMA,
    SECTIONS_SCHEMA,
    WORK_SECTIONS_SCHEMA,
    Extracted,
    Need,
    Searched,
    SectionText,
    _Extracted,
    _Needs,
    _Searched,
    _Sections,
    searched_once_more,
)
from app.rules.extract import READ_SCHEMA


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _list(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item}


def _enum(*values: str) -> dict[str, Any]:
    return {"type": "string", "enum": list(values)}


_S, _STRS, _NUM, _INT = {"type": "string"}, {"type": "array", "items": {"type": "string"}}, {"type": ["number", "null"]}, {"type": ["integer", "null"]}
RULE_VERDICTS = _list(_obj({"rule": _S, "status": _enum("PASS", "FAIL", "NOT_APPLICABLE"), "note": _S}))

READ_WITH_READINGS = _obj(
    {
        **READ_SCHEMA["properties"],
        "readings": _list(_obj({"sourceId": _S, "title": _S, "authors": _STRS, "organisation": _S, "year": _S, "container": _S, "doi": _S})),
    }
)
PLAN_SCHEMA = _obj(
    {
        "title": _S,
        "position": _S,
        "sections": _list(_obj({"key": _S, "heading": _S, "words": {"type": "integer"}, "brief": _S, "criteria": _STRS, "coverage": _STRS})),
        "questionsForStudent": _STRS,
        "notes": _STRS,
    }
)
# "suggestions" (w-plan-review-v2, w-results-review-v2): what would make it stronger, never blocking.
REVIEW_PLAN_SCHEMA = _obj({"verdict": _enum("PASS", "REPAIR"), "rules": RULE_VERDICTS, "issues": _STRS, "suggestions": _STRS})
RESULTS_SCHEMA = _obj(
    {
        "goal": _obj({"id": _S, "statement": _S}),
        "objectives": _list(_obj({"id": _S, "statement": _S})),
        "outcomes": _list(_obj({"id": _S, "statement": _S, "objectiveId": _S, "assumptions": _STRS})),
        "outputs": _list(_obj({"id": _S, "statement": _S, "outcomeId": _S})),
        "activities": _list(_obj({"id": _S, "statement": _S, "outputId": _S, "ownerRole": _S, "startMonth": _INT, "endMonth": _INT, "costed": {"type": "boolean"}, "major": {"type": "boolean"}})),
        "indicators": _list(_obj({"id": _S, "resultId": _S, "level": _enum("goal", "outcome", "output"), "definition": _S, "unit": _S, "baselinePlan": _S, "targetDate": _S,
                                  "disaggregation": _STRS, "meansOfVerification": _S, "frequency": _S, "responsibleRole": _S})),
        "risks": _list(_obj({"id": _S, "statement": _S, "likelihood": _enum("low", "medium", "high"), "impact": _enum("low", "medium", "high"), "mitigation": _S, "ownerRole": _S})),
        "assumptions": _STRS,
        "budgetLines": _list(_obj({"category": _S, "description": _S, "unit": _S, "activityIds": _STRS, "support": {"type": "boolean"}, "role": _S})),
    }
)
LEVELS = _enum("goal", "outcome", "output", "activity")
# w-results-review-v3 (Codex audit 2026-10-04): issues name their rule and statements, and a reversed
# classification of unchanged wording carries its reason.
REVIEW_RESULTS_SCHEMA = _obj(
    {"rules": RULE_VERDICTS, "classified": _list(_obj({"id": _S, "statedAs": _S, "reads": LEVELS, "note": _S})),
     "issues": _list(_obj({"rule": _S, "ids": _STRS, "text": _S})), "suggestions": _STRS,
     "reversed": _list(_obj({"id": _S, "before": LEVELS, "now": LEVELS, "reason": _S}))}
)
INTEGRITY_SCHEMA = _obj({"results": _list(_obj({"key": _S, "meaningKept": {"type": "boolean"}, "invented": _STRS, "lockedChanged": _STRS, "note": _S}))})
EVALUATE_SCHEMA = _obj(
    {
        "results": _list(
            _obj(
                {
                    "key": _S,
                    "verdict": _enum("PASS", "REPAIR", "REJECT"),
                    "rules": RULE_VERDICTS,
                    "issues": _list(_obj({"type": _S, "severity": _enum("minor", "moderate", "major"), "instruction": _S})),
                    "scores": _obj({"fidelity": {"type": "number"}, "quality": {"type": "number"}, "naturalness": {"type": "number"}}),
                }
            )
        )
    }
)
ADJUDICATE_SCHEMA = _obj({"results": _list(_obj({"key": _S, "decision": _enum("PASS", "REPAIR"), "instruction": _S}))})
FINAL_SCHEMA = _obj(
    {
        "rules": _list(_obj({"rule": _S, "status": _enum("PASS", "FAIL", "NOT_APPLICABLE"), "note": _S, "where": _S})),
        "coverage": _list(_obj({"id": _S, "answered": {"type": "boolean"}, "where": _S})),
        "priorities": _list(_obj({"priority": _S, "addressed": {"type": "boolean"}, "where": _S})),
    }
)


class RuleVerdict(BaseModel):
    rule: str
    status: Literal["PASS", "FAIL", "NOT_APPLICABLE"]
    note: str


class _Read(BaseModel):
    model_config = {"extra": "allow"}
    requirements: list[dict[str, Any]]
    unclear: list[str]
    readings: list[dict[str, Any]] = []


class PlanAnswer(BaseModel):
    model_config = {"extra": "allow"}
    title: str
    position: str
    sections: list[dict[str, Any]]
    questionsForStudent: list[str]  # noqa: N815 - the schema's own field name
    notes: list[str]


class PlanReview(BaseModel):
    verdict: Literal["PASS", "REPAIR"]
    rules: list[RuleVerdict]
    issues: list[str]
    suggestions: list[str] = []


class ResultsAnswer(BaseModel):
    model_config = {"extra": "allow"}


class Classified(BaseModel):
    id: str
    statedAs: str  # noqa: N815
    reads: Literal["goal", "outcome", "output", "activity"]
    note: str


class Issue(BaseModel):
    rule: str = ""
    ids: list[str] = []
    text: str


class Reversal(BaseModel):
    id: str
    before: str
    now: str
    reason: str


class ResultsReview(BaseModel):
    rules: list[RuleVerdict]
    classified: list[Classified]
    issues: list[Issue]
    suggestions: list[str] = []
    reversed: list[Reversal] = []

    @field_validator("issues", mode="before")
    @classmethod
    def _plain(cls, value: Any) -> Any:  # an earlier engine's issues are plain text
        return [{"text": v} if isinstance(v, str) else v for v in value or []]

    @property
    def texts(self) -> list[str]:
        return [i.text for i in self.issues]


class Integrity(BaseModel):
    key: str
    meaningKept: bool  # noqa: N815
    invented: list[str]
    lockedChanged: list[str]  # noqa: N815
    note: str


class _Integrity(BaseModel):
    results: list[Integrity]


class Issue(BaseModel):
    type: str
    severity: Literal["minor", "moderate", "major"]
    instruction: str


class Scores(BaseModel):
    fidelity: float
    quality: float
    naturalness: float


class Evaluation(BaseModel):
    key: str
    verdict: Literal["PASS", "REPAIR", "REJECT"]
    rules: list[RuleVerdict]
    issues: list[Issue]
    scores: Scores


class _Evaluations(BaseModel):
    results: list[Evaluation]


class Adjudication(BaseModel):
    key: str
    decision: Literal["PASS", "REPAIR"]
    instruction: str


class _Adjudications(BaseModel):
    results: list[Adjudication]


class FinalRule(BaseModel):
    rule: str
    status: Literal["PASS", "FAIL", "NOT_APPLICABLE"]
    note: str
    where: str


class Covered(BaseModel):
    id: str
    answered: bool
    where: str


class Priority(BaseModel):
    priority: str
    addressed: bool
    where: str


class Final(BaseModel):
    rules: list[FinalRule]
    coverage: list[Covered]
    priorities: list[Priority]


def _whole[T: BaseModel](answer: T | None, task: str) -> T:
    if answer is None:
        raise RetryableStageError("OUTPUT_TRUNCATED", UNAVAILABLE, f"answer did not fit on {task}")
    return answer


class WorkRunner(AIRunner):
    # --- reading the student's documents ----------------------------------------------------
    def read(self, payload: dict[str, Any]) -> _Read:
        return _whole(self._call("w_read", payload, READ_WITH_READINGS, _Read), "w_read")

    # --- evidence (the proposal prompts, on the works roles) --------------------------------
    def research_needs(self, payload: dict[str, Any]) -> list[Need]:
        answer = self._call("w_needs", payload, NEEDS_SCHEMA, _Needs)
        return answer.needs[: payload.get("limit", 8)] if answer else []

    def extract(self, need: str, works: list[dict[str, str]]) -> list[Extracted]:
        answer = self._call("w_extract", {"need": need, "works": works}, EXTRACT_SCHEMA, _Extracted)
        known = {w["id"] for w in works}
        return [f for f in (answer.findings if answer else []) if f.work in known][:3]

    def search(self, need: str, query: str, max_searches: int, query_ok: Callable[[str], bool]) -> list[Searched]:
        def accept(answer: _Searched, result: ModelResult) -> _Searched:
            if not all(query_ok(q) for q in result.queries):
                return _Searched(findings=[])
            return _Searched(findings=[f for f in answer.findings if research.opened(f.url, result.sources)][:3])

        try:
            answer = searched_once_more(lambda: self._call("w_search", {"need": need, "query": query}, SEARCH_SCHEMA, _Searched, max_searches=max_searches, accept=accept))
        except PermanentStageError as exc:
            if exc.code in SEARCH_DECLINED:
                return []  # declined by the provider: nothing usable found for this need
            if exc.code != "BUDGET_EXCEEDED":
                raise
            self.budget_reached = True
            return []
        return answer.findings if answer else []

    def verify(self, items: list[dict[str, Any]]) -> dict[str, VerifyItem]:
        known = {i["id"] for i in items}
        batch = [{**i, "_words": i["claim"] + " " + " ".join(s.get("passage", "") for s in i.get("sources", []))} for i in items]
        out: dict[str, VerifyItem] = {}
        for answer in self._batched("w_verify", batch, lambda b: {"claims": b}, _VERIFY, _Verify):
            out.update({r.id: r for r in answer.results if r.id in known})
        return out

    # --- the plan, and for funding the Results Model -----------------------------------------
    def plan(self, payload: dict[str, Any]) -> PlanAnswer:
        return _whole(self._call("w_plan", payload, PLAN_SCHEMA, PlanAnswer), "w_plan")

    def review_plan(self, payload: dict[str, Any]) -> PlanReview:
        return _whole(self._call("w_plan_review", payload, REVIEW_PLAN_SCHEMA, PlanReview), "w_plan_review")

    def final_review_plan(self, payload: dict[str, Any]) -> PlanReview | None:
        """The final reviewer's decision on the exact plan; None when it could not be completed
        (cut off, refused or unaffordable): "not reviewed", never approval."""
        try:
            return self._call("w_plan_review", payload, REVIEW_PLAN_SCHEMA, PlanReview)
        except PermanentStageError as exc:
            if exc.code != "BUDGET_EXCEEDED":
                raise
            self.budget_reached = True
            return None

    def final_review_results(self, payload: dict[str, Any]) -> "ResultsReview | None":
        try:
            return self._call("w_results_review", payload, REVIEW_RESULTS_SCHEMA, ResultsReview)
        except PermanentStageError as exc:
            if exc.code != "BUDGET_EXCEEDED":
                raise
            self.budget_reached = True
            return None

    def results(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _whole(self._call("w_results", payload, RESULTS_SCHEMA, ResultsAnswer), "w_results").model_dump()

    def review_results(self, payload: dict[str, Any]) -> ResultsReview:
        return _whole(self._call("w_results_review", payload, REVIEW_RESULTS_SCHEMA, ResultsReview), "w_results_review")

    # --- sections: the writer drafts, code checks, the reviewers judge, the writer repairs ----
    def _sections(self, task: str, items: list[dict[str, Any]], common: dict[str, Any]) -> dict[str, SectionText]:
        known = {i["key"] for i in items}
        out: dict[str, SectionText] = {}
        # The answer format of the prompt version the step was priced with: figures from w-draft-v2 / w-repair-v3.
        schema = WORK_SECTIONS_SCHEMA if self._prompt_for(task) in ("w-draft-v2", "w-draft-v3", "w-draft-v4", "w-repair-v3", "w-repair-v4", "w-repair-v5") else SECTIONS_SCHEMA
        for answer in self._batched(task, items, lambda b: {**common, "sections": b}, schema, _Sections, stop_on_budget=True):
            out.update({s.key: s for s in answer.sections if s.key in known})
        return out

    def draft(self, items: list[dict[str, Any]], common: dict[str, Any]) -> dict[str, SectionText]:
        return self._sections("w_draft", items, common)

    def repair(self, items: list[dict[str, Any]], common: dict[str, Any]) -> dict[str, SectionText]:
        return self._sections("w_repair", items, common)

    def compress(self, items: list[dict[str, Any]], common: dict[str, Any]) -> dict[str, SectionText]:
        return self._sections("w_compress", items, common)

    def integrity(self, items: list[dict[str, Any]], common: dict[str, Any]) -> dict[str, Integrity]:
        known = {i["key"] for i in items}
        out: dict[str, Integrity] = {}
        for batch, answer in self._batched_with_items("w_integrity", items, lambda b: {**common, "sections": b}, INTEGRITY_SCHEMA, _Integrity, stop_on_budget=True):
            keys = {i["key"] for i in batch}
            out.update({r.key: r for r in answer.results if r.key in keys & known})
        return out

    def evaluate(self, items: list[dict[str, Any]], common: dict[str, Any]) -> dict[str, Evaluation]:
        known = {i["key"] for i in items}
        out: dict[str, Evaluation] = {}
        for batch, answer in self._batched_with_items("w_evaluate", items, lambda b: {**common, "sections": b}, EVALUATE_SCHEMA, _Evaluations, stop_on_budget=True):
            keys = {i["key"] for i in batch}
            out.update({r.key: r for r in answer.results if r.key in keys & known})
        return out

    def adjudicate(self, items: list[dict[str, Any]], common: dict[str, Any]) -> dict[str, Adjudication]:
        if not self._engine.roles.get("ADJUDICATOR"):
            return {}
        answer = self._call("w_adjudicate", {**common, "sections": items}, ADJUDICATE_SCHEMA, _Adjudications)
        known = {i["key"] for i in items}
        return {r.key: r for r in (answer.results if answer else []) if r.key in known}

    def final(self, payload: dict[str, Any]) -> Final | None:
        try:
            return self._call("w_final", payload, FINAL_SCHEMA, Final)
        except PermanentStageError as exc:
            if exc.code != "BUDGET_EXCEEDED":
                raise
            self.budget_reached = True
            return None
