"""Works: the fixes from Codex's second audit of 2026-09-30 (ragged tables, revisions that change
nothing, verdicts on earlier wording, required headings, missing documents, form boxes with tables,
every hard-limit finding kept, warnings that do not hold a draft back)."""

import pytest

from app.rules.compliance import report
from app.rules.validators import VALIDATORS, Context
from app.works import templates
from app.works.models import FormField, Limit, PlanSection, WorkDocument, WorkInputs, WorkSection
from tests import fake_works
from tests.test_api import STUDENT
from tests.test_works import _coursework, _run, _work
from tests.test_works_golden import _spec


@pytest.fixture
def works_client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKS_ENABLED", '["CONCEPT_NOTE","COURSEWORK","FUNDING_PROPOSAL"]')
    from tests.conftest import _client

    yield from _client(tmp_path, monkeypatch, "cost")


def _drafted(client):
    work = _coursework(client)
    _run(client, work["id"], "PLAN")
    work = _work(client, work["id"])
    client.post(f"/api/works/{work['id']}/plan/approve", headers=STUDENT, json={"baseVersion": work["planVersion"]})
    return work


def test_a_writers_uneven_table_is_padded_and_the_word_file_is_built_before_completion(works_client):
    client = works_client

    def ragged(payload):
        drafted = fake_works.draft(payload)
        drafted["sections"][1]["table"] = {"caption": "Coverage by district", "rows": [["District", "Coverage"], ["Kamuli", "High", "Rising"], ["Iganga"]]}
        return drafted

    client.models.overrides["w_draft"] = ragged
    work = _drafted(client)
    _, job = _run(client, work["id"], "DRAFT")
    assert job["status"] == "COMPLETED", job.get("failure")
    doc = client.get(f"/api/works/{work['id']}/document", headers=STUDENT).json()
    table = next(s["table"] for s in doc["sections"] if s.get("table"))
    assert {len(row) for row in table} == {3} and table[2] == ["Iganga", "", ""]  # padded, nothing cut
    assert client.get(f"/api/works/{work['id']}/export", headers=STUDENT).status_code == 200


def test_a_revision_that_changes_nothing_fails_without_charge_and_leaves_the_request_open(works_client):
    from app.runtime import get_runtime

    client = works_client
    work = _drafted(client)
    _run(client, work["id"], "DRAFT")
    work = client.post(f"/api/works/{work['id']}/requests", headers=STUDENT, json={"instruction": "Say more about supervision.", "sections": ["conclusion"]}).json()
    client.models.overrides["w_repair"] = lambda payload: {"sections": []}  # the writer returns nothing
    _, job = _run(client, work["id"], "REVISE")
    assert job["status"] == "FAILED" and job["failure"]["code"] == "NOTHING_REVISED"
    assert get_runtime().store.get(job["id"]).billing.state == "RELEASED"
    work = _work(client, work["id"])
    assert work["current"] == 1 and work["requests"][0]["status"] == "OPEN"


def test_a_section_returned_unchanged_is_not_counted_as_revised(works_client):
    from app.runtime import get_runtime

    client = works_client
    work = _drafted(client)
    _run(client, work["id"], "DRAFT")
    client.post(f"/api/works/{work['id']}/requests", headers=STUDENT, json={"instruction": "Sharper opening.", "sections": ["introduction"]})
    client.post(f"/api/works/{work['id']}/requests", headers=STUDENT, json={"instruction": "Say more about supervision.", "sections": ["conclusion"]})

    def only_conclusion(payload):
        answer = fake_works.repair(payload)
        for s in answer["sections"]:
            if s["key"] == "introduction":
                s["paragraphs"] = next(x["text"] for x in payload["sections"] if x["key"] == "introduction")  # returned exactly as it was
        return answer

    client.models.overrides["w_repair"] = only_conclusion
    _, job = _run(client, work["id"], "REVISE")
    assert job["status"] == "COMPLETED" and job["outcome"] == "PARTIAL", job.get("failure")
    assert get_runtime().store.get(job["id"]).delivery["WORK_REVISE"] == 0.5
    status = {r["text"]: r["status"] for r in _work(client, work["id"])["requests"]}
    assert status == {"Sharper opening.": "OPEN", "Say more about supervision.": "APPLIED"}


def test_a_repaired_section_never_keeps_the_verdict_on_its_earlier_wording(works_client):
    """The first review fails one section; its repair is then never reviewed (the reviewers return
    nothing): it must be reported as not reviewed, not passed on the old verdict."""
    client = works_client
    evaluated = []

    def evaluate(payload):
        evaluated.append(1)
        if len(evaluated) > 1:
            return {"results": []}  # nothing comes back for the repaired text
        answer = fake_works.answer("w_evaluate", payload)
        answer["results"][0]["verdict"] = "REPAIR"
        answer["results"][0]["issues"] = [{"type": "clarity", "severity": "major", "instruction": "Tighten the opening."}]
        return answer

    client.models.overrides["w_evaluate"] = evaluate
    work = _drafted(client)
    _, job = _run(client, work["id"], "DRAFT")
    assert job["status"] == "COMPLETED", job.get("failure")
    doc = client.get(f"/api/works/{work['id']}/document", headers=STUDENT).json()
    reviewed = next(i for i in doc["readiness"] if i["id"] == "W-REVIEWED")
    assert reviewed["status"] == "NEEDS_REVIEW"


