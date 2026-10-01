"""Figures the student gave keep counting as theirs whatever characters surround them, and the
document's own section numbers are not statistics (live proposal prj_18519f00596d, 2026-10-01: every
sentence about "children aged 6–24 months" was refused because the escaped plan text hid the 24, and
"Section 1.9" was read as the figure 1.9, so Chapter One never finished)."""

import json

from app.proposals import evidence
from tests.fake_models import PLAN
from tests.test_api import STUDENT
from tests.test_proposals import _approved, _create, _run

AGED = "children aged 6–24 months"


def test_a_figure_after_a_dash_or_symbol_in_the_students_text_is_theirs():
    allowed = json.dumps({"population": f"{AGED}; adults ≥18 years; women 15–49"}, ensure_ascii=False)
    for sentence in (f"Objective 1: to estimate uptake among {AGED}.", "Women aged 15–49 and adults ≥18 years will be included."):
        assert evidence.figure_problems(sentence, {}, allowed) == [], sentence
    assert evidence.figure_problems("Coverage was 87.3% in Lira.", {}, allowed)  # an invented statistic is still refused


def test_section_table_and_figure_numbers_are_references_not_statistics():
    for sentence in ("The framework is presented in Section 1.9.", "See Sections 2.1 and 2.4, Table 3.2 and Figure 1.1.", "Chapter 3 describes the methods."):
        assert evidence.figure_problems(sentence, {}, "") == [], sentence


def test_a_withheld_numbered_objective_leaves_no_bare_number_behind():
    assert evidence.strip_unsupported("1. To report coverage of 87.3% in Lira.", {}, set(), "") == ""


def test_chapter_one_about_children_aged_6_24_months_is_written_and_kept(client):
    """The live failure, end to end: the plan and the chapter both speak of children aged 6–24
    months and cross-reference Section 1.9; the chapter completes with those sentences intact."""
    plan = {**PLAN, "title": f"Factors associated with malaria vaccine uptake among {AGED} in Lira District",
            "population": f"Caregivers of {AGED}", "specificObjectives": [f"To estimate the proportion of {AGED} who will have received age-appropriate doses", *PLAN["specificObjectives"][1:]]}
    client.models.overrides["p_finalise"] = lambda payload: plan if "title" in payload["draft"] else payload["draft"]  # the plan, not Chapter One's briefs
    from tests.fake_models import FakeModels

    def draft(payload):
        answer = FakeModels.default("p_draft", payload)
        for s in answer["sections"]:
            s["paragraphs"] = [f"The study will estimate uptake among {AGED} in Lira District.", *s["paragraphs"], "The conceptual framework is presented in Section 1.9."]
        return answer

    client.models.overrides["p_draft"] = draft
    project = _create(client)
    assert _run(client, project["id"], "PLAN")["status"] == "COMPLETED"
    project = _approved(client, project["id"], sampleSize={**PLAN["sampleSize"], "populationSource": "DHO records"})
    chapter = next(c for c in client.get(f"/api/projects/{project['id']}", headers=STUDENT).json()["chapters"] if c["number"] == 1)
    assert chapter["current"] == 1, chapter
    document = client.get(f"/api/projects/{project['id']}/chapters/1", headers=STUDENT).json()
    text = json.dumps(document, ensure_ascii=False)
    assert f"estimate uptake among {AGED} in Lira District" in text and "presented in Section 1.9" in text  # kept, not withheld
    assert "could not trace" not in text


def test_the_students_own_text_is_searched_as_written():
    """The builders of "what the student gave" keep every character, in proposals and in works."""
    from types import SimpleNamespace

    from app.proposals import pipeline

    def dumpable(data):
        return SimpleNamespace(model_dump=lambda by_alias=True: data)

    inp = SimpleNamespace(inputs=dumpable({"population": f"Caregivers of {AGED}"}), plan=dumpable({"title": f"Uptake among {AGED}"}))
    allowed = pipeline._allowed_text(inp)
    assert AGED in allowed and evidence.figure_problems(f"Uptake among {AGED} will be measured.", {}, allowed) == []


def test_a_works_students_own_figures_are_searched_as_written(monkeypatch):
    from types import SimpleNamespace

    from app.works import pipeline as works_pipeline

    monkeypatch.setattr(works_pipeline, "_student", lambda inp: {"description": f"A study of {AGED}; adults ≥18 years"})
    monkeypatch.setattr(works_pipeline, "_spec", lambda inp: SimpleNamespace(requirements=[], duration_months=None))
    allowed = works_pipeline._allowed_text(SimpleNamespace())
    assert evidence.figure_problems(f"Uptake among {AGED} and adults ≥18 years will be compared.", {}, allowed) == []
