"""Phase 2 of the agreed four-model plan (owner go-ahead 2026-09-29): skipped passages are asked
again once, incomplete or unscorable checks are not charged, unapproved university rules are
skipped and refunded, institution profiles need both approvals, and frontier guidance is a switch."""

import io

import pytest
from docx import Document

from app.ai import orchestration
from app.core.config import Settings
from app.jobs.models import Engine
from app.jobs.pipeline import NOT_CHARGED_CHECK, TEMPLATE_SKIPPED
from app.pricing import quote
from app.runtime import get_runtime
from tests.conftest import fixture_bytes
from tests.test_ai import MemoryCache, ScriptedProvider, real_settings, runner_with
from tests.test_ai_coverage import _judgment, _passage
from tests.test_api import STUDENT, get_quote, wait
from tests.test_profiles import _guide
from tests.test_proposals import _create, _run


@pytest.fixture(autouse=True)
def dual_approval_engine(monkeypatch):
    """This file pins the policy of jobs priced before one accountable final reviewer (owner decision
    2026-09-30): both approvals and Opus's guidance, which those jobs keep."""
    monkeypatch.setenv("SINGLE_REVIEWER", "false")
    monkeypatch.setenv("FRONTIER_GUIDANCE", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

# --- P1: a skipped passage is asked about once more, with its own request identity ---------------


def test_a_skipped_passage_is_asked_about_again_once(monkeypatch):
    scripted = ScriptedProvider({"analyse": [{"blocks": [_judgment("b1")]}, {"blocks": [_judgment("b2")]}]})
    runner, _ = runner_with(monkeypatch, scripted)
    answers, seen = runner.analyse([_passage("b1"), _passage("b2")], [], {})
    assert seen == {"b1", "b2"} and set(answers) == {"b1", "b2"} and scripted.calls == ["analyse", "analyse"]


def test_the_retry_is_never_answered_from_a_saved_incomplete_answer(monkeypatch):
    cache = MemoryCache()
    scripted = ScriptedProvider({"analyse": [{"blocks": []}, {"blocks": [_judgment("b1")]}]})
    runner, _ = runner_with(monkeypatch, scripted, cache=cache)
    _, seen = runner.analyse([_passage("b1")], [], {})
    assert seen == {"b1"} and scripted.calls == ["analyse", "analyse"]  # the empty answer was not replayed
    # a replay of the whole run (a retried stage) uses both saved answers and pays for nothing
    again = ScriptedProvider({"analyse": []})
    replay, _ = runner_with(monkeypatch, again, cache=cache)
    assert replay.analyse([_passage("b1")], [], {})[1] == {"b1"} and again.calls == []


def test_there_is_only_one_retry(monkeypatch):
    scripted = ScriptedProvider({"analyse": [{"blocks": []}, {"blocks": []}]})
    runner, _ = runner_with(monkeypatch, scripted)
    assert runner.analyse([_passage("b1")], [], {})[1] == set() and len(scripted.calls) == 2


def test_older_engines_never_retry(monkeypatch):
    scripted = ScriptedProvider({"analyse": [{"blocks": []}]})
    monkeypatch.setattr(orchestration, "provider_for", lambda ref, settings: (scripted, ref.split(":")[-1]))
    old = Engine(lead_model="openai:gpt-6-sol", writer_model="anthropic:claude-opus-5-5", prompts={"analyse": "analyse-v2"})
    orchestration.AIRunner(real_settings(), lambda c: None, lambda: 0, 5, engine=old).analyse([_passage("b1")], [], {})
    assert scripted.calls == ["analyse"]


def test_the_quote_reserves_the_retry_for_every_checker():
    settings = Settings(_env_file=None)
    engine = orchestration.current_engine(settings)
    without = engine.model_copy(update={"explicit_coverage": False})
    assert quote.analysis_usd(settings, 5000, engine) == pytest.approx(2 * quote.analysis_usd(settings, 5000, without))


# --- P3: no complete result, no charge for the check -------------------------------------------


def _check(client, name="simple_essay.docx", academic=False):
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    assert client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": (name, fixture_bytes(name), "application/octet-stream")}).status_code == 200
    priced = get_quote(client, job_id, {"writing": "AI_CHECK", "academic": academic})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": priced["id"]})
    return priced, wait(client, job_id)


def test_an_incomplete_check_is_not_charged(fixed_client):
    fixed_client.models.overrides["analyse_peer"] = lambda payload: {"blocks": []}
    start = fixed_client.get("/api/wallet", headers=STUDENT).json()["available"]
    _, job = _check(fixed_client)
    assert job["status"] == "COMPLETED" and job["analysis"]["coverageComplete"] is False
    assert job["billing"]["charged"] == 0 and NOT_CHARGED_CHECK in job["warnings"]
    assert fixed_client.get("/api/wallet", headers=STUDENT).json()["available"] == start


def test_other_parts_of_the_job_are_still_charged(fixed_client):
    fixed_client.models.overrides["analyse_peer"] = lambda payload: {"blocks": []}
    priced, job = _check(fixed_client, academic=True)
    academic = next(line["amount"] for line in priced["lines"] if line["service"] == "ACADEMIC")
    assert job["billing"]["charged"] == academic


def test_a_paper_nothing_can_be_scored_in_is_refused_before_pricing(client):
    doc = Document()
    for i in range(6):
        doc.add_paragraph(f"Short paragraph {i} contains only ten words for this check.")
    source = io.BytesIO()
    doc.save(source)
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    uploaded = client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("short.docx", source.getvalue(), "application/octet-stream")})
    assert uploaded.status_code == 200
    refused = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": {"writing": "AI_CHECK", "academic": False}})
    assert refused.status_code == 400 and refused.json()["code"] == "NOT_SCORABLE"
    formatting = client.post(f"/api/jobs/{job_id}/quote", headers=STUDENT, json={"selection": {"writing": "NONE", "formatting": "FORMAT", "preset": "apa7"}})
    assert formatting.status_code == 200  # other services on the same paper still work


