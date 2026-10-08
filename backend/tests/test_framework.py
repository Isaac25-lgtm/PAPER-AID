"""The conceptual framework reworked (owner decision 2026-10-08, Codex's recommendations): black and white by
default, every variable drawn, a concept framework for a qualitative study, the same figure and note in the
app, the Word file and its own download, and edits from the workspace."""

import io

from docx import Document

from app.proposals import framework
from app.proposals.models import ProposalPlan, Variables
from tests.fake_models import PLAN
from tests.test_api import STUDENT
from tests.test_proposals import _approved, _create, _run


def test_every_variable_is_drawn_however_many_there_are():
    """The figure used to keep 10 independent, 3 dependent and 6 intervening variables and drop the rest unsaid."""
    many = Variables(independent=[f"Factor {i}" for i in range(1, 15)], dependent=[f"Outcome {i}" for i in range(1, 5)],
                     intervening=[f"Condition {i}" for i in range(1, 9)])
    png = framework.draw(many)
    assert png is not None and png[:8] == b"\x89PNG\r\n\x1a\n"
    text = framework.describe(many)
    assert all(f"factor {i}" in text.lower() for i in range(1, 15)) and "condition 8" in text.lower()


def test_black_and_white_by_default_and_a_style_only_recolours():
    from PIL import Image

    v = Variables(**PLAN["variables"])
    mono, green = framework.draw(v), framework.draw(v, "GREEN")
    colours = {c for _, c in Image.open(io.BytesIO(mono)).convert("RGB").getcolors(1_000_000)}
    assert all(abs(r - g) < 12 and abs(g - b) < 12 for r, g, b in colours)  # greys only
    assert mono != green and Image.open(io.BytesIO(mono)).size == Image.open(io.BytesIO(green)).size


def test_a_qualitative_study_gets_a_concept_framework_not_variables():
    plan = ProposalPlan.model_validate({**PLAN, "studyType": "QUALITATIVE", "variables": {},
                                        "purpose": "To explore caregivers' experiences of the malaria vaccine",
                                        "specificObjectives": ["To explore caregivers' understanding of the vaccine", "To describe the barriers to completing the doses"]})
    assert framework.draw_kind(plan) == "CONCEPTS" and framework.figure(plan) is not None
    assert framework.describe_plan(plan).startswith("The study explores caregivers' experiences")
    assert "no cause or direction" in framework.note(plan)


def test_the_framework_is_edited_from_the_workspace(client):
    project = _create(client)
    _run(client, project["id"], "PLAN")
    _approved(client, project["id"])
    url = f"/api/projects/{project['id']}"
    project = client.get(url, headers=STUDENT).json()
    assert project["frameworkStyle"] == "MONO" and project["frameworkNote"].endswith("Source: Researcher's own conceptualisation.")
    version = project["planVersion"]
    styled = client.post(f"{url}/framework", headers=STUDENT, json={"baseVersion": version, "style": "BLUE"}).json()
    assert styled["frameworkStyle"] == "BLUE" and styled["planVersion"] == version  # a colour is not a change to the study
    variables = {**PLAN["variables"], "independent": [*PLAN["variables"]["independent"], "Household income"]}
    edited = client.post(f"{url}/framework", headers=STUDENT, json={"baseVersion": version, "variables": variables}).json()
    assert edited["planVersion"] == version + 1 and "Household income" in edited["plan"]["variables"]["independent"] and edited["planStatus"] == "APPROVED"
    assert "household income" in edited["framework"].lower()
    chapter_one = next(c for c in edited["chapters"] if c["number"] == 1)
    assert any("Conceptual Framework" in s for s in chapter_one["needsReview"])  # built on the variables: to review
    stale = client.post(f"{url}/framework", headers=STUDENT, json={"baseVersion": version, "variables": variables})
    assert stale.status_code == 409
    half = client.post(f"{url}/framework", headers=STUDENT, json={"baseVersion": version + 1, "variables": {**variables, "dependent": []}})
    assert half.status_code == 400 and half.json()["code"] == "FRAMEWORK_INCOMPLETE"
    word = Document(io.BytesIO(client.get(f"{url}/export", headers=STUDENT).content))
    assert any(p.text == "Note. " + edited["frameworkNote"] for p in word.paragraphs)  # the same note as the app
    assert client.get(f"{url}/framework.png", headers=STUDENT).content[:8] == b"\x89PNG\r\n\x1a\n"
