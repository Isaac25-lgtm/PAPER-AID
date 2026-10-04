"""An uploaded guide overrides the standard guide; where it departs a lot from it, the student confirms
each point or takes the standard guide's version (owner decision 2026-10-04)."""

import copy
import json

from tests.test_api import STUDENT
from tests.test_proposals import _create


def _use_guide(pid, change):
    from app.proposals import profile, rulebook
    from app.runtime import get_runtime

    rt = get_runtime()
    book = copy.deepcopy(rulebook.load(rulebook.DEFAULT))
    book.update({"id": "custom-0123456789ab", "custom": True, "institution": "Example University"})
    change(book)
    book["departures"] = profile.departures(book)
    rt.files.put(rulebook.stored_path(book["id"]), json.dumps(book).encode(), "application/json")
    rt.store.update_project(pid, lambda p: p.model_copy(update={"rulebook": book["id"], "profiles": [book["id"]]}))
    return book


def _no_ethics_one_objective(book):
    book["chapters"][2]["sections"] = [s for s in book["chapters"][2]["sections"] if s["key"] != "ethics"]
    book["objectives"] = book["questions"] = {"min": 1, "max": 1}


def test_departures_are_asked_about_and_block_start_until_answered(client):
    pid = _create(client)["id"]
    _use_guide(pid, _no_ethics_one_objective)
    view = client.get(f"/api/projects/{pid}", headers=STUDENT).json()
    ids = [q["id"] for q in view["guideQuestions"]]
    assert ids == ["section:3:ethics", "objectives"] and view["institution"] == "Example University"
    assert "Ethical Considerations" in view["guideQuestions"][0]["question"]
    blocked = client.post(f"/api/projects/{pid}/start", headers=STUDENT, json={})
    assert blocked.status_code == 400 and blocked.json()["code"] == "GUIDE_QUESTIONS"
    kept = client.post(f"/api/projects/{pid}/guide-answers", headers=STUDENT, json={"id": "objectives", "answer": "KEEP"}).json()
    assert [q["id"] for q in kept["guideQuestions"]] == ["section:3:ethics"]
    standard = client.post(f"/api/projects/{pid}/guide-answers", headers=STUDENT, json={"id": "section:3:ethics", "answer": "STANDARD"}).json()
    assert standard["guideQuestions"] == [] and standard["rulebook"] != "custom-0123456789ab"  # a new profile: saved ones never change
    from app.proposals import rulebook
    from app.runtime import get_runtime

    book = rulebook.load(standard["rulebook"])
    chapter = next(c for c in book["chapters"] if c["number"] == 3)
    assert any(s["heading"] == "Ethical Considerations" for s in chapter["sections"]) and abs(sum(s["share"] for s in chapter["sections"]) - 1) < 0.01
    assert book["objectives"] == {"min": 1, "max": 1}  # kept as the guide says
    record = get_runtime().store.get_project(pid)
    assert record.guide_answers["objectives"]["answer"] == "KEEP" and record.guide_answers["section:3:ethics"]["answer"] == "STANDARD"
    again = client.post(f"/api/projects/{pid}/guide-answers", headers=STUDENT, json={"id": "objectives", "answer": "STANDARD"})
    assert again.status_code == 409


def test_the_standard_guide_asks_nothing(client):
    view = client.get(f"/api/projects/{_create(client)['id']}", headers=STUDENT).json()
    assert view["guideQuestions"] == [] and view["institution"] == "Standard guide"
