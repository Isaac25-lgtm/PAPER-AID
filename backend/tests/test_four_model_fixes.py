"""Phase 1 of the agreed four-model plan (Claude audit and Codex review, 2026-09-29): each test is a
reported defect with its correct outcome."""

import io
import json
import re

import pytest
from docx import Document

from app.ai import orchestration
from app.ai.orchestration import PROMPTS, STEPS, current_engine, model_for_engine, work_engine
from app.analysis.signals import MODEL_SCORE
from app.core.config import Settings
from app.core.errors import RetryableStageError
from app.jobs.models import Engine
from app.pricing import quote
from app.proposals import evidence
from app.proposals.ai import ProposalRunner
from app.runtime import get_runtime
from tests.test_ai import ScriptedProvider, real_settings, runner_with
from tests.test_ai_coverage import _judgment, _passage
from tests.test_api import STUDENT, _judge_all, _submit, enable_score
from tests.test_audit_20260928 import _chapter_ready
from tests.test_audit_20260928 import _run as run_step

# --- F1: approved text is delivered exactly as approved -----------------------------------------


@pytest.mark.parametrize("paragraph", ["Malaria remains a burden.  Uptake is low.", "Uptake is low. ", "Line one.\nLine two.", " "])
def test_cleanup_that_removes_nothing_returns_the_text_unchanged(paragraph):
    assert evidence.strip_unsupported(paragraph, {}, set(), "") == paragraph


def test_cleanup_still_removes_an_untraceable_citation():
    assert evidence.strip_unsupported("As Smith (2019) showed, it matters. The study will follow the plan.", {}, set(), "") == "The study will follow the plan."


def test_a_chapter_with_double_spaces_and_line_breaks_is_delivered_as_written(client):
    pid = _chapter_ready(client)
    original = client.models.default

    spaced_text = "Malaria remains a burden.  Uptake is low.\nCaregivers travel far. "

    def spaced(payload):
        answer = original("p_draft", payload)
        for section in answer["sections"]:
            section["paragraphs"] = [spaced_text, *section["paragraphs"]]
        return answer

    client.models.overrides["p_draft"] = spaced
    job = run_step(client, pid, "CHAPTER_1")
    assert job["status"] == "COMPLETED", job.get("failure")
    rt = get_runtime()
    stored = json.loads(rt.files.get(f"{rt.store.get(job['id']).storage_prefix()}/internal/chapter.json"))
    assert all(s["paragraphs"][0] == spaced_text for s in stored["sections"])  # exactly the approved wording
    last = [r for t, r in zip(client.models.tasks, client.models.requests, strict=True) if t == "p_review"][-1]  # the one final reviewer
    assert json.dumps(spaced_text)[1:-1] in last


def test_older_engines_keep_removing_untraceable_text_after_review(client, monkeypatch):
    monkeypatch.setattr(get_runtime().settings, "require_dual_approval", False)
    pid = _chapter_ready(client)
    client.models.overrides["p_draft"] = lambda payload: {
        "sections": [{"key": s["key"], "paragraphs": ["As Smith (2019) showed, it matters. The study will follow the plan."], "table": {"caption": "", "rows": []}} for s in payload["sections"]]
    }
    job = run_step(client, pid, "CHAPTER_1")
    assert job["status"] == "COMPLETED" and any("removed sentences" in w for w in job["warnings"])
    assert "p_review_peer" not in client.models.tasks


# --- F4: every prompt describes its role truthfully ---------------------------------------------


def test_no_prompt_gives_a_model_a_role_it_does_not_have():
    engine = current_engine(Settings(_env_file=None))
    models_by_prompt: dict[str, set[str]] = {}
    engine = work_engine(Settings(_env_file=None), "FUNDING_PROPOSAL")  # every role, the works roles included
    for task in STEPS:
        if STEPS[task].role == "ADJUDICATOR" and not engine.roles.get("ADJUDICATOR"):
            continue  # no adjudicator is configured by default
        models_by_prompt.setdefault(engine.prompts[task], set()).add(model_for_engine(engine, task))
    for prompt, models in models_by_prompt.items():
        opening = PROMPTS[prompt].split("\n\n")[0]
        if len(models) > 1:  # shared by different models: no single-role claim
            assert "You are the lead" not in opening and "you finalised" not in PROMPTS[prompt], prompt
    for task in ("finalise", "p_finalise", "spec_finalise", "p_profile_finalise"):
        assert "You drafted" not in PROMPTS[engine.prompts[task]], task
    for task in ("guide", "p_guide", "spec_guide", "p_profile_guide"):
        text = PROMPTS[engine.prompts[task]]
        assert "carry it out" not in text and "independently" in text, task


# --- F5: explicit coverage is part of the frozen engine, not a prompt name -------------------------


