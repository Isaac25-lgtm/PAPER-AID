"""The standard guide v2 (2026-10-08), checked against the UCU handbook's own wording: the general (main)
objective is stated under Objectives of the Study (§5.3.3), with a primary research question (vetting form,
p. 51), hypotheses as null and alternative (§5.3.4), the concept paper's three to five (§1.4); and the owner's
rule: Bachelor's, PGD and Master's take three specific objectives, four only when the student asks."""

import io

import pytest
from docx import Document

from app.proposals import rulebook
from app.proposals.models import ProposalPlan
from app.proposals.pipeline import plan_statements
from tests.fake_models import PLAN
from tests.test_api import STUDENT
from tests.test_proposals import DETAILS, _approved, _create, _run

V1, V2 = "ucu-2018-v1", "ucu-2018-v2"


def _plan(**changes) -> ProposalPlan:
    return ProposalPlan.model_validate({**PLAN, **changes})


@pytest.mark.parametrize(("level", "four", "concept", "expected"), [
    ("MASTERS", False, False, (2, 3)), ("MASTERS", True, False, (2, 4)), ("BACHELORS", False, False, (2, 3)), ("PGD", True, False, (2, 4)),
    ("PHD", False, False, (2, 5)), ("PHD", True, False, (2, 5)),
    ("MASTERS", False, True, (3, 3)), ("MASTERS", True, True, (3, 4)), ("PHD", False, True, (3, 5)),
])
def test_the_number_of_objectives_follows_the_owners_cap_inside_the_handbook(level, four, concept, expected):
    assert rulebook.objective_range(V2, level, four, concept) == expected
    assert rulebook.objective_range(V1, level, four) == (2, 5)  # proposals under way keep the handbook's general advice


def test_the_plan_rules_are_enforced_on_the_standard_guide_v2_only():
    four = _plan(specificObjectives=[*PLAN["specificObjectives"], "To explore the role of community leaders"],
                 researchQuestions=[*PLAN["researchQuestions"], "What role do community leaders play?"],
                 alignment=[*PLAN["alignment"], {**PLAN["alignment"][0], "objective": 4}])
    assert any("takes 2 to 3 specific objectives" in p for p in rulebook.plan_problems(V2, four, "MASTERS"))
    assert not rulebook.plan_problems(V2, four, "MASTERS", four=True)
    assert not rulebook.plan_problems(V2, four, "PHD")
    assert not rulebook.plan_problems(V1, four, "MASTERS")
    assert any("primary research question" in p for p in rulebook.plan_problems(V2, _plan(primaryQuestion=""), "MASTERS"))
    nulls = _plan(questionsKind="HYPOTHESES", researchQuestions=["There is no association between distance and uptake."] * 3)
    assert any("alternative" in p for p in rulebook.plan_problems(V2, nulls, "MASTERS"))
    paired = nulls.model_copy(update={"alternative_hypotheses": ["There is an association between distance and uptake."] * 3})
    assert not any("alternative" in p for p in rulebook.plan_problems(V2, paired, "MASTERS"))


@pytest.mark.parametrize(("question", "past"), [
    ("What factors influenced vaccine uptake in Mukono?", True), ("How did distance affect uptake?", True), ("Why were caregivers absent?", True),
    ("What factors are associated with vaccine uptake?", False), ("How will distance affect uptake?", False),
    ("What is the perceived risk of the vaccine among caregivers?", False), ("How does distance affect uptake?", False),
])
def test_research_questions_in_the_past_tense_are_noticed(question, past):
    assert rulebook.past_tense(question) is past


def test_the_statements_are_laid_out_as_the_handbook_asks():
    plan = _plan()
    objectives = plan_statements(plan, "objectives", "1.3")
    assert objectives[:3] == ["1.3.1 General Objective", PLAN["purpose"], "1.3.2 Specific Objectives"]
    assert objectives[3:] == [f"{n}. {o}" for n, o in zip(("i", "ii", "iii"), PLAN["specificObjectives"], strict=True)]
    questions = plan_statements(plan, "questions", "1.4")
    assert questions[:3] == ["1.4.1 Primary Research Question", PLAN["primaryQuestion"], "1.4.2 Specific Research Questions"]
    hypotheses = plan_statements(_plan(questionsKind="HYPOTHESES", researchQuestions=["No association (1)."],
                                       alternativeHypotheses=["An association (1)."]), "questions", "1.4")
    assert hypotheses[-3:] == ["1.4.2 Research Hypotheses", "H01: No association (1).", "HA1: An association (1)."]


