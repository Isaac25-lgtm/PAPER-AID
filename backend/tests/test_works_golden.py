"""Rulebook v1.0 §28 golden cases that code settles on its own: requirement resolution, section
templates, limits and the budget engine (the semantic cases run end to end in test_works_flows)."""

from app.rules.resolve import resolve
from app.rules.validators import VALIDATORS, Context
from app.works import budget as budget_engine
from app.works import templates
from app.works.models import Budget, BudgetLine, Requirement, ResolvedSpec, SourceFile, WorkDocument, WorkInputs, WorkSection


def _source(role="CALL", sid="s1"):
    return SourceFile(id=sid, name=f"{role.title()}.docx", role=role, words=500, sha256="x", path="p")


def _req(key, value, number=None, unit="", sid="s1", verified=True, **extra):
    return Requirement(id=f"R{key}{value}"[:24].replace(" ", ""), key=key, label=key, value=value, number=number, unit=unit, source_id=sid, source="Call.docx",
                       quote=value, verified=verified, **extra)


def _spec(kind, variant, mode="STANDARD", answers=None, reqs=None, sources=None, description="Too many mothers deliver at home without skilled care in Kamuli.") -> ResolvedSpec:
    inputs = WorkInputs(title="A work", description=description, answers={"problem": "p", "intervention": "i", "confirm:all": "yes", **(answers or {})})
    return resolve(1, kind, variant, mode if kind != "COURSEWORK" else "", inputs, sources or [_source()], reqs or [])


def test_cn_no_external_guidance_gives_the_standard_funding_concept():
    spec = _spec("CONCEPT_NOTE", "FUNDING_CONCEPT", reqs=[], sources=[])
    assert spec.target_words == 1800 and not spec.limits
    keys = [s.key for s in templates.skeleton(spec)]
    assert keys[:2] == ["summary", "problem"] and "timeline_budget" not in keys  # no budget or timeline asked for


def test_cn_hard_two_page_call_plans_under_the_page_limit_and_waits_for_the_rendered_count():
    spec = _spec("CONCEPT_NOTE", "FUNDING_CONCEPT", reqs=[_req("limit.pages", "no more than 2 pages", 2, "pages")])
    assert spec.target_words == int(2 * 500 * 0.97) and spec.flags["has_page_limit"]
    doc = WorkDocument(kind="CONCEPT_NOTE", variant="FUNDING_CONCEPT", title="t", spec_version=1, plan_version=1,
                       sections=[WorkSection(key="summary", heading="Summary", paragraphs=["word " * 300])])
    result = VALIDATORS["limits.rendered_pages"](Context(spec=spec, stage="FINAL", inputs=WorkInputs(title="A work"), doc=doc), {"id": "SH-005"})
    assert result is not None and result[0] == "NEEDS_REVIEW"  # never declared compliant from an estimate
    measured = VALIDATORS["limits.rendered_pages"](Context(spec=spec, stage="FINAL", inputs=WorkInputs(title="A work"), doc=doc, pages=3), {"id": "SH-005"})
    assert measured is not None and measured[0] == "FAIL"


def test_cn_indicative_budget_above_the_ceiling_is_blocked():
    spec = _spec("CONCEPT_NOTE", "FUNDING_CONCEPT", reqs=[_req("ceiling", "up to USD 20,000", 20000, "USD")])
    budget = Budget(currency="USD", lines=[BudgetLine(id="B1", category="Training", description="x", quantity=5, unit_cost=5000, activity_ids=["A1"])])
    found = {rid: status for rid, status, _ in budget_engine.checks(budget, spec, None)}
    assert found["CN-022"] == "FAIL" and found["FP-041"] == "FAIL"


def test_fp_research_grant_never_inherits_ngo_headings():
    keys = [s.key for s in templates.skeleton(_spec("FUNDING_PROPOSAL", "RESEARCH_GRANT"))]
    assert "aims" in keys and "methods" in keys and "intervention_logic" not in keys and "mel" not in keys


def test_fp_scoring_weights_deepen_the_sections_that_answer_them_without_becoming_word_shares():
    plain = templates.skeleton(_spec("FUNDING_PROPOSAL", "NGO_PROJECT", sources=[]))
    weighted = templates.skeleton(_spec("FUNDING_PROPOSAL", "NGO_PROJECT", reqs=[
        _req("scoring", "Relevance", weight=40), _req("scoring", "Monitoring and evaluation", weight=40), _req("scoring", "Sustainability", weight=20)]))
    by_key = {s.key: s for s in weighted}
    assert by_key["mel"].words > {s.key: s for s in plain}["mel"].words and by_key["mel"].criteria
    assert sum(s.words for s in weighted) <= 5500 and by_key["mel"].words < 5500 * 0.4  # deeper, never 40% of the words


