"""Institution profiles from an uploaded research guide: read by the lead, critiqued by the writer,
finalised by the lead, then validated by code into a rulebook the whole proposal follows."""

import io

import pytest
from docx import Document

from app.proposals import profile, rulebook
from tests.fake_models import profile_answer
from tests.test_api import STUDENT
from tests.test_proposals import _approved, _create, _run


def _guide(text: str = "research proposal") -> bytes:
    doc = Document()
    doc.add_heading(f"Kyambogo University Graduate School: guidelines for the {text}", level=1)
    for i in range(40):
        doc.add_paragraph(f"Section {i}: the {text} shall follow the structure set out here, with chapters, headings and references as described in this guide.")
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _answer():
    return profile_answer({"guide": "research proposal", "reference": profile.reference()})


def test_a_profile_is_validated_into_a_rulebook_with_gaps_filled_from_the_default():
    answer = _answer()
    answer["chapters"][0]["sections"].append(dict(answer["chapters"][0]["sections"][0]))  # a repeated key
    answer["citation"] = "OTHER"
    book = profile.build(answer, "guide.docx")
    assert book["institution"] == "Kyambogo University" and book["id"].startswith("custom-")
    keys = [s["key"] for s in book["chapters"][0]["sections"]]
    assert len(keys) == len(set(keys)) and "definitions" in keys
    assert abs(sum(c["share"] for c in book["chapters"][:3]) - 1) < 0.01
    assert abs(sum(s["share"] for s in book["chapters"][1]["sections"]) - 1) < 0.01
    assert book["levels"]["MASTERS"]["pages"] == [20, 40] and book["levels"]["PHD"] == rulebook.load(rulebook.DEFAULT)["levels"]["PHD"]
    assert book["formatting"]["font"] == "Times New Roman" and book["objectives"]["min"] == 3
    assert book["chapters"][3]["kind"] == "CONCEPT"  # the concept paper keeps the default layout
    assert book["vetting"]["questions"]["3"][0]["question"] == "Is the sampling procedure justified?"
    assert book["vetting"]["questions"]["1"] == rulebook.load(rulebook.DEFAULT)["vetting"]["questions"]["1"]  # none in the guide
    assert any("citation style" in u for u in book["unclear"]) and book["default_citation"] == "APA7"


def test_a_text_that_is_not_a_guide_is_refused():
    with pytest.raises(profile.NotAGuide):
        profile.build({**_answer(), "chapters": []}, "notes.docx")


def test_the_proposal_follows_the_students_institution(client):
    project = _create(client)
    uploaded = client.post(f"/api/projects/{project['id']}/guide", headers=STUDENT, files={"file": ("KyU guide.docx", _guide(), "application/octet-stream")})
    assert uploaded.status_code == 200 and uploaded.json()["guideName"] == "KyU guide.docx"
    quoted = client.post(f"/api/projects/{project['id']}/steps", headers=STUDENT, json={"step": "PROFILE"}).json()
    assert quoted["quote"]["lines"][0]["label"].startswith("Your institution's guide")
    job = _run(client, project["id"], "PROFILE")
    assert job["status"] == "COMPLETED", job
    assert client.models.tasks[-6:] == ["p_profile", "p_profile_critique", "p_profile_guide", "p_profile_finalise", "p_profile_review", "p_profile_review_peer"]
    project = client.get(f"/api/projects/{project['id']}", headers=STUDENT).json()
    assert project["rulebook"].startswith("custom-") and project["institution"] == "Kyambogo University" and project["citation"] == "APA7"
    assert "The guide does not say how long the literature review should be." in project["institutionNotes"] and project["guideRead"]

    _run(client, project["id"], "PLAN")
    _approved(client, project["id"])  # Chapter One follows the new structure
    chapter = client.get(f"/api/projects/{project['id']}/chapters/1", headers=STUDENT).json()
    assert chapter["title"] == "Introduction" and any(s["heading"] == "Definition of Key Terms" for s in chapter["sections"])
    doc = Document(io.BytesIO(client.get(f"/api/projects/{project['id']}/export", headers=STUDENT).content))
    assert any("OF KYAMBOGO UNIVERSITY" in p.text for p in doc.paragraphs) and doc.styles["Normal"].font.name == "Times New Roman"

    refused = client.post(f"/api/projects/{project['id']}/steps", headers=STUDENT, json={"step": "PROFILE"})
    assert refused.status_code == 400 and refused.json()["code"] == "CHAPTERS_WRITTEN"

    from app.runtime import get_runtime

    stored = rulebook.stored_path(project["rulebook"])
    assert get_runtime().files.exists(stored)
    assert client.delete(f"/api/projects/{project['id']}", headers=STUDENT).status_code == 204
    assert not get_runtime().files.exists(stored)  # the profile goes with the project


def test_a_guide_without_a_proposal_structure_fails_without_charge(client):
    project = _create(client)
    client.post(f"/api/projects/{project['id']}/guide", headers=STUDENT, files={"file": ("notes.docx", _guide("lecture notes"), "application/octet-stream")})
    job = _run(client, project["id"], "PROFILE")
    assert job["status"] == "FAILED" and job["failure"]["code"] == "NOT_A_GUIDE" and job["paymentStatus"] != "PAID"
    assert client.get(f"/api/projects/{project['id']}", headers=STUDENT).json()["rulebook"] == rulebook.DEFAULT


def test_a_profile_needs_a_guide_first(client):
    project = _create(client)
    refused = client.post(f"/api/projects/{project['id']}/steps", headers=STUDENT, json={"step": "PROFILE"})
    assert refused.status_code == 400 and refused.json()["code"] == "NO_GUIDE"
