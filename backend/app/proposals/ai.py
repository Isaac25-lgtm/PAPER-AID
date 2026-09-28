"""The proposal steps of the permanent algorithm (roles in app.ai.orchestration.STEPS). Every call
goes through AIRunner._call, so each keeps the same guarantees: usage recorded before parsing,
answers cached by request fingerprint, the job's spend ceiling enforced before each call, and cut-off
batches halved. Schemas are strict: every field required, nothing extra."""

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel

from app.ai.orchestration import AIRunner
from app.ai.providers import UNAVAILABLE, ModelResult
from app.analysis import research
from app.core.errors import PermanentStageError, RetryableStageError


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _list(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item}


def _enum(*values: str) -> dict[str, Any]:
    return {"type": "string", "enum": list(values)}


_S, _N, _STRS = {"type": "string"}, {"type": "number"}, {"type": "array", "items": {"type": "string"}}
_NULLABLE_INT = {"type": ["integer", "null"]}
STUDY_TYPES = ("QUANTITATIVE", "QUALITATIVE", "MIXED", "SECONDARY", "NON_EMPIRICAL")
SAMPLE_METHODS = ("YAMANE", "COCHRAN", "KREJCIE_MORGAN", "CENSUS", "SATURATION", "AUTHOR_STATED", "NOT_APPLICABLE")
READY = _enum("PASS", "NEEDS_REVIEW", "MISSING", "NOT_APPLICABLE")

NEEDS_SCHEMA = _obj({"needs": _list(_obj({"id": _S, "need": _S, "kind": _enum("LITERATURE", "FACT"), "query": _S}))})
EXTRACT_SCHEMA = _obj({"findings": _list(_obj({"work": _S, "statement": _S, "passage": _S, "scope": _S}))})
SEARCH_SCHEMA = _obj(
    {
        "findings": _list(
            _obj(
                {
                    "url": _S, "title": _S, "publisher": _S, "published": _S, "access": _enum("FULL_TEXT", "ABSTRACT", "SNIPPET"),
                    "statement": _S, "passage": _S, "scope": _S,
                }
            )
        )
    }
)
PLAN_SCHEMA = _obj(
    {
        "title": _S,
        "problem": _S,
        "purpose": _S,
        "specificObjectives": _STRS,
        "questionsKind": _enum("QUESTIONS", "HYPOTHESES", "PROPOSITIONS"),
        "researchQuestions": _STRS,
        "studyType": _enum(*STUDY_TYPES),
        "design": _S,
        "studyArea": _S,
        "population": _S,
        "sampling": _S,
        "sampleSize": _obj(
            {
                "method": _enum(*SAMPLE_METHODS), "population": _NULLABLE_INT, "populationSource": _S, "margin": _N,
                "confidence": {"type": "integer", "enum": [90, 95, 99]}, "proportion": _N, "stated": _NULLABLE_INT, "rationale": _S,
            }
        ),
        "inclusion": _S,
        "variables": _obj({"independent": _STRS, "dependent": _STRS, "intervening": _STRS}),
        "alignment": _list(_obj({"objective": {"type": "integer"}, "data": _S, "collection": _S, "analysis": _S})),
        "theory": _S,
        "scope": _S,
        "timelineMonths": {"type": "integer"},
        "gaps": _STRS,
        "questionsForStudent": _STRS,
    }
)
CRITIQUE_SCHEMA = _obj({"items": _list(_obj({"field": _S, "problem": _S, "proposal": _S})), "overall": _S})
BRIEFS_SCHEMA = _obj({"sections": _list(_obj({"key": _S, "points": _STRS, "evidence": _STRS}))})
SECTIONS_SCHEMA = _obj({"sections": _list(_obj({"key": _S, "paragraphs": _STRS, "table": _obj({"caption": _S, "rows": _list(_STRS)})}))})
REVIEW_SCHEMA = _obj({"results": _list(_obj({"key": _S, "grade": _enum("PASS", "PASS_WITH_WARNINGS", "REPAIR"), "issues": _STRS, "note": _S}))})
READINESS_SCHEMA = _obj(
    {
        "items": _list(_obj({"id": _S, "status": READY, "note": _S, "where": _S})),
        "consistency": _list(_obj({"id": _S, "question": _S, "status": READY, "note": _S, "where": _S})),
    }
)
AUDIT_SCHEMA = _obj(
    {
        "items": _list(_obj({"id": _S, "status": READY, "note": _S, "where": _S})),
        "findings": _list(
            _obj(
                {
                    "where": _S, "kind": _enum("ALIGNMENT", "EVIDENCE", "METHOD", "STRUCTURE", "TENSE", "WRITING"),
                    "severity": _enum("major", "moderate", "minor"), "issue": _S, "suggestion": _S,
                }
            )
        ),
    }
)