def test_fp_currency_conversion_needs_its_rate_and_date_and_the_request_must_match_the_budget():
    spec = _spec("FUNDING_PROPOSAL", "NGO_PROJECT")
    budget = Budget(currency="USD", requested=9000, exchange_from="UGX", lines=[BudgetLine(id="B1", category="Training", description="x", quantity=1, unit_cost=8000, activity_ids=["A1"])])
    found = {rid: status for rid, status, _ in budget_engine.checks(budget, spec, None)}
    assert found["FP-046"] == "FAIL" and found["FP-048"] == "FAIL"


def test_fp_a_staff_line_longer_than_the_project_is_for_the_student_to_check():
    spec = _spec("FUNDING_PROPOSAL", "NGO_PROJECT", answers={"duration_months": "12"})
    budget = Budget(currency="USD", lines=[BudgetLine(id="B1", category="Personnel", description="Officer", quantity=18, unit="month", unit_cost=1000, role="MEL Officer", support=True)])
    found = {rid: (status, note) for rid, status, note in budget_engine.checks(budget, spec, None)}
    assert found["FP-047"][0] == "NEEDS_REVIEW" and "18 months" in found["FP-047"][1]


def test_cw_missing_word_limit_asks_once_then_uses_the_level_length():
    question = "Critically evaluate the effectiveness of community health workers in improving maternal health outcomes in rural Uganda since 2015."
    open_ = _spec("COURSEWORK", "ESSAY", answers={}, sources=[], description=question)
    assert open_.gate == "ASK_ONCE" and any(q.id == "word_limit" and not q.answered for q in open_.questions)
    skipped = _spec("COURSEWORK", "ESSAY", answers={"word_limit": "SKIPPED", "level": "POSTGRADUATE", "ai_policy": "NOT_MENTIONED", "citation_style": "APA7"}, sources=[],
                    description=question)
    assert skipped.target_words == 3000 and any("3,000" in a for a in skipped.assumptions)


def test_cw_the_briefs_referencing_style_outranks_the_students_choice():
    spec = _spec("COURSEWORK", "ESSAY", answers={"citation_style": "APA7"}, reqs=[_req("citation_style", "Harvard", sid="b1")], sources=[_source("BRIEF", "b1")])
    assert spec.citation_style == "HARVARD"


def test_cw_empirical_papers_have_methods_and_analytical_papers_do_not():
    empirical = [s.key for s in templates.skeleton(_spec("COURSEWORK", "RESEARCH_PAPER_EMPIRICAL", answers={"word_limit": "2000"}, sources=[]))]
    analytical = [s.key for s in templates.skeleton(_spec("COURSEWORK", "RESEARCH_PAPER_NON_EMPIRICAL", answers={"word_limit": "2000"}, sources=[]))]
    assert "methods" in empirical and "methods" not in analytical and "framework" in analytical


def test_cw_a_literature_review_is_planned_in_themes_and_a_postgraduate_one_says_how_it_searched():
    keys = [s.key for s in templates.skeleton(_spec("COURSEWORK", "LITERATURE_REVIEW", answers={"word_limit": "3000", "level": "POSTGRADUATE"}, sources=[]))]
    assert "search" in keys and sum(k.startswith("theme") for k in keys) >= 3 and "gaps" in keys


def test_cw_rubric_criteria_become_quality_rules_and_a_mandatory_one_is_marked():
    spec = _spec("COURSEWORK", "ESSAY", answers={"word_limit": "2000"}, reqs=[
        _req("rubric", "Critical analysis", weight=40, sid="b1"), Requirement(id="Rk2", key="rubric", label="rubric", value="Referencing", weight=10, source_id="b1",
                                                                             quote="Referencing must be accurate to pass", verified=True)], sources=[_source("RUBRIC", "b1")])
    rubric = {c.name: c for c in spec.scoring}
    assert rubric["Critical analysis"].weight == 40 and rubric["Referencing"].mandatory and spec.flags["has_rubric"] and "CW-020" in spec.active_rules


def test_cw_a_conclusion_that_brings_new_evidence_is_flagged():
    spec = _spec("COURSEWORK", "ESSAY", answers={"word_limit": "2000"}, sources=[])
    doc = WorkDocument(kind="COURSEWORK", variant="ESSAY", title="t", spec_version=1, plan_version=1, sections=[
        WorkSection(key="theme1", heading="Theme", paragraphs=["Evidence ⟦Eaaaaaa⟧."]), WorkSection(key="conclusion", heading="Conclusion", paragraphs=["New ⟦Ebbbbbb⟧."])])
    result = VALIDATORS["coursework.conclusion_new_evidence"](Context(spec=spec, stage="FINAL", inputs=WorkInputs(title="A work"), doc=doc), {"id": "CW-029"})
    assert result is not None and result[0] == "NEEDS_REVIEW"


