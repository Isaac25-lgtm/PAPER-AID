"""Claims, statistics and the proposal's front pages (the academic audit of 10 October 2026, as agreed with the owner
on the 11th). Each test is a defect the audit found in a delivered trial document."""

import io
import zipfile

import pytest
from docx import Document

from app.proposals import evidence
from app.proposals import pipeline as proposals
from app.proposals.models import EvidenceItem, EvidenceSource
from app.works import pipeline as works
from tests.test_api import STUDENT
from tests.test_proposal_v2 import _with_chapter_one


def test_a_claim_that_nothing_has_been_studied_is_sent_back():
    """A proposal said factors in Mukono "remain uninvestigated" and baseline evidence "remains completely lacking"
    while a registered study and a dissertation on the topic existed."""
    for claim in ("The factors driving completion in Mukono District remain uninvestigated.",
                  "Baseline evidence on dose completion remains completely lacking.",
                  "No study has examined caregivers in Mukono since the vaccine was introduced.",
                  "This relationship has never been studied in Uganda.",
                  "There is no empirical evidence on this outcome in Uganda.",
                  "There is no published research available on this population."):
        problems = evidence.gap_problems(claim)
        assert len(problems) == 1 and "never that no study exists" in problems[0], claim
    for sound in ("Published evidence on dose completion in Mukono District is limited.",
                  "The studies found did not examine caregivers in Mukono District.",
                  "No significant difference was reported between the two groups.",
                  "The study will examine factors that have not yet received much attention.",
                  "Data on stock-outs were completely recorded at each facility.",
                  # Not claims about research: the check names research or evidence itself.
                  "In many rural schools electricity is completely lacking.",
                  "Undocumented migrants were excluded from the sampling frame.",
                  "There is no research department in the organisation.",
                  "The role of fathers remains largely unstudied in the work found.",  # hedged: a limit, not an absolute
                  # Codex's audit of 1a3b1e7, finding 5: saying a fact is not known is honest, and is never a claim about research
                  "The eligible population remains unknown.",
                  "The district disease burden remains undocumented.",
                  "Data on the eligible population are entirely missing from the district register.",
                  "No data exist on how many facilities offer the service.",
                  "Whether the service is available in every sub-county is unknown.",
                  "There is no evidence that the vaccine causes harm.",
                  # the claim is reported or denied, not made
                  "Earlier reviews claimed that no study has examined caregivers, which later work showed to be wrong.",
                  "One author wrote that “no study has examined this question”, a claim this review does not accept."):
        assert evidence.gap_problems(sound) == [], sound
    kept = "The eligible population remains unknown. The district disease burden remains undocumented."
    assert evidence.strip_overclaims(kept) is kept


def test_a_sentence_still_overclaiming_after_repair_is_withheld_before_the_final_review():
    """The repair rounds are given both checks' findings. What they leave is removed as an untraceable figure is, so
    a pattern never fails a whole chapter and never reaches the student."""
    paragraph = ("Uptake of the vaccine varies between districts. No study has examined caregivers in Mukono District. "
                 "Education showed a significant association with uptake (OR = 1.27; 95% CI: 0.56–2.89; p = 0.043). The study will address these questions.")
    assert evidence.strip_overclaims(paragraph) == "Uptake of the vaccine varies between districts. The study will address these questions."
    assert evidence.strip_overclaims(paragraph, gaps=False) == ("Uptake of the vaccine varies between districts. No study has examined caregivers in Mukono District. "
                                                               "The study will address these questions.")  # coursework: the statistic only
    sound = "Published evidence is limited.  The interval reported (0.56–2.89) includes 1."
    assert evidence.strip_overclaims(sound) is sound  # nothing removed: the approved spacing is untouched
    for denied in ("The result was not statistically significant (OR = 1.27; 95% CI: 0.56–2.89; p = 0.043).",
                   "The result did not reach statistical significance (OR = 1.27; 95% CI: 0.56–2.89; p = 0.043).",
                   "There was no significant association (OR = 1.27; 95% CI: 0.56–2.89; p = 0.043)."):
        assert evidence.statistic_problems(denied) == [], denied


