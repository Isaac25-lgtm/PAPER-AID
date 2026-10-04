"""Fixes from the live funding runs of 2026-10-03 (decisions.md): a call's required parts each get
their own heading (templates-v2); a final review's suggestions never block; after a repair the
reviewer is given its earlier issues, so the review settles instead of starting over."""

from app.works import templates
from app.works.ai import PlanReview, ResultsReview
from app.works.models import PlanSection
from app.works.pipeline import _plan_decision


def test_parts_a_call_requires_by_name_each_get_their_own_heading():
    sections = [PlanSection(key="results", heading="Results and monitoring", words=600, min_words=400, max_words=900, brief="The results chain"),
                PlanSection(key="problem", heading="The problem", words=300, brief="Why")]
    named = templates._name_required(sections, ["Results framework with indicators", "Monitoring and evaluation plan"], 900)
    headings = [s.heading for s in named]
    assert "Results framework with indicators" in headings and "Monitoring and evaluation plan" in headings  # never one joined heading
    assert not any(" and Monitoring" in h for h in headings)
    keys = [s.key for s in named]
    assert len(keys) == len(set(keys)) and all(s.locked for s in named if s.heading in ("Results framework with indicators", "Monitoring and evaluation plan"))
    assert sum(s.words for s in named) <= 900


def test_a_single_required_name_keeps_its_section_as_before():
    sections = [PlanSection(key="approach", heading="Approach and activities", words=300, brief="What the project will do")]
    named = templates._name_required(sections, ["Proposed intervention"], 300)
    assert [s.key for s in named] == ["approach"] and named[0].heading == "Proposed intervention"


def test_suggestions_never_block_a_plan_and_are_kept():
    rules = [{"rule": "CN-001", "requirement": "x"}]
    review = PlanReview(verdict="PASS", rules=[{"rule": "CN-001", "status": "PASS", "note": "ok"}], issues=[], suggestions=["Add a district map."])
    decision = _plan_decision(review, rules, [], "REVIEW_UNAVAILABLE")
    assert decision.outcome == "APPROVED" and decision.suggestions == ["Add a district map."]
    blocking = PlanReview(verdict="REPAIR", rules=[{"rule": "CN-001", "status": "PASS", "note": "ok"}], issues=["Do not state the partnership as fact."], suggestions=[])
    assert _plan_decision(blocking, rules, [], "REVIEW_UNAVAILABLE").outcome == "OBJECTIONS"


def test_older_answers_without_suggestions_still_parse():
    assert PlanReview.model_validate({"verdict": "PASS", "rules": [], "issues": []}).suggestions == []
    assert ResultsReview.model_validate({"rules": [], "classified": [], "issues": []}).suggestions == []


from tests.test_one_start import works_client  # noqa: E402,F401 (the fixture)


def test_a_repaired_plan_is_reviewed_against_the_earlier_issues(works_client):  # noqa: F811
    from tests.test_one_start import H, _coursework, _done, _settled

    client = works_client
    seen = []

    def review(payload):
        seen.append(payload.get("previousIssues"))
        rules = [{"rule": r["rule"], "status": "PASS", "note": "Met."} for r in payload.get("rules", [])]
        if len(seen) == 1:
            return {"verdict": "REPAIR", "rules": rules, "issues": ["Do not state the partnership as fact."], "suggestions": []}
        return {"verdict": "PASS", "rules": rules, "issues": [], "suggestions": ["A stronger opening."]}

    client.models.overrides["w_plan_review"] = review
    work = _coursework(client)
    client.post(f"/api/works/{work['id']}/start", headers=H)
    work = _settled(client, f"/api/works/{work['id']}", _done)
    assert seen[0] is None and seen[1] == ["Do not state the partnership as fact."]
    assert work["documents"] and work["planReview"]["outcome"] == "APPROVED" and work["planReview"]["suggestions"] == ["A stronger opening."]


def test_target_plausibility_cannot_fail_while_the_applicants_figures_are_gaps():
    """Live check 2026-10-04: the reviewer failed FP-028 ("the applicant has not supplied the baselines and
    targets") in every round, so no One Start funding proposal without figures could ever be approved."""
    from app.works.models import Indicator, Outcome, Output, ResultsModel
    from app.works.pipeline import _results_decision

    rules = [{"rule": "FP-028", "requirement": "Targets are plausible."}, {"rule": "FP-020", "requirement": "Outputs are deliverables."}]
    review = ResultsReview.model_validate({
        "rules": [{"rule": "FP-028", "status": "FAIL", "note": "The applicant has not supplied the baselines and targets."},
                  {"rule": "FP-020", "status": "PASS", "note": "Fine."}],
        "classified": [{"id": i, "statedAs": level, "reads": level, "note": "ok"} for i, level in (("G1", "goal"), ("O1", "outcome"), ("OP1", "output"))],
        "issues": []})
    gaps = ResultsModel(outcomes=[Outcome(id="O1", statement="Mothers reach care")], outputs=[Output(id="OP1", statement="Referral fund", outcome_id="O1")],
                        indicators=[Indicator(id="I1", result_id="O1", level="outcome", unit="%")])
    assert _results_decision(review, gaps, rules, "REVIEW_UNAVAILABLE", []).outcome == "APPROVED"
    given = gaps.model_copy(update={"indicators": [Indicator(id="I1", result_id="O1", level="outcome", unit="%", baseline=20, target=90)]})
    decision = _results_decision(review, given, rules, "REVIEW_UNAVAILABLE", [])
    assert decision.outcome == "OBJECTIONS" and any(o.startswith("FP-028") for o in decision.objections)  # with figures, the judgement stands
