"""The academic concept note (Research Proposals → Concept note, owner decision 2026-09-30): the UCU
concept paper on the proposal engine, which never starts or charges for a chapter by itself
(Codex review 2026-09-30 #8), and continues into the full proposal on the same project."""

from tests.fake_models import PLAN
from tests.test_api import STUDENT, wait
from tests.test_proposals import DETAILS, _approved, _run


def test_a_concept_note_never_starts_chapter_one_and_continues_into_the_full_proposal(client):
    project = client.post("/api/projects", headers=STUDENT, json={**DETAILS, "goal": "CONCEPT"}).json()
    assert project["goal"] == "CONCEPT"
    quoted = client.post(f"/api/projects/{project['id']}/steps", headers=STUDENT, json={"step": "PLAN"}).json()
    assert quoted["then"] == []  # no Chapter One shown with the plan's price
    client.post(f"/api/projects/{project['id']}/steps/{quoted['job']['id']}/submit", headers=STUDENT, json={"quoteId": quoted["quote"]["id"]})
    wait(client, quoted["job"]["id"])
    approved = _approved(client, project["id"], sampleSize={**PLAN["sampleSize"], "populationSource": "DHO records"})
    assert approved["activeJob"] is None and approved["autoChapterOne"] is False  # nothing started, nothing charged
    refused = client.post(f"/api/projects/{project['id']}/steps", headers=STUDENT, json={"step": "CHAPTER_1"})
    assert refused.status_code == 400 and refused.json()["code"] == "CONCEPT_ONLY"
    job = _run(client, project["id"], "CONCEPT")
    assert job["status"] == "COMPLETED", job.get("failure")
    paper = client.get(f"/api/projects/{project['id']}/chapters/4", headers=STUDENT).json()
    checks = {i["id"]: i for i in paper["readiness"]}
    assert checks["C4-METHODS"]["status"] == "PASS" and checks["C4-METHODS"]["basis"] == "CODE" and checks["C4-ETHICS"]["basis"] == "CODE"
    continued = client.post(f"/api/projects/{project['id']}/continue", headers=STUDENT).json()
    assert continued["goal"] == "FULL" and continued["activeJob"] is None
    chapter = client.post(f"/api/projects/{project['id']}/steps", headers=STUDENT, json={"step": "CHAPTER_1"})
    assert chapter.status_code == 200, chapter.json()