def test_a_ratio_whose_interval_includes_one_is_not_called_significant():
    """ "OR = 1.27; 95% CI: 0.56–2.89; p = 0.043", called a significant association. The figures were the
    publisher's own, so code corrects none of them: it stops the word "significant". """
    copied = "Caregivers with secondary education showed a significant association with uptake (OR = 1.27; 95% CI: 0.56–2.89; p = 0.043)."
    problems = evidence.statistic_problems(copied)
    assert len(problems) == 1 and "0.56–2.89" in problems[0] and "Do not call this result significant" in problems[0]
    for sound in ("The study reported OR = 1.27 (95% CI: 0.56–2.89; p = 0.043), an interval that includes 1.",  # told as reported
                  "The association was not significant (OR = 1.27; 95% CI: 0.56–2.89; p = 0.043).",
                  "Uptake was significantly higher among urban caregivers (OR = 2.10; 95% CI: 1.30–3.40; p = 0.002).",  # the two agree
                  "The odds ratio was 1.27 with a 95% confidence interval of 0.56 to 2.89 and p = 0.43, which is not significant.",
                  "The result was significant at the five per cent level."):
        assert evidence.statistic_problems(sound) == [], sound
    for worded in ("A significant effect was found, with an odds ratio of 1.27, 95% confidence interval 0.56 to 2.89, p < 0.05.",
                   "Education was a significant predictor: the odds ratio was 1.27 with a 95% confidence interval of 0.56 to 2.89 (p = 0.043)."):
        assert len(evidence.statistic_problems(worded)) == 1, worded


def test_the_writers_are_told_beforehand_what_code_will_check():
    """A rule the writer first hears of in a repair round costs a round. New work is written and repaired on prompts
    that carry them; work priced before keeps the prompts it was priced with."""
    from pathlib import Path

    from app.ai.orchestration import STEPS

    folder = Path(__file__).parents[1] / "app" / "ai" / "prompts"
    for step in ("p_draft", "p_fix", "w_draft", "w_repair"):
        prompt = (folder / f"{STEPS[step].prompt}.md").read_text(encoding="utf-8")
        assert '"caution"' in prompt and "that no study exists" in prompt and "value of no difference (1 for" in prompt, step
        assert "interval includes 1 is never" not in prompt and "when its reported interval includes 1" not in prompt, step  # a difference's value of no difference is 0
    plan = (folder / f"{STEPS['p_plan'].prompt}.md").read_text(encoding="utf-8")
    assert "relationships and associations" in plan and "never list one variable in two roles" in plan
    # Codex's audit of 1a3b1e7, finding 8: what a study can show is not decided by what its design is called
    assert "a cohort included, examine relationships and associations" in plan and "stays descriptive" in plan and "tell the student which word changed" in plan
    for step in ("p_draft", "p_fix"):
        prompt = (folder / f"{STEPS[step].prompt}.md").read_text(encoding="utf-8")
        assert "longitudinal findings" not in prompt and "identify a cause" in prompt, step
    assert "command word asks for and no more" in (folder / f"{STEPS['w_draft'].prompt}.md").read_text(encoding="utf-8")