def test_chapter_one_states_the_approved_objectives_word_for_word_whatever_the_writer_returns(client):
    project = _create(client)
    assert project["rulebook"] == V2
    _run(client, project["id"], "PLAN")

    def rewriting_writer(payload):  # the writer restates and rewords the objectives: code places the approved ones
        sections = []
        for s in payload["sections"]:
            text = ["This section sets out what the study aims to achieve."]
            if s["key"] in ("objectives", "questions"):
                text += ["i. To study something else entirely.", "The general objective is to establish the determinants of malaria vaccine uptake among caregivers."]
            else:
                text.append(f"{s['heading']} is discussed here for caregivers in Mukono District.")
            sections.append({"key": s["key"], "paragraphs": text, "table": {"caption": "", "rows": []}})
        return {"sections": sections}

    client.models.overrides["p_draft"] = rewriting_writer
    _approved(client, project["id"])  # Chapter One starts on approval
    chapter = client.get(f"/api/projects/{project['id']}/chapters/1", headers=STUDENT).json()
    keys = [s["key"] for s in chapter["sections"]]
    assert "purpose" not in keys and keys.index("objectives") < keys.index("questions") and keys[-1] == "conclusion"
    objectives = next(s for s in chapter["sections"] if s["key"] == "objectives")
    number = objectives["number"]
    assert objectives["paragraphs"] == ["This section sets out what the study aims to achieve.", f"{number}.1 General Objective", PLAN["purpose"],
                                        f"{number}.2 Specific Objectives", *[f"{n}. {o}" for n, o in zip(("i", "ii", "iii"), PLAN["specificObjectives"], strict=True)]]
    questions = next(s for s in chapter["sections"] if s["key"] == "questions")
    assert questions["paragraphs"][1:3] == [f"{questions['number']}.1 Primary Research Question", PLAN["primaryQuestion"]]
    checks = {i["id"]: i for i in chapter["readiness"]}
    assert checks["C1-STATED-OBJECTIVES"]["status"] == "PASS" and checks["C1-STATED-QUESTIONS"]["status"] == "PASS" and checks["C1-QUESTION-TENSE"]["status"] == "PASS"
    doc = Document(io.BytesIO(client.get(f"/api/projects/{project['id']}/export", headers=STUDENT).content))
    headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading 3")]
    assert f"{number}.1 General Objective" in headings and f"{number}.2 Specific Objectives" in headings


def test_four_objectives_reach_the_planner_only_when_the_student_asks(client):
    asked = client.post("/api/projects", headers=STUDENT, json={**DETAILS, "inputs": {**DETAILS["inputs"], "fourObjectives": True}}).json()
    _run(client, asked["id"], "PLAN")
    plain = _create(client)
    _run(client, plain["id"], "PLAN")
    counts = [r["objectiveCount"] for t, r in zip(client.models.tasks, client.models.requests, strict=True) if t == "p_plan" for r in [__import__("json").loads(r[len(t):])]]
    assert {"min": 2, "max": 4} in counts and {"min": 2, "max": 3} in counts


def test_a_complete_export_is_blocked_when_the_objectives_are_not_as_approved(client):
    from app.proposals import export, service
    from app.runtime import get_runtime

    project = _create(client)
    _run(client, project["id"], "PLAN")
    _approved(client, project["id"])
    rt = get_runtime()
    stored = rt.store.get_project(project["id"])
    doc = service._chapter_doc(rt, stored.chapter(1))
    assert not any("stated as approved" in b for b in export.final_blockers(stored, {1: doc}))
    next(i for i in doc.readiness if i.id == "C1-STATED-OBJECTIVES").status = "MISSING"  # the delivered objectives differ from the plan
    assert any("stated as approved" in b for b in export.final_blockers(stored, {1: doc}))


def test_the_code_checks_never_share_an_id_with_the_handbooks_vetting_questions():
    """The browser journey 2026-10-08: "C1-QUESTIONS" was both a vetting question and a code check, so the
    checklist repeated an entry."""
    for number in (1, 4):
        vetting = {q["id"] for q in rulebook.vetting(V2, number)}
        assert not vetting & {f"C{number}-STATED-OBJECTIVES", f"C{number}-STATED-QUESTIONS", f"C{number}-QUESTION-TENSE"}



@pytest.mark.parametrize(("paragraph", "lead"), [
    ("To address the knowledge gaps identified in the statement of the problem, this study establishes clear objectives.", True),
    ("To systematically examine the factors that govern uptake, specific research questions aligned with the objectives will guide the study.", True),
    ("The primary research question and the specific questions are presented below.", True),
    ("To determine the level of malaria vaccine uptake among caregivers in Mukono District.", False),
    ("To examine caregiver-related factors, including distance and cost, associated with uptake.", False),
    ("ii. To assess health facility factors.", False),
    ("H01: There is no association between distance and uptake.", False),
])
def test_an_introduction_opening_with_to_is_kept_and_an_objective_is_not(paragraph, lead):
    """The live runs 2026-10-08: the writer's introduction began "To address ..." or "To systematically examine ...",
    was taken for a restated objective and dropped, and the review then failed the section for its introduction."""
    from app.proposals.pipeline import _introduction
    assert _introduction(paragraph, ["what is the level of malaria vaccine up"]) is lead


def test_an_introduction_naming_the_primary_question_is_not_taken_for_a_statement():
    """The third live run 2026-10-08: "... this study will address one primary research question supported by three
    specific research questions ..." matched the sub-heading "Primary Research Question" and was dropped."""
    from app.proposals.pipeline import _introduction, stated_fragments
    stated = stated_fragments(_plan(), "1.4")
    intro = ("To operationalise the research problem and guide data collection, this study will address one primary research question "
             "supported by three specific research questions directly aligned with the specific objectives.")
    assert _introduction(intro, stated)
    assert not _introduction(PLAN["primaryQuestion"], stated) and not _introduction(PLAN["purpose"], stated)
    assert not _introduction(f"The study asks: {PLAN['researchQuestions'][0]}", stated)