def test_a_required_heading_goes_to_the_section_about_it_not_one_sharing_a_generic_word():
    sections = [PlanSection(key="approach", heading="Approach and activities", words=300, brief="What the project will do"),
                PlanSection(key="budget", heading="Proposed budget", words=100, brief="The costs")]
    named = {s.key: s for s in templates._name_required(sections, ["Proposed intervention"], 400)}
    assert named["approach"].heading == "Proposed intervention" and named["budget"].heading == "Proposed budget"
    assert "Proposed intervention" in named["approach"].brief  # the content follows the heading


def test_a_document_that_cannot_be_read_is_never_marked_read(works_client):
    from app.runtime import get_runtime

    client = works_client
    work = client.post("/api/works", headers=STUDENT, json={"kind": "COURSEWORK", "variant": "ESSAY", "inputs": {"title": "CHWs", "description": "Discuss community health workers in rural Uganda and their effect on maternal health."}}).json()
    client.post(f"/api/works/{work['id']}/sources/text", headers=STUDENT, json={"role": "BRIEF", "name": "Brief", "text": "Essays must not exceed 1,500 words. Use APA 7."})
    work = client.post(f"/api/works/{work['id']}/sources/text", headers=STUDENT, json={"role": "RUBRIC", "name": "Rubric", "text": "Critical analysis 40%. Structure 20%."}).json()
    rt = get_runtime()
    rt.files.delete(rt.store.get_work(work["id"]).sources[1].path)
    _, job = _run(client, work["id"], "READ")
    assert job["status"] == "FAILED" and job["failure"]["code"] == "SOURCES_MISSING" and "Rubric" in job["failure"]["userMessage"]
    assert _work(client, work["id"])["needsRead"] and not get_runtime().store.get_work(work["id"]).read_sources


def test_a_form_box_counts_its_table_too():
    spec = _spec("CONCEPT_NOTE", "FUNDING_CONCEPT").model_copy(update={"fields": [FormField(id="f1", label="Summary", max_words=50)]})
    doc = WorkDocument(kind="CONCEPT_NOTE", variant="FUNDING_CONCEPT", title="t", spec_version=1, plan_version=1,
                       sections=[WorkSection(key="field_f1", heading="Summary", paragraphs=["word " * 40], field_id="f1", table=[["A", "B"], ["x " * 20, "y"]])])
    result = VALIDATORS["limits.field_count"](Context(spec=spec, stage="FINAL", inputs=WorkInputs(title="A work"), doc=doc), {"id": "CN-039"})
    assert result[0] == "FAIL"


def test_an_estimated_page_count_never_hides_a_word_limit_failure():
    spec = _spec("CONCEPT_NOTE", "FUNDING_CONCEPT").model_copy(update={"limits": [Limit(type="WORD", max=100), Limit(type="PAGE", max=2)]})
    doc = WorkDocument(kind="CONCEPT_NOTE", variant="FUNDING_CONCEPT", title="t", spec_version=1, plan_version=1,
                       sections=[WorkSection(key="summary", heading="Summary", paragraphs=["word " * 300])])
    status, note, _ = VALIDATORS["limits.hard_max"](Context(spec=spec, stage="FINAL", inputs=WorkInputs(title="A work"), doc=doc), {"id": "SH-004"})
    assert status == "FAIL" and "over the 100-word limit" in note and "pages" in note


def test_a_warning_is_shown_but_does_not_hold_the_draft_back(monkeypatch):
    from app.proposals import evidence as ev
    from app.rules import compliance

    monkeypatch.setattr(ev, "reference_list", lambda sources, style="APA7": ["ref " * 300])
    spec = _spec("COURSEWORK", "ESSAY", answers={"word_limit": "1000", "level": "LATER_UG"})
    doc = WorkDocument(kind="COURSEWORK", variant="ESSAY", title="t", spec_version=1, plan_version=1,
                       sections=[WorkSection(key="analysis", heading="Analysis", paragraphs=["word " * 950])])
    items = report(Context(spec=spec, stage="FINAL", inputs=WorkInputs(title="A work"), doc=doc), ("DRAFT", "FINAL"))
    limit = next(i for i in items if "1,250 with the references" in i.note)
    assert limit.status == "NEEDS_REVIEW" and limit.severity == "WARNING"
    assert compliance.overall([limit]) == "READY_WITH_WARNINGS"