def test_a_question_that_asks_to_describe_is_planned_and_researched_as_one():
    """ "What are input devices? Describe five examples and explain what each is used for" was answered with a
    microphone's readout circuit and touchscreens in aircraft cockpits (round of 11 October): the research topics and
    the plan set an answer's depth, so both are told, on every path."""
    from pathlib import Path

    from app.ai.orchestration import STEPS, WORKFLOW_PROMPTS
    from app.proposals.ai import NEEDS_SCHEMA, NEEDS_SCHEMA_V2, needs_schema

    folder = Path(__file__).parents[1] / "app" / "ai" / "prompts"
    for prompt in (STEPS["w_needs"].prompt, WORKFLOW_PROMPTS[2]["w_needs"]):
        assert "never for specialist research on one narrow device" in (folder / f"{prompt}.md").read_text(encoding="utf-8"), prompt
    assert needs_schema(STEPS["w_needs"].prompt) == NEEDS_SCHEMA and needs_schema(WORKFLOW_PROMPTS[2]["w_needs"]) == NEEDS_SCHEMA_V2  # each keeps its path's answer format
    plan = (folder / f"{STEPS['w_plan'].prompt}.md").read_text(encoding="utf-8")
    assert "at the depth its command words and the student's level ask for, and no deeper" in plan and "plan a direct answer" in plan


def _item(**details) -> EvidenceItem:
    return EvidenceItem(**{"id": "E0a1b2c", "chapter": 1, "need": "n", "statement": "Moodle is used by 98.7% of institutions.",
                           "passage": "98.7% of the universities sampled in Kampala used Moodle", "scope": "Kampala institutions sampled, 2021", "access": "FULL_TEXT",
                           "verified": True, "support": "PARTLY_SUPPORTED", "source": EvidenceSource(url="https://example.org/a", title="E-learning in Kampala", year="2021"),
                           "retrieved_on": "2026-10-11", **details})


def test_a_partly_supported_finding_reaches_the_writer_with_what_it_must_not_claim():
    """98.7% of a Kampala sample was written as "98.7% of accredited institutions" nationally. A partly supported
    finding stays usable, so its writer and reviewer are now told where the statement goes beyond its source."""
    caution = "The passage is about universities sampled in Kampala, not all accredited institutions in Uganda."
    for given in (proposals._for_model([_item(caution=caution)], passages=True)[0], works._for_model([_item(caution=caution)], passages=True)[0]):
        assert given["caution"].startswith("Only partly supported: The passage is about universities sampled in Kampala") and "people, place and period" in given["caution"]
        assert given["scope"] == "Kampala institutions sampled, 2021" and given["sourceWords"].startswith("98.7% of the universities sampled in Kampala")
    assert "caution" not in proposals._for_model([_item(support="SUPPORTED")], passages=True)[0]  # a supported finding, and evidence saved before, are given as before


def test_the_support_check_s_reservation_is_kept_with_the_finding(client):
    seen = {}
    client.models.overrides["verify"] = lambda payload: {"results": [{"id": c["id"], "support": "PARTLY_SUPPORTED", "note": "The source covers  rural caregivers in one district only."}
                                                                     for c in payload["claims"]]}

    def draft(payload):
        from tests.fake_models import FakeModels

        seen.setdefault("evidence", [e for s in payload["sections"] for e in s["evidence"]])
        return FakeModels.proposal("p_draft", payload)

    client.models.overrides["p_draft"] = draft
    project_id = _with_chapter_one(client)
    library = client.get(f"/api/projects/{project_id}/evidence", headers=STUDENT).json()
    assert library and all(i["caution"] == "The source covers rural caregivers in one district only." for i in library if i["support"] == "PARTLY_SUPPORTED")
    assert seen["evidence"] and all("one district only" in e["caution"] for e in seen["evidence"])


