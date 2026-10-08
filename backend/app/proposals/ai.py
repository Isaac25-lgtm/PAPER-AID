"""The proposal steps of the permanent algorithm (roles in app.ai.orchestration.STEPS). Every call
goes through AIRunner._call, so each keeps the same guarantees: usage recorded before parsing,
answers cached by request fingerprint, the job's spend ceiling enforced before each call, and cut-off
batches halved. Schemas are strict: every field required, nothing extra."""

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, StrictBool

from app.ai.orchestration import SEARCH_DECLINED, AIRunner
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
# p-plan-v2 (the research-gap builder): the plan with its research gap.
PLAN_SCHEMA_V2 = _obj(
    {
        **PLAN_SCHEMA["properties"],
        "researchGap": _obj({"known": _S, "missing": _S, "contribution": _S, "evidence": _STRS}),
    }
)
# p-plan-v3 (the handbook's general objective, primary question and hypothesis pairs, 2026-10-08).
PLAN_SCHEMA_V3 = _obj(
    {
        **PLAN_SCHEMA_V2["properties"],
        "primaryQuestion": _S,
        "alternativeHypotheses": _STRS,
    }
)


def plan_schema(prompt: str) -> dict[str, Any]:
    """The plan's answer format for the prompt version a step was priced with."""
    return PLAN_SCHEMA if prompt == "p-plan-v1" else PLAN_SCHEMA_V2 if prompt == "p-plan-v2" else PLAN_SCHEMA_V3


CRITIQUE_SCHEMA = _obj({"items": _list(_obj({"field": _S, "problem": _S, "proposal": _S})), "overall": _S})
BRIEFS_SCHEMA = _obj({"sections": _list(_obj({"key": _S, "points": _STRS, "evidence": _STRS}))})
SECTIONS_SCHEMA = _obj({"sections": _list(_obj({"key": _S, "paragraphs": _STRS, "table": _obj({"caption": _S, "rows": _list(_STRS)})}))})
_FIGURE = _obj({"caption": _S, "x_axis": _S, "y_axis": _S, "series": _list(_obj({"label": _S, "points": _list(_obj({"x": _N, "y": _N}))}))})
# Works sections from w-draft-v2 / w-repair-v3: an illustrative table and an optional figure (2026-10-07).
WORK_SECTIONS_SCHEMA = _obj({"sections": _list(_obj({"key": _S, "paragraphs": _STRS, "table": _obj({"caption": _S, "rows": _list(_STRS), "illustrative": {"type": "boolean"}}),
                                                      "figure": {"anyOf": [_FIGURE, {"type": "null"}]}}))})
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
    illustrative: bool = False  # a worked example's hypothetical numbers, labelled as such by code (works, 2026-10-07)


class FigurePoint(BaseModel):
    x: float
    y: float


class FigureSeries(BaseModel):
    label: str
    points: list[FigurePoint]


class Figure(BaseModel):
    """A graph the writer gives as data and PaperAid's code draws (works, 2026-10-07: a coursework question
    asking for "graphical illustrations" could not be answered by text alone)."""

    caption: str
    x_axis: str
    y_axis: str
    series: list[FigureSeries]


class SectionText(BaseModel):
    key: str
    paragraphs: list[str]
    table: Table
    figure: Figure | None = None


class _Sections(BaseModel):
    sections: list[SectionText]


class Grade(BaseModel):
    key: str
    grade: Literal["PASS", "PASS_WITH_WARNINGS", "REPAIR"]
    issues: list[str]
    note: str