class Need(BaseModel):
    id: str
    need: str
    kind: Literal["LITERATURE", "FACT"]
    query: str


class _Needs(BaseModel):
    needs: list[Need]


class Extracted(BaseModel):
    work: str
    statement: str
    passage: str
    scope: str


class _Extracted(BaseModel):
    findings: list[Extracted]


class Searched(BaseModel):
    url: str
    title: str
    publisher: str
    published: str
    access: Literal["FULL_TEXT", "ABSTRACT", "SNIPPET"]
    statement: str
    passage: str
    scope: str


class _Searched(BaseModel):
    findings: list[Searched]


class Critique(BaseModel):
    items: list[dict[str, str]]
    overall: str = ""


class Brief(BaseModel):
    key: str
    points: list[str]
    evidence: list[str]


class _Briefs(BaseModel):
    sections: list[Brief]


class Table(BaseModel):
    caption: str
    rows: list[list[str]]


class SectionText(BaseModel):
    key: str
    paragraphs: list[str]
    table: Table


class _Sections(BaseModel):
    sections: list[SectionText]


class Grade(BaseModel):
    key: str
    grade: Literal["PASS", "PASS_WITH_WARNINGS", "REPAIR"]
    issues: list[str]
    note: str


class _Grades(BaseModel):
    results: list[Grade]


class Judged(BaseModel):
    id: str
    status: Literal["PASS", "NEEDS_REVIEW", "MISSING", "NOT_APPLICABLE"]
    note: str
    where: str
    question: str = ""


class Readiness(BaseModel):
    items: list[Judged]
    consistency: list[Judged]


class AuditFinding(BaseModel):
    where: str
    kind: Literal["ALIGNMENT", "EVIDENCE", "METHOD", "STRUCTURE", "TENSE", "WRITING"]
    severity: Literal["major", "moderate", "minor"]
    issue: str
    suggestion: str


class Audit(BaseModel):
    items: list[Judged]
    findings: list[AuditFinding]


def _whole(answer: BaseModel | None, task: str) -> BaseModel:
    """A single-call step that must fit: a cut-off answer is retried later, never half-used."""
    if answer is None:
        raise RetryableStageError("OUTPUT_TRUNCATED", UNAVAILABLE, f"answer did not fit on {task}")
    return answer