def test_the_contents_page_lists_the_document_s_headings_and_never_an_instruction(client):
    """Every proposal printed "Word fills in this table when the document is opened (or right-click it and choose
    Update Field)" where its contents should be."""
    project_id = _with_chapter_one(client)
    exported = client.get(f"/api/projects/{project_id}/export", headers=STUDENT)
    assert exported.status_code == 200
    xml = zipfile.ZipFile(io.BytesIO(exported.content)).read("word/document.xml").decode("utf-8")
    assert "Word fills in this table" not in xml and "Update Field" not in xml
    assert ' TOC \\o "1-3"' in xml and 'w:dirty="true"' in xml  # still a real contents field, which Word fills with page numbers
    paragraphs = [p.text for p in Document(io.BytesIO(exported.content)).paragraphs]
    contents = paragraphs[paragraphs.index("Table of Contents") + 1]
    # its own headings until then, read from the finished document: every numbered section, the statements placed
    # under Objectives, and the references (Codex's audit of 1a3b1e7: the list given to it had left those out)
    assert "CHAPTER ONE\nGENERAL INTRODUCTION\n    1.0 Introduction\n    1.1 Background to the Study\n    1.2 Statement of the Problem\n" in contents
    assert "\n        1.3.1 General Objective\n        1.3.2 Specific Objectives\n" in contents and contents.endswith("\nREFERENCES")
    headings = [p.text.strip() for p in Document(io.BytesIO(exported.content)).paragraphs if p.style.name in ("Heading 1", "Heading 2", "Heading 3") and p.text.strip() != "Table of Contents"]
    assert [line.strip() for line in contents.split("\n")] == headings


def test_the_declaration_and_approval_pages_say_they_are_forms_still_to_sign(client):
    project_id = _with_chapter_one(client)
    paragraphs = [p.text for p in Document(io.BytesIO(client.get(f"/api/projects/{project_id}/export", headers=STUDENT).content)).paragraphs]
    declaration, approval = paragraphs.index("Declaration"), paragraphs.index("Approval")
    assert paragraphs[declaration + 1] == "(A form for you to read, complete and sign before you submit. It is not yet signed.)"
    assert paragraphs[approval + 1] == "(A form for your supervisor to sign once they have approved the proposal. It is not yet signed.)"
    assert any(p.startswith("Signature: ____") for p in paragraphs[declaration:approval])


# --- Codex's audit of 1a3b1e7 ------------------------------------------------------------------------------------

RATIO = "OR = 1.27; {level} CI: 0.56–2.89; p = 0.043"


def test_the_statistics_check_judges_only_what_cannot_be_true():
    """Finding 2: a 99% interval that includes 1 at p = 0.02 can be right; the level was never read."""
    said = "Education showed a significant association with uptake ({})."
    assert len(evidence.statistic_problems(said.format(RATIO.format(level="95%")))) == 1
    assert len(evidence.statistic_problems(said.format(RATIO.format(level="90%")))) == 1  # narrower still: it cannot include 1 at p below 0.05
    for level in ("99%", "99.9%", ""):  # can agree, or the level is not stated: left to the reviewer
        assert evidence.statistic_problems(said.format(RATIO.format(level=level).replace("  ", " "))) == [], level
    assert evidence.statistic_problems("Education showed a significant association (OR = 1.27; 99% CI: 0.56–2.89; p = 0.02).") == []
    # a difference or a coefficient: the value of no difference is 0, so an interval that includes 1 says nothing
    for other in ("The mean difference was significant (difference = 1.4; 95% CI: 0.6–2.2; p = 0.001).",
                  "Income was a significant predictor (β = 0.9; 95% CI: 0.2–1.6; p = 0.012)."):
        assert evidence.statistic_problems(other) == [], other


def test_the_word_significant_must_belong_to_the_result_it_is_judged_against():
    """Finding 2: a sentence with a significant age result and "education was not significant" was deleted."""
    mixed = ("Caregiver age was significantly associated with uptake (OR = 2.10; 95% CI: 1.30–3.40; p = 0.002), whereas education was not significant "
             "(OR = 1.27; 95% CI: 0.56–2.89; p = 0.043).")
    assert evidence.statistic_problems(mixed) == [] and evidence.strip_overclaims(mixed) is mixed
    reversed_order = "Education was not associated with uptake (OR = 1.27; 95% CI: 0.56–2.89; p = 0.043), while age was significant (OR = 2.10; 95% CI: 1.30–3.40; p = 0.002)."
    assert evidence.statistic_problems(reversed_order) == []
    wrong = "Age was significant (OR = 2.10; 95% CI: 1.30–3.40; p = 0.002) and education was significant too (OR = 1.27; 95% CI: 0.56–2.89; p = 0.043)."
    assert len(evidence.statistic_problems(wrong)) == 1
    after = "For education the estimate was OR = 1.27 (95% CI: 0.56–2.89; p = 0.043), which the authors describe as statistically significant."
    assert len(evidence.statistic_problems(after)) == 1