class Permission(BaseModel):
    approved: StrictBool
    issues: list[str]


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
            if exc.code in SEARCH_DECLINED:
                return []  # declined by the provider: nothing usable found for this need
            if exc.code != "BUDGET_EXCEEDED":
                raise
            self.budget_reached = True
            return []
        return answer.findings if answer else []

    # --- plan and briefs: lead drafts → writer critiques → lead finalises ------------------

    def negotiate(self, kind: Literal["plan", "briefs"], payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], Critique]:
        """Returns (final, draft, critique) as plain data; code validates the final version."""
        schema_of_plan = plan_schema(self._prompt_for("p_plan"))  # the schema of the engine it was priced with
        task, schema, shape = ("p_plan", schema_of_plan, None) if kind == "plan" else ("p_brief", BRIEFS_SCHEMA, _Briefs)
        draft = self._raw(task, payload, schema, shape)
        critique = _whole(self._call("p_critique", {**payload, "kind": kind, "draft": draft}, CRITIQUE_SCHEMA, Critique), "p_critique")
        assert isinstance(critique, Critique)
        guidance = _whole(self._call("p_guide", {**payload, "kind": kind, "draft": draft}, CRITIQUE_SCHEMA, Critique), "p_guide") if self.guided else None
        final = self._raw("p_finalise", {**payload, "kind": kind, "draft": draft, "critique": critique.model_dump(),
                                           **({"frontierGuidance": guidance.model_dump()} if guidance else {})}, schema, shape)
        return final, draft, critique

    def profile(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], Critique]:
        """An institution profile from a guide: (final, draft, critique); code validates the final."""
        from app.proposals.profile import CRITIQUE_SCHEMA as PROFILE_CRITIQUE
        from app.proposals.profile import SCHEMA as PROFILE

        draft = self._raw("p_profile", payload, PROFILE, None)
        critique = _whole(self._call("p_profile_critique", {**payload, "draft": draft}, PROFILE_CRITIQUE, Critique), "p_profile_critique")
        assert isinstance(critique, Critique)
        guidance = _whole(self._call("p_profile_guide", {**payload, "draft": draft}, PROFILE_CRITIQUE, Critique), "p_profile_guide") if self.guided else None
        final = self._raw("p_profile_finalise", {**payload, "draft": draft, "critique": critique.model_dump(),
                                                   **({"frontierGuidance": guidance.model_dump()} if guidance else {})}, PROFILE, None)
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
        tasks = ["p_review", "p_review_peer"] if self._engine.require_dual_approval and not self._engine.single_reviewer else ["p_review"]
        assessments = []
        for task in tasks:
            judged = {}
            for batch, answer in self._batched_with_items(task, items, lambda b: {**common, "sections": b}, REVIEW_SCHEMA, _Grades, stop_on_budget=True):
                batch_keys = {item["key"] for item in batch}
                judged.update({g.key: g for g in answer.results if g.key in batch_keys})
            assessments.append(judged)
        for key in known:
            grades = [a.get(key) for a in assessments]
            if any(g is None for g in grades):
                continue  # missing either approval is NOT_REVIEWED downstream
            issues = list(dict.fromkeys(i for g in grades if g.grade == "REPAIR" or (self._engine.require_dual_approval and g.issues) for i in (g.issues or ["REVIEW_REJECTED"])))
            grade = "REPAIR" if issues else "PASS_WITH_WARNINGS" if any(g.grade == "PASS_WITH_WARNINGS" for g in grades) else "PASS"
            out[key] = Grade(key=key, grade=grade, issues=issues, note=" ".join(dict.fromkeys(g.note for g in grades if g.note.strip())))
        return out

    def readiness(self, payload: dict[str, Any]) -> Readiness:
        answer = _whole(self._call("p_readiness", payload, READINESS_SCHEMA, Readiness), "p_readiness")
        assert isinstance(answer, Readiness)
        return answer

    def approve_plan(self, payload: dict[str, Any]) -> None:
        self._approve(
            ("p_plan_review", "p_plan_review_peer"), payload, "DOCUMENT_NOT_APPROVED",
            "PaperAid could not approve this proposal plan. No document was released and nothing was charged. Please try again.",
        )

    def review_plan(self, payload: dict[str, Any]) -> tuple[bool, list[str], str]:
        """The one accountable final review of the exact plan (Sol; owner decision 2026-09-30):
        (approved, objections, reason). An answer that is missing, cut off, refused or unaffordable
        is "not reviewed", never approval."""
        schema = _obj({"approved": {"type": "boolean"}, "issues": _STRS})
        try:
            answer = self._call("p_plan_review", payload, schema, Permission)
        except PermanentStageError as exc:
            if exc.code != "BUDGET_EXCEEDED":
                raise
            self.budget_reached = True
            return False, ["PaperAid's review of this plan could not be completed within this step's limits."], "SPEND_CAP"
        if answer is None:
            return False, ["PaperAid's review of this plan could not be completed."], "REVIEW_UNAVAILABLE"
        issues = [i.strip() for i in answer.issues if i.strip()]
        return answer.approved and not issues, issues or ([] if answer.approved else ["Not approved, without a stated reason."]), "REVIEW_OBJECTION"

    def repair_plan(self, payload: dict[str, Any], plan: dict[str, Any], objections: list[str]) -> dict[str, Any]:
        """A targeted repair of the plan for exactly the objections given (Sonnet finalises again with
        them as the critique); the repaired plan is then reviewed again."""
        schema = plan_schema(self._prompt_for("p_plan"))
        critique = {"items": [{"issue": o, "fix": "Fix exactly this, changing nothing else."} for o in objections], "overall": "Repair only what these points name."}
        return self._raw("p_finalise", {**payload, "kind": "plan", "draft": plan, "critique": critique}, schema, None)

    def review_profile(self, payload: dict[str, Any]) -> tuple[bool, list[str]]:
        """The one final reviewer's decision on the exact profile: (approved, objections). A missing,
        cut-off or unaffordable answer is not approval."""
        schema = _obj({"approved": {"type": "boolean"}, "issues": _STRS})
        try:
            answer = self._call("p_profile_review", payload, schema, Permission)
        except PermanentStageError as exc:
            if exc.code != "BUDGET_EXCEEDED":
                raise
            self.budget_reached = True
            return False, []
        if answer is None:
            return False, []
        issues = [i.strip() for i in answer.issues if i.strip()]
        return answer.approved and not issues, issues

    def repair_profile(self, payload: dict[str, Any], profile: dict[str, Any], objections: list[str]) -> dict[str, Any]:
        """A targeted repair of the profile for exactly the objections raised (Sonnet finalises again)."""
        from app.proposals.profile import SCHEMA as PROFILE

        critique = {"items": [{"issue": o, "fix": "Fix exactly this, changing nothing else."} for o in objections], "overall": "Repair only what these points name."}
        return self._raw("p_profile_finalise", {**payload, "draft": profile, "critique": critique}, PROFILE, None)

    def approve_profile(self, payload: dict[str, Any]) -> None:
        """Both approvals for an institution profile before any proposal is written to it."""
        self._approve(
            ("p_profile_review", "p_profile_review_peer"), payload, "PROFILE_NOT_APPROVED",
            "PaperAid could not confirm your institution's structure from this guide, so nothing was changed and you were not charged. "
            "You can try again, or continue with the standard structure.",
        )

    def _approve(self, tasks: tuple[str, str], payload: dict[str, Any], code: str, message: str) -> None:
        if not self._engine.require_dual_approval:
            return
        schema = _obj({"approved": {"type": "boolean"}, "issues": _STRS})
        for task in tasks[:1] if self._engine.single_reviewer else tasks:  # one accountable reviewer: no second veto
            answer = self._call(task, payload, schema, Permission)
            if answer is None or not answer.approved or answer.issues:
                raise PermanentStageError(code, message, f"{task}: not approved")

    def audit(self, payload: dict[str, Any]) -> Audit:
        answer = _whole(self._call("p_audit", payload, AUDIT_SCHEMA, Audit), "p_audit")
        assert isinstance(answer, Audit)
        return answer


class _AnyObject(BaseModel):
    """A plan answer: its shape is enforced by the schema and validated by the caller."""

    model_config = {"extra": "allow"}
