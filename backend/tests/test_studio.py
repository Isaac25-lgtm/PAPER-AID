"""One screen from upload to final draft (owner request 2026-09-29): the paper shows as soon as it is
uploaded, the check gives a percentage, and redrafting, formatting and the student's own requests
for changes continue from the same paper."""

import io

from docx import Document

from tests.conftest import fixture_bytes
from tests.test_api import STUDENT, enable_score, start_job, wait
from tests.test_proposal_v2 import _with_chapter_one

CHECK = {"writing": "AI_CHECK", "academic": False}


def _draft(client, name="simple_essay.docx"):
    job_id = client.post("/api/jobs", headers=STUDENT).json()["id"]
    client.post(f"/api/jobs/{job_id}/files/source", headers=STUDENT, files={"file": (name, fixture_bytes(name), "application/octet-stream")})
    return job_id


def _run(client, selection, name="simple_essay.docx"):
    job_id, quote = start_job(client, name=name, selection=selection)
    assert client.post(f"/api/jobs/{job_id}/submit", headers=STUDENT, json={"quoteId": quote["id"]}).status_code == 200
    return job_id, wait(client, job_id, timeout=120)


def test_the_paper_shows_as_soon_as_it_is_uploaded(client):
    job_id = _draft(client)
    doc = client.get(f"/api/jobs/{job_id}/document", headers=STUDENT)
    assert doc.status_code == 200
    body = doc.json()
    assert len(body["blocks"]) > 3 and body["changes"] == [] and any(b["text"] for b in body["blocks"])


def test_the_check_gives_a_percentage_consistent_with_its_band(client):
    enable_score()
    _, job = _run(client, CHECK)
    analysis = job["analysis"]
    assert isinstance(analysis["percent"], int) and 0 <= analysis["percent"] <= 100
    bands = {"LOW": (0, 14), "MODERATE": (15, 31), "HIGH": (32, 100)}  # the band's own limits
    low, high = bands[analysis["band"]]
    assert low <= analysis["percent"] <= high


def test_redrafting_continues_from_the_checked_paper(fixed_client):
    checked_id, _ = _run(fixed_client, CHECK)
    draft = fixed_client.post(f"/api/jobs/{checked_id}/continue", headers=STUDENT, json={"origin": "original"})
    assert draft.status_code == 200, draft.json()
    new = draft.json()
    assert new["status"] == "DRAFT" and new["sourceJob"] == checked_id and new["source"]["wordCount"] > 0
    quote = fixed_client.post(f"/api/jobs/{new['id']}/quote", headers=STUDENT, json={"selection": {"writing": "REFINE", "formatting": "FORMAT", "preset": "apa7"}})
    assert quote.status_code == 200 and quote.json()["quote"]


def test_asking_for_changes_sends_the_students_words_to_the_writer(fixed_client):
    refined_id, refined = _run(fixed_client, {"writing": "REFINE", "academic": False})
    assert refined["status"] == "COMPLETED"
    blocks = fixed_client.get(f"/api/jobs/{refined_id}/document", headers=STUDENT).json()["blocks"]
    first = next(b["id"] for b in blocks if b["kind"] == "paragraph")
    draft = fixed_client.post(
        f"/api/jobs/{refined_id}/continue", headers=STUDENT, json={"origin": "result", "instruction": "Make this paragraph shorter and plainer.", "blocks": [first]}
    ).json()
    assert draft["selection"]["onlyBlocks"] == [first] and draft["fixNotes"]["*"] == ["The student asks: Make this paragraph shorter and plainer."]
    quote = fixed_client.post(f"/api/jobs/{draft['id']}/quote", headers=STUDENT, json={"selection": draft["selection"]}).json()["quote"]
    assert fixed_client.post(f"/api/jobs/{draft['id']}/submit", headers=STUDENT, json={"quoteId": quote["id"]}).status_code == 200
    assert wait(fixed_client, draft["id"], timeout=120)["status"] == "COMPLETED"
    assert any("Make this paragraph shorter and plainer." in r for r in fixed_client.models.requests if r.startswith("refine"))


def test_the_whole_finished_paper_can_be_formatted_next(fixed_client):
    refined_id, _ = _run(fixed_client, {"writing": "REFINE", "academic": False})
    draft = fixed_client.post(f"/api/jobs/{refined_id}/continue", headers=STUDENT, json={"origin": "result"}).json()
    formatted = fixed_client.post(f"/api/jobs/{draft['id']}/quote", headers=STUDENT, json={"selection": {"writing": "NONE", "formatting": "FORMAT", "preset": "harvard"}}).json()["quote"]
    assert fixed_client.post(f"/api/jobs/{draft['id']}/submit", headers=STUDENT, json={"quoteId": formatted["id"]}).status_code == 200
    job = wait(fixed_client, draft["id"], timeout=120)
    assert job["status"] == "COMPLETED" and any(o["id"] == "paper" for o in job["outputs"])


def test_changes_to_the_concept_paper_can_be_asked_for_directly(client):
    project_id = _with_chapter_one(client)
    from tests.test_proposals import _run as run_step

    assert run_step(client, project_id, "CONCEPT")["status"] == "COMPLETED"
    asked = client.post(f"/api/projects/{project_id}/chapters/4/request", headers=STUDENT, json={"instruction": "Shorten the background to half a page.", "sections": ["background"]})
    assert asked.status_code == 200, asked.json()
    comment = asked.json()["feedback"][-1]
    assert comment["by"] == "STUDENT" and comment["chapter"] == 4 and comment["sections"] == ["background"]
    quoted = client.post(f"/api/projects/{project_id}/steps", headers=STUDENT, json={"step": "REVISE_4", "comments": [comment["id"]]}).json()
    assert client.post(f"/api/projects/{project_id}/steps/{quoted['job']['id']}/submit", headers=STUDENT, json={"quoteId": quoted["quote"]["id"]}).status_code == 200
    job = wait(client, quoted["job"]["id"])
    assert job["status"] == "COMPLETED", job
    project = client.get(f"/api/projects/{project_id}", headers=STUDENT).json()
    assert next(c for c in project["chapters"] if c["number"] == 4)["current"] == 2
    assert project["feedback"][-1]["status"] == "APPLIED"
    report = client.get(f"/api/projects/{project_id}/feedback/report", headers=STUDENT)
    assert report.status_code == 400 or len(Document(io.BytesIO(report.content)).tables[0].rows) == 1  # own requests are not supervisor answers