def test_a_table_is_read_as_prose_is_and_a_row_with_its_headings():
    """Finding 6: the same sentence passed unchanged in a caption or a cell, and a statistic spread across columns
    was never read as one."""
    sentence = "Education showed a significant association with uptake (OR = 1.27; 95% CI: 0.56–2.89; p = 0.043)."
    header = ["Factor", "OR", "95% CI", "p-value", "Interpretation"]
    wrong = ["Education", "1.27", "0.56–2.89", "0.043", "Significant"]
    sound = ["Age", "2.10", "1.30–3.40", "0.002", "Significant"]
    denied = ["Income", "1.27", "0.56–2.89", "0.043", "Not significant"]
    assert evidence.row_text(header, wrong) == "Factor = Education; OR = 1.27; 95% CI = 0.56–2.89; p-value = 0.043; Interpretation = Significant"
    assert evidence.row_overclaims(header, wrong) == [4] and evidence.row_overclaims(header, sound) == [] and evidence.row_overclaims(header, denied) == []
    assert len(evidence.table_problems([header, wrong, sound, denied])) == 1 and "Education" in evidence.table_problems([header, wrong, sound, denied])[0]
    assert evidence.strip_table_overclaims([header, wrong, sound, denied]) == [header, ["Education", "1.27", "0.56–2.89", "0.043", ""], sound, denied]
    untouched = [header, sound, denied]
    assert evidence.strip_table_overclaims(untouched) is untouched

    # the proposal's checks and its last line of defence
    from app.proposals.ai import SectionText, Table
    from app.proposals.models import StepInput
    from app.proposals.pipeline import _checks, _strip_table

    inp = StepInput.model_construct(chapter=2, plan=None)
    figures = "1.27 95% 0.56 2.89 0.043 2.10 1.30 3.40 0.002"  # the table's own numbers are traced: only the claim is at issue
    for table in (Table(caption=sentence, rows=[]), Table(caption="Factors", rows=[["Finding"], [sentence]]), Table(caption="Factors", rows=[header, wrong, sound])):
        text = SectionText(key="empirical", paragraphs=["The studies found are summarised below."], table=table)
        found = _checks(inp, "empirical", text, {}, figures)
        assert len(found) == 1 and found[0].startswith("In the table: ") and "do not agree" in found[0], (table, found)
        cleaned = _strip_table(inp, text, {}, set(), figures)
        assert cleaned != table and "ignificant association" not in cleaned.caption and all("ignificant" not in c or r == sound for r in cleaned.rows[1:] for c in r)
    gap = SectionText(key="empirical", paragraphs=["A summary follows."], table=Table(caption="No study has examined caregivers in Mukono District.", rows=[]))
    assert len(_checks(inp, "empirical", gap, {}, "")) == 1 and _strip_table(inp, gap, {}, set(), "").caption == ""


def test_coursework_tables_get_the_same_reading(client):
    from app.proposals.ai import SectionText as WorkText
    from app.proposals.ai import Table as WorkTable
    from app.works import pipeline as works_pipeline
    from app.works.models import PlanSection

    header = ["Factor", "OR", "95% CI", "p-value", "Interpretation"]
    wrong = ["Education", "1.27", "0.56–2.89", "0.043", "Significant"]
    sentence = "Education showed a significant association with uptake (OR = 1.27; 95% CI: 0.56–2.89; p = 0.043)."
    assert evidence.table_problems([header, wrong]) and evidence.statistic_problems(sentence)
    section = PlanSection.model_construct(key="theme1", heading="Evidence", brief="", words=300, min_words=0, max_words=0, field_id="", coverage=[], criteria=[])
    for table in (WorkTable(caption=sentence, rows=[header, ["Age", "2.10", "1.30–3.40", "0.002", "Significant"]]), WorkTable(caption="Factors", rows=[header, wrong])):
        text = WorkText(key="theme1", paragraphs=["The studies are summarised in the table."], table=table)
        assert any("do not agree" in p for p in works_pipeline._checks(_work_input(), section, text, {}, "", {})), table