def test_explicit_coverage_follows_the_frozen_engine(monkeypatch):
    scripted = ScriptedProvider({"analyse": [{"blocks": []}, {"blocks": []}, {"blocks": []}]})  # strict: answer and retry; legacy: one
    monkeypatch.setattr(orchestration, "provider_for", lambda ref, settings: (scripted, ref.split(":")[-1]))
    prompts = {"analyse": "analyse-v2"}
    strict = Engine(lead_model="openai:gpt-6-sol", writer_model="anthropic:claude-opus-5-5", prompts=prompts, explicit_coverage=True)
    legacy = Engine(lead_model="openai:gpt-6-sol", writer_model="anthropic:claude-opus-5-5", prompts=prompts)
    assert orchestration.AIRunner(real_settings(), lambda c: None, lambda: 0, 5, engine=strict).analyse([_passage("b1")], [], {})[1] == set()
    assert orchestration.AIRunner(real_settings(), lambda c: None, lambda: 0, 5, engine=legacy).analyse([_passage("b1")], [], {})[1] == {"b1"}
    assert current_engine(Settings(_env_file=None)).explicit_coverage is True


# --- F6: a provider can never set the combined score --------------------------------------------


def test_a_provider_cannot_supply_the_combined_score(monkeypatch):
    runner, _ = runner_with(monkeypatch, ScriptedProvider({"analyse": [{"blocks": [{**_judgment("b1"), "review_score": 0.99, "reviewer_bands": ["high"]}]}]}))
    answers, _ = runner.analyse([_passage("b1")], [], {})
    assert answers["b1"].score == MODEL_SCORE["low"] and answers["b1"].bands == ["low"]


# --- F7: formatting approval must be a real boolean ---------------------------------------------


def test_a_loose_yes_is_not_a_formatting_approval(monkeypatch):
    runner, _ = runner_with(monkeypatch, ScriptedProvider({"spec_review": [{"pass": "yes", "problems": []}]}))
    with pytest.raises(RetryableStageError):  # malformed: never cached, never an approval
        runner.review_spec("guide", {})


# --- F9: an older engine is priced with its own prompts -----------------------------------------


def test_an_older_engine_is_priced_with_its_own_prompt_versions():
    settings = Settings(_env_file=None)
    old = Engine(lead_model="openai:gpt-6-sol", writer_model="anthropic:claude-opus-5-5", prompts={"analyse": "analyse-v2"})
    provider, _, model = "openai:gpt-6-sol".partition(":")
    expected = orchestration.costs.estimate_usd(provider, model, len(PROMPTS["analyse-v2"]), STEPS["analyse"].max_tokens, settings.model_prices)
    assert quote._step_usd(settings, "analyse", 0, 0, old) == pytest.approx(expected)


# --- F13: a proposal review that asks for repair is never a pass, whatever the engine -----------


@pytest.mark.parametrize("dual", [False, True])
def test_a_repair_grade_without_issues_is_not_a_pass(monkeypatch, dual):
    answer = {"results": [{"key": "problem", "grade": "REPAIR", "issues": [], "note": ""}]}
    scripted = ScriptedProvider({"p_review": [answer], "p_review_peer": [answer]})
    monkeypatch.setattr(orchestration, "provider_for", lambda ref, settings: (scripted, ref.split(":")[-1]))
    settings = real_settings(require_dual_approval=dual)
    runner = ProposalRunner(settings, lambda c: None, lambda: 0, 5, engine=current_engine(settings))
    grade = runner.grade([{"key": "problem", "text": ["A claim."], "_words": "A claim."}], {})["problem"]
    assert grade.grade == "REPAIR" and grade.issues


# --- Disagreement: only low against high is uncertainty ------------------------------------------


def test_one_band_differences_are_averaged_not_flagged(client):
    client.models.overrides["analyse_peer"] = _judge_all(lambda b: {"riskBand": "moderate"})
    _, job = _submit(client, {"writing": "AI_CHECK", "academic": False})
    assert job["analysis"]["disagreementBlocks"] == [] and job["analysis"]["coverageComplete"] is True


def test_low_against_high_everywhere_makes_confidence_low(client):
    enable_score()
    client.models.overrides["analyse_peer"] = _judge_all(lambda b: {"riskBand": "high"})
    _, job = _submit(client, {"writing": "AI_CHECK", "academic": False})
    assert job["analysis"]["disagreementBlocks"] and job["analysis"]["confidence"] == "LOW"


def test_one_uncertain_passage_in_a_long_paper_is_flagged_without_low_confidence(client):
    enable_score()
    chosen: list[str] = []

    def one_high(b):
        chosen.append(b["id"]) if not chosen else None
        return {"riskBand": "high"} if b["id"] == chosen[0] else {}

    client.models.overrides["analyse_peer"] = _judge_all(one_high)
    _, job = _submit(client, {"writing": "AI_CHECK", "academic": False}, name="dissertation_long.docx", timeout=180)
    assert job["analysis"]["disagreementBlocks"] == chosen[:1]
    assert job["analysis"]["coverageComplete"] is True and job["analysis"]["confidence"] != "HIGH"  # uncertainty caps it


def test_the_report_names_uncertain_passages_without_ids(client):
    client.models.overrides["analyse_peer"] = _judge_all(lambda b: {"riskBand": "high"})
    job_id, job = _submit(client, {"writing": "AI_CHECK", "academic": False})
    report = Document(io.BytesIO(client.get(f"/api/jobs/{job_id}/outputs/writing-report", headers=STUDENT).content))
    text = "\n".join(p.text for p in report.paragraphs)
    count = len(job["analysis"]["disagreementBlocks"])
    assert f"uncertain for {count} passage" in text and "“" in text and "AI-likeness" not in text
    assert not re.search(r"\bb\d{3,}\b", text) and "Assessments differed" not in text
