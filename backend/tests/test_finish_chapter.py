"""Phase 6 (owner go-ahead 2026-09-29, Codex's conditions): a new chapter delivers the sections both
reviewers approved, the rest are recorded as not written yet, and "Finish chapter" writes only those,
priced so that the draft and its finish never cost more than one chapter."""

import pytest

from tests.test_api import STUDENT
from tests.test_audit_20260928 import _chapter_ready
from tests.test_proposals import _run


def _reject_first_section(client):
    """Both reviewers keep refusing one section (the first one they see) in every round."""
    target: list[str] = []

    def review(payload):
        keys = [s["key"] for s in payload["sections"]]
        if not target:
            target.append(keys[0])
        return {"results": [{"key": k, "grade": "REPAIR" if k == target[0] else "PASS", "issues": ["Not supported."] if k == target[0] else [], "note": ""} for k in keys]}

    client.models.overrides["p_review"] = review
    client.models.overrides["p_review_peer"] = review
    return target


def _chapter_price(fixed_client, pid, step="CHAPTER_1"):
    quoted = fixed_client.post(f"/api/projects/{pid}/steps", headers=STUDENT, json={"step": step}).json()
    return quoted["quote"]["amount"]


@pytest.fixture
def partial(fixed_client, monkeypatch):
    """A project whose Chapter One was delivered without its first section (partial chapters on)."""
    from app.runtime import get_runtime

    monkeypatch.setattr(get_runtime().settings, "partial_chapters", True)
    pid = _chapter_ready(fixed_client)
    full = _chapter_price(fixed_client, pid)
    target = _reject_first_section(fixed_client)
    job = _run(fixed_client, pid, "CHAPTER_1")
    fixed_client.models.overrides.pop("p_review")
    fixed_client.models.overrides.pop("p_review_peer")
    return pid, job, full, target[0]


def test_a_new_chapter_delivers_its_approved_sections(fixed_client, partial):
    pid, job, full, missing_key = partial
    assert job["status"] == "COMPLETED" and job["outcome"] == "PARTIAL"
    assert 0 < job["billing"]["charged"] < full  # only the delivered share
    chapter = fixed_client.get(f"/api/projects/{pid}/chapters/1", headers=STUDENT).json()
    assert len(chapter["missing"]) == 1 and all(s["key"] != missing_key for s in chapter["sections"])
    assert any(r["status"] == "MISSING" and r["basis"] == "CODE" for r in chapter["readiness"])
    assert any(w.startswith("These sections are not written yet:") for w in chapter["warnings"])


def test_an_incomplete_chapter_cannot_be_approved(fixed_client, partial):
    pid, _, _, _ = partial
    version = fixed_client.get(f"/api/projects/{pid}", headers=STUDENT).json()["chapters"][0]["current"]
    refused = fixed_client.post(f"/api/projects/{pid}/chapters/1", headers=STUDENT, json={"version": version, "approved": True})
    assert refused.status_code == 400 and refused.json()["code"] == "CHAPTER_INCOMPLETE"


def test_finishing_writes_only_the_missing_sections_and_never_costs_more_than_a_chapter(fixed_client, partial):
    pid, first, full, missing_key = partial
    quoted = fixed_client.post(f"/api/projects/{pid}/steps", headers=STUDENT, json={"step": "COMPLETE_1"}).json()
    assert first["billing"]["charged"] + quoted["quote"]["amount"] <= full + 100  # rounding to UGX 100 only
    before = fixed_client.get(f"/api/projects/{pid}/chapters/1", headers=STUDENT).json()
    job = _run(fixed_client, pid, "COMPLETE_1")
    assert job["status"] == "COMPLETED", job.get("failure")
    drafted = [r for t, r in zip(fixed_client.models.tasks, fixed_client.models.requests, strict=True) if t == "p_draft"][-1]
    assert f'"key": "{missing_key}"' in drafted and drafted.count('"key": "') == 1  # the missing section only
    chapter = fixed_client.get(f"/api/projects/{pid}/chapters/1", headers=STUDENT).json()
    assert chapter["missing"] == [] and any(s["key"] == missing_key for s in chapter["sections"])
    kept = {s["key"]: s["paragraphs"] for s in before["sections"]}
    assert all(s["paragraphs"] == kept[s["key"]] for s in chapter["sections"] if s["key"] in kept)  # approved sections unchanged
    assert first["billing"]["charged"] + job["billing"]["charged"] <= full + 100
    version = fixed_client.get(f"/api/projects/{pid}", headers=STUDENT).json()["chapters"][0]["current"]
    assert fixed_client.post(f"/api/projects/{pid}/chapters/1", headers=STUDENT, json={"version": version, "approved": True}).status_code == 200


def test_the_same_finish_cannot_be_bought_twice(fixed_client, partial):
    pid, _, _, _ = partial
    first = fixed_client.post(f"/api/projects/{pid}/steps", headers=STUDENT, json={"step": "COMPLETE_1"}).json()
    second = fixed_client.post(f"/api/projects/{pid}/steps", headers=STUDENT, json={"step": "COMPLETE_1"}).json()  # another tab
    fixed_client.post(f"/api/projects/{pid}/steps/{first['job']['id']}/submit", headers=STUDENT, json={"quoteId": first["quote"]["id"]})
    from tests.test_api import wait

    assert wait(fixed_client, first["job"]["id"])["status"] == "COMPLETED"
    late = fixed_client.post(f"/api/projects/{pid}/steps/{second['job']['id']}/submit", headers=STUDENT, json={"quoteId": second["quote"]["id"]})
    assert late.status_code in (400, 409)


def test_nothing_to_finish_and_nothing_written_are_not_charged(fixed_client, partial):
    pid, _, _, _ = partial
    fixed_client.models.overrides["p_review_peer"] = lambda payload: {"results": [{"key": s["key"], "grade": "REPAIR", "issues": ["No."], "note": ""} for s in payload["sections"]]}
    job = _run(fixed_client, pid, "COMPLETE_1")
    assert job["status"] == "FAILED" and job["failure"]["code"] == "NOTHING_WRITTEN" and job["billing"]["charged"] == 0
    fixed_client.models.overrides.pop("p_review_peer")
    assert _run(fixed_client, pid, "COMPLETE_1")["status"] == "COMPLETED"
    refused = fixed_client.post(f"/api/projects/{pid}/steps", headers=STUDENT, json={"step": "COMPLETE_1"})
    assert refused.status_code == 400 and refused.json()["code"] == "NOTHING_TO_FINISH"


def test_a_changed_plan_needs_the_chapter_written_again(fixed_client, partial):
    from tests.test_proposals import _approved

    pid, _, _, _ = partial
    project = fixed_client.get(f"/api/projects/{pid}", headers=STUDENT).json()
    _approved(fixed_client, pid, title=project["plan"]["title"] + " in Mukono")
    refused = fixed_client.post(f"/api/projects/{pid}/steps", headers=STUDENT, json={"step": "COMPLETE_1"})
    assert refused.status_code == 400 and refused.json()["code"] == "PLAN_CHANGED"