# --- P5: unapproved university rules are skipped and refunded -----------------------------------


def _template_job(client, selection):
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    for role, name in (("source", "simple_essay.docx"), ("guideline", "guideline_university.docx")):
        assert client.post(f"/api/jobs/{job_id}/files/{role}", headers=STUDENT, files={"file": (name, fixture_bytes(name), "application/octet-stream")}).status_code == 200
    priced = get_quote(client, job_id, selection)
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": priced["id"]})
    return priced, wait(client, job_id, timeout=120)


REJECT_RULES = {"pass": False, "problems": [{"field": "font", "problem": "Not what the guide says.", "fix": "Use the guide's font."}]}


def test_unapproved_university_rules_are_skipped_and_the_rest_delivered(fixed_client):
    fixed_client.models.overrides["spec_review_peer"] = lambda payload: REJECT_RULES
    priced, job = _template_job(fixed_client, {"writing": "REFINE", "academic": False, "formatting": "TEMPLATE_FORMAT"})
    assert job["status"] == "COMPLETED" and job["outcome"] == "PARTIAL" and TEMPLATE_SKIPPED in job["warnings"]
    assert job["formatting"] is None
    outputs = {o["id"] for o in job["outputs"]}
    assert {"paper", "paper-apa"} <= outputs  # the refined paper, and the usual APA version to choose
    template = next(line["amount"] for line in priced["lines"] if line["service"] == "TEMPLATE_FORMAT")
    assert 0 < job["billing"]["charged"] <= priced["amount"] - template


def test_a_template_only_job_with_unapproved_rules_fails_without_charge(fixed_client):
    fixed_client.models.overrides["spec_review"] = lambda payload: REJECT_RULES
    _, job = _template_job(fixed_client, {"writing": "NONE", "formatting": "TEMPLATE_FORMAT"})
    assert job["status"] == "FAILED" and job["failure"]["code"] == "TEMPLATE_NOT_APPROVED" and job["billing"]["charged"] == 0


# --- P6: an institution profile needs both approvals; the student chooses the structure ---------


def _with_guide(client):
    project = _create(client)
    uploaded = client.post(f"/api/projects/{project['id']}/guide", headers=STUDENT, files={"file": ("guide.docx", _guide(), "application/octet-stream")})
    assert uploaded.status_code == 200
    return project["id"]


@pytest.mark.parametrize("reviewer", ["p_profile_review", "p_profile_review_peer"])
def test_either_frontier_can_refuse_an_institution_profile(client, reviewer):
    pid = _with_guide(client)
    client.models.overrides[reviewer] = lambda payload: {"approved": False, "issues": ["Chapter two is not in the guide."]}
    job = _run(client, pid, "PROFILE")
    assert job["status"] == "FAILED" and job["failure"]["code"] == "PROFILE_NOT_APPROVED" and job["billing"]["charged"] == 0
    project = client.get(f"/api/projects/{pid}", headers=STUDENT).json()
    assert not project["rulebook"].startswith("custom-") and project["guideRead"] is False


def test_writing_waits_until_the_student_chooses_a_structure(client):
    pid = _with_guide(client)
    refused = client.post(f"/api/projects/{pid}/steps", headers=STUDENT, json={"step": "PLAN"})
    assert refused.status_code == 400 and refused.json()["code"] == "GUIDE_UNREAD"
    chosen = client.post(f"/api/projects/{pid}/rulebook/default", headers=STUDENT)
    assert chosen.status_code == 200 and chosen.json()["guideName"] is None
    assert client.post(f"/api/projects/{pid}/steps", headers=STUDENT, json={"step": "PLAN"}).status_code == 200


def test_the_approved_profile_is_exactly_the_one_used(client):
    pid = _with_guide(client)
    job = _run(client, pid, "PROFILE")
    assert job["status"] == "COMPLETED"
    tasks = client.models.tasks
    assert tasks.index("p_profile_finalise") < tasks.index("p_profile_review") < tasks.index("p_profile_review_peer")
    reviewed = [r for t, r in zip(tasks, client.models.requests, strict=True) if t == "p_profile_review_peer"][-1]
    project = client.get(f"/api/projects/{pid}", headers=STUDENT).json()
    assert project["rulebook"] in reviewed  # the reviewed profile carries the id it is stored under


# --- P7: frontier guidance can be switched off without losing either approval --------------------


def test_guidance_can_be_switched_off_but_both_approvals_remain(client, monkeypatch):
    monkeypatch.setattr(get_runtime().settings, "frontier_guidance", False)
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": ("simple_essay.docx", fixture_bytes("simple_essay.docx"), "application/octet-stream")})
    priced = get_quote(client, job_id, {"writing": "REFINE", "academic": False})
    client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": priced["id"]})
    assert wait(client, job_id)["status"] == "COMPLETED"
    assert "guide" not in client.models.tasks and {"review", "review_peer"} <= set(client.models.tasks)
    settings = Settings(_env_file=None)
    on = orchestration.current_engine(settings)
    passages = quote.worst_passages(2000, 0.5)
    assert quote.refinement_usd(settings, passages, engine=on.model_copy(update={"frontier_guidance": False})) < quote.refinement_usd(settings, passages, engine=on)