def test_equal_authority_documents_that_disagree_block_until_the_student_chooses():
    reqs = [_req("ceiling", "USD 10,000", 10000, "USD", sid="s1"), _req("ceiling", "USD 12,000", 12000, "USD", sid="s2")]
    spec = _spec("FUNDING_PROPOSAL", "NGO_PROJECT", reqs=reqs, sources=[_source("CALL", "s1"), _source("TEMPLATE", "s2")])
    assert spec.gate == "BLOCK" and spec.conflicts and spec.ceiling is None
    chosen = _spec("FUNDING_PROPOSAL", "NGO_PROJECT", reqs=reqs, sources=[_source("CALL", "s1"), _source("TEMPLATE", "s2")], answers={"conflict:ceiling": reqs[1].id})
    assert chosen.ceiling == 12000 and chosen.conflicts[0].chosen == reqs[1].id


def test_sections_a_call_requires_by_name_are_headed_with_that_name():
    """Real-model pilot 2026-09-30: the call required "Proposed intervention" and "Implementation
    arrangements"; the plan kept its own headings and the draft failed the required-sections check."""
    reqs = [_req("section.required", name) for name in ("problem statement", "proposed intervention", "expected results", "implementation arrangements", "indicative budget")]
    spec = _spec("CONCEPT_NOTE", "FUNDING_CONCEPT", reqs=reqs, answers={"budget_envelope": "48000"})
    headings = [s.heading for s in templates.skeleton(spec)]
    for name in ("Proposed intervention", "Implementation arrangements", "Expected results", "Indicative budget"):
        assert any(name.lower() in h.lower() for h in headings), (name, headings)
    assert sum(s.words for s in templates.skeleton(spec)) <= spec.target_words * 1.02
    doc = WorkDocument(kind="CONCEPT_NOTE", variant="FUNDING_CONCEPT", title="t", spec_version=1, plan_version=1,
                       sections=[WorkSection(key=s.key, heading=s.heading, paragraphs=["Text."]) for s in templates.skeleton(spec)])
    result = VALIDATORS["structure.required_sections"](Context(spec=spec, stage="FINAL", inputs=WorkInputs(title="A work"), doc=doc), {"id": "SH-019"})
    assert result[0] == "PASS", result


def test_a_coursework_plan_keeps_the_writers_choice_of_criteria_and_every_criterion_a_home():
    """Live 2026-10-08: the skeleton put all six marking criteria on both themes; the final reviewer asked for Theme 1
    to serve S1 to S3 only and Theme 2 S4 to S6; the writer could add criteria but never remove them, so the plan was
    refused twice. The writer's choice now stands, and code only gives a criterion left out everywhere its home back."""
    from app.works.models import Criterion, PlanSection
    from app.works.pipeline import _plan_from

    spec = _spec("COURSEWORK", "ESSAY", answers={"word_limit": "1500", "level": "LATER_UG"},
                 description="Critically evaluate the design of modern web applications.")
    six = [f"S{n}" for n in range(1, 7)]
    spec = spec.model_copy(update={"scoring": [Criterion(id=c, name=f"Criterion {c}", weight=10) for c in six]})
    skeleton = [PlanSection(key="introduction", heading="Introduction", words=150),
                PlanSection(key="theme1", heading="Theme 1", words=600, criteria=list(six)),
                PlanSection(key="theme2", heading="Theme 2", words=600, criteria=list(six)),
                PlanSection(key="conclusion", heading="Conclusion", words=150)]
    narrowed = {"title": "Web applications", "sections": [{"key": "theme1", "heading": "Architecture", "criteria": ["S1", "S2", "S3"]},
                                                           {"key": "theme2", "heading": "Technologies", "criteria": ["S4", "S5", "S6"]}]}
    plan = {s.key: s.criteria for s in _plan_from(narrowed, skeleton, spec).sections}
    assert plan["theme1"] == ["S1", "S2", "S3"] and plan["theme2"] == ["S4", "S5", "S6"]  # as the reviewer asked: now possible

    dropped = {"title": "Web applications", "sections": [{"key": "theme1", "criteria": ["S1"]}, {"key": "theme2", "criteria": ["S2"]}]}
    plan = {s.key: s.criteria for s in _plan_from(dropped, skeleton, spec).sections}
    assert sorted(plan["theme1"] + plan["theme2"]) == six  # every criterion still has a home
    silent = {"title": "Web applications", "sections": [{"key": "theme1"}, {"key": "theme2"}]}
    assert _plan_from(silent, skeleton, spec).sections[1].criteria == six  # no choice given: the skeleton's stands
    moved = {"title": "Web applications", "sections": [{"key": "theme1", "criteria": []}, {"key": "theme2", "criteria": list(six)}]}
    plan = {s.key: s.criteria for s in _plan_from(moved, skeleton, spec).sections}
    assert plan["theme1"] == [] and plan["theme2"] == six  # an empty list is a choice too (Codex audit, finding 8)

    funding = _spec("FUNDING_PROPOSAL", "NGO_PROJECT").model_copy(update={"scoring": spec.scoring})
    kept = _plan_from(narrowed, skeleton, funding).sections[1].criteria
    assert kept == six  # other works keep the skeleton's criteria and only add to them