class ProposalRunner(AIRunner):
    # --- evidence ---------------------------------------------------------------------------

    def research_needs(self, payload: dict[str, Any]) -> list[Need]:
        answer = self._call("p_needs", payload, NEEDS_SCHEMA, _Needs)
        return answer.needs[: payload.get("limit", 10)] if answer else []

    def extract(self, need: str, works: list[dict[str, str]]) -> list[Extracted]:
        """Findings from scholarly abstracts; only the need and the works are sent."""
        answer = self._call("p_extract", {"need": need, "works": works}, EXTRACT_SCHEMA, _Extracted)
        known = {w["id"] for w in works}
        return [f for f in (answer.findings if answer else []) if f.work in known][:3]

    def search(self, need: str, query: str, max_searches: int, query_ok: Callable[[str], bool]) -> list[Searched]:
        """Live web research for one need. Sources the search did not open are dropped; a search
        that sent an unsafe query has all its results discarded."""

        def accept(answer: _Searched, result: ModelResult) -> _Searched:
            if not all(query_ok(q) for q in result.queries):
                return _Searched(findings=[])
            return _Searched(findings=[f for f in answer.findings if research.opened(f.url, result.sources)][:3])

        try:
            answer = self._call("p_search", {"need": need, "query": query}, SEARCH_SCHEMA, _Searched, max_searches=max_searches, accept=accept)
        except PermanentStageError as exc:
            if exc.code != "BUDGET_EXCEEDED":
                raise
            self.budget_reached = True
            return []
        return answer.findings if answer else []

    # --- plan and briefs: lead drafts → writer critiques → lead finalises ------------------

    def negotiate(self, kind: Literal["plan", "briefs"], payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], Critique]:
        """Returns (final, draft, critique) as plain data; code validates the final version."""
        task, schema, shape = ("p_plan", PLAN_SCHEMA, None) if kind == "plan" else ("p_brief", BRIEFS_SCHEMA, _Briefs)
        draft = self._raw(task, payload, schema, shape)
        critique = _whole(self._call("p_critique", {**payload, "kind": kind, "draft": draft}, CRITIQUE_SCHEMA, Critique), "p_critique")
        assert isinstance(critique, Critique)
        final = self._raw("p_finalise", {**payload, "kind": kind, "draft": draft, "critique": critique.model_dump()}, schema, shape)
        return final, draft, critique

    def _raw(self, task: str, payload: dict[str, Any], schema: dict[str, Any], shape: type[BaseModel] | None) -> dict[str, Any]:
        answer = _whole(self._call(task, payload, schema, shape or _AnyObject), task)
        return answer.model_dump()

    # --- chapter: writer drafts, lead reviews, writer fixes ------------------------------

    def _sections(self, task: str, items: list[dict[str, Any]], common: dict[str, Any], stop_on_budget: bool) -> dict[str, SectionText]:
        known = {i["key"] for i in items}
        out: dict[str, SectionText] = {}
        for answer in self._batched(task, items, lambda b: {**common, "sections": b}, SECTIONS_SCHEMA, _Sections, stop_on_budget=stop_on_budget):
            out.update({s.key: s for s in answer.sections if s.key in known})
        return out

    def draft(self, items: list[dict[str, Any]], common: dict[str, Any]) -> dict[str, SectionText]:
        return self._sections("p_draft", items, common, stop_on_budget=True)

    def fix(self, items: list[dict[str, Any]], common: dict[str, Any]) -> dict[str, SectionText]:
        return self._sections("p_fix", items, common, stop_on_budget=True)

    def grade(self, items: list[dict[str, Any]], common: dict[str, Any]) -> dict[str, Grade]:
        known = {i["key"] for i in items}
        out: dict[str, Grade] = {}
        for answer in self._batched("p_review", items, lambda b: {**common, "sections": b}, REVIEW_SCHEMA, _Grades, stop_on_budget=True):
            out.update({g.key: g for g in answer.results if g.key in known})
        return out

    def readiness(self, payload: dict[str, Any]) -> Readiness:
        answer = _whole(self._call("p_readiness", payload, READINESS_SCHEMA, Readiness), "p_readiness")
        assert isinstance(answer, Readiness)
        return answer

    def audit(self, payload: dict[str, Any]) -> Audit:
        answer = _whole(self._call("p_audit", payload, AUDIT_SCHEMA, Audit), "p_audit")
        assert isinstance(answer, Audit)
        return answer


class _AnyObject(BaseModel):
    """A plan answer: its shape is enforced by the schema and validated by the caller."""

    model_config = {"extra": "allow"}