def _work_input():
    from app.works.models import ResolvedSpec, WorkStepInput

    spec = ResolvedSpec.model_construct(kind="COURSEWORK", variant="ESSAY", mode="", level="LATER_UG", source_policy="OPEN", fields=[], citation_style="APA7", directives=[], coverage=[],
                                        active_rules=[], flags={}, limits=[], requirements=[], target_words=1500)
    return WorkStepInput.model_construct(spec=spec, plan=None, inputs=None, results=None, budget=None, kind="COURSEWORK")


@pytest.fixture
def works_client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKS_ENABLED", '["CONCEPT_NOTE","COURSEWORK","FUNDING_PROPOSAL"]')
    from tests.conftest import _client

    yield from _client(tmp_path, monkeypatch, "cost")


def test_the_coursework_evaluator_reads_each_section_beside_the_evidence_it_cites(works_client):
    """Finding 3: the caution reached the writer and the repair, and no reviewer. The request the evaluator is
    actually sent is read here, not the helper that builds an evidence entry."""
    from tests.test_works import _coursework, _run, _work

    client = works_client
    reservation = "The passage is about universities sampled in Kampala, not Uganda nationally."
    client.models.overrides["w_verify"] = lambda payload: {"results": [{"id": c["id"], "support": "PARTLY_SUPPORTED", "note": reservation} for c in payload["claims"]]}
    asked: list[dict] = []

    def evaluate(payload):
        asked.append(payload)
        return client.models.default("w_evaluate", payload)

    client.models.overrides["w_evaluate"] = evaluate
    work = _coursework(client)
    _run(client, work["id"], "PLAN")
    work = _work(client, work["id"])
    client.post(f"/api/works/{work['id']}/plan/approve", headers=STUDENT, json={"baseVersion": work["planVersion"]})
    _, job = _run(client, work["id"], "DRAFT")
    assert job["status"] == "COMPLETED", job.get("failure")
    sections = [s for payload in asked for s in payload["sections"]]
    citing = [s for s in sections if "⟦E" in " ".join(s["text"])]
    assert citing and all(s["evidence"] for s in citing)
    for section in citing:
        cited = set(evidence.cited_ids(" ".join(section["text"])))
        assert {e["id"] for e in section["evidence"]} == cited  # what it cites, and nothing else
        assert all(reservation in e["caution"] and e["sourceWords"] and "scope" in e for e in section["evidence"])
    assert all("evidence" in s for s in sections)  # a section that cites nothing is told so with an empty list


def test_page_numbers_carry_on_into_the_references(client):
    """Found when Word filled the contents page of a trial proposal (2026-10-11): "REFERENCES ... 1". A new section
    starts as a copy of the one before, its restart at page 1 included."""
    import re

    project_id = _with_chapter_one(client)
    exported = client.get(f"/api/projects/{project_id}/export", headers=STUDENT)
    xml = zipfile.ZipFile(io.BytesIO(exported.content)).read("word/document.xml").decode("utf-8")
    assert "REFERENCES" in xml
    numbering = re.findall(r"<w:pgNumType[^>]*>", xml)
    assert len(numbering) == 3 and ['w:start="1"' in n for n in numbering] == [True, True, False]  # the preliminary pages, the first chapter, then on
    assert 'w:fmt="lowerRoman"' in numbering[0] and all('w:fmt="decimal"' in n for n in numbering[1:])
