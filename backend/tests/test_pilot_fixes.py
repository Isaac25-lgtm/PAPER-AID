"""Defects the Phase 4 real-model pilot found (2026-09-29), each with its correct outcome."""

from app.ai.orchestration import PROMPTS, STEPS
from app.proposals.pipeline import _shorten


def test_an_over_long_plan_field_ends_at_a_complete_sentence():
    text = "Caregivers of children aged 6-23 months are eligible. Four-dose completion will be assessed only among children for whom all four doses were due."
    assert _shorten(text, 90) == "Caregivers of children aged 6-23 months are eligible."
    assert _shorten("one very long sentence without any stop " * 5, 60) is None  # nothing to end at: never cut mid-way


def test_a_plan_is_not_refused_for_lacking_the_proposals_reference_list():
    prompt = PROMPTS[STEPS["p_plan_review"].prompt]
    assert STEPS["p_plan_review"].prompt == STEPS["p_plan_review_peer"].prompt == "p-plan-review-v2"
    assert "never carries a reference list" in prompt and "apply to the chapters, not to this plan" in prompt
