"""Works: the fixes from Codex's audit of 2026-09-30 (publication and settlement, checks on the exact
published text, plans that can be approved, partial revisions, limit scope, table cells, long
documents, search privacy, frozen content, quote values and the preview's tables)."""

import pytest

from app.jobs.models import Stage
from app.rules.extract import requirements_from, value_in_quote
from app.rules.validators import VALIDATORS, Context
from app.works import pipeline as works_pipeline
from app.works.models import Limit, SourceFile, WorkDocument, WorkInputs, WorkSection
from tests import fake_works
from tests.test_api import STUDENT
from tests.test_works import QUESTION, _coursework, _run, _work
from tests.test_works_golden import _spec


@pytest.fixture
def works_client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKS_ENABLED", '["CONCEPT_NOTE","COURSEWORK","FUNDING_PROPOSAL"]')
    from tests.conftest import _client

    yield from _client(tmp_path, monkeypatch, "cost")


def _approved(client, work):
    _run(client, work["id"], "PLAN")
    work = _work(client, work["id"])
    return client.post(f"/api/works/{work['id']}/plan/approve", headers=STUDENT, json={"baseVersion": work["planVersion"]}).json()


# --- #1: a published result is settled in the same transaction ------------------------------------


def test_an_error_after_publishing_never_refunds_the_published_result(works_client, monkeypatch):
    from app.runtime import get_runtime

    client = works_client
    work = _coursework(client)
    real = works_pipeline.STAGES[Stage.EXPORTING]

    def export_then_crash(ctx):
        real(ctx)
        raise RuntimeError("the worker was lost after the export committed")

    monkeypatch.setitem(works_pipeline.STAGES, Stage.EXPORTING, export_then_crash)
    _, job = _run(client, work["id"], "PLAN")
    stored = get_runtime().store.get(job["id"])
    assert job["status"] == "COMPLETED" and stored.billing.state == "SETTLED"
    assert job["id"] in get_runtime().store.get_work(work["id"]).published and _work(client, work["id"])["plan"]


def test_a_step_failed_meanwhile_is_never_published(works_client, monkeypatch):
    """What an older release does to a step it cannot run: fail it and refund it. A late export of the
    same step must not publish afterwards."""
    from app.jobs import state
    from app.jobs.models import JobFailure, JobStatus
    from app.pricing.billing import refund_job
    from app.runtime import get_runtime

    client = works_client
    work = _coursework(client)
    real = works_pipeline.STAGES[Stage.EXPORTING]

    def failed_elsewhere_first(ctx):
        def fail(j, w):
            j.failure = JobFailure(code="SERVICE_UNAVAILABLE", user_message="Not available.", retryable=False)
            state.transition(j, JobStatus.FAILED, "Failed elsewhere")
            refund_job(j, w, "Job failed, so nothing was charged")
            return j, w

        ctx.rt.store.update_job_and_wallet(ctx.job.id, fail)
        real(ctx)

    monkeypatch.setitem(works_pipeline.STAGES, Stage.EXPORTING, failed_elsewhere_first)
    _, job = _run(client, work["id"], "PLAN")
    stored = get_runtime().store.get_work(work["id"])
    assert job["status"] == "FAILED" and job["id"] not in stored.published and stored.plan is None


# --- #2: the exact published text is reviewed ------------------------------------------------------


def _long_draft(payload):
    drafted = fake_works.draft(payload)
    for s in drafted["sections"]:
        s["paragraphs"] = s["paragraphs"] * 2  # twice its planned length: compression must run
    return drafted


def test_text_compressed_after_the_whole_document_review_is_reviewed_again(works_client):
    client = works_client
    client.models.overrides["w_draft"] = _long_draft
    work = _approved(client, _coursework(client))
    _, job = _run(client, work["id"], "DRAFT")
    assert job["status"] == "COMPLETED", job.get("failure")
    tasks = client.models.tasks
    compressed = max(i for i, t in enumerate(tasks) if t == "w_compress")
    assert "w_final" in tasks[compressed:] and "w_evaluate" in tasks[compressed:] and "w_integrity" in tasks[compressed:]
    doc = client.get(f"/api/works/{work['id']}/document", headers=STUDENT).json()
    assert doc["words"] <= 1500


def test_a_draft_the_final_reviewer_still_objects_to_after_two_repairs_is_not_delivered_or_charged(works_client):
    """The final review runs on the exact (compressed) deliverable; an objection is repaired and the
    whole reviewed again, at most twice; still objecting, nothing is delivered or charged."""
    from app.runtime import get_runtime

    client = works_client
    client.models.overrides["w_draft"] = _long_draft
    finals = []

    def final(payload):
        finals.append(1)
        return {"rules": [{"rule": r["rule"], "status": "PASS", "note": "Met.", "where": ""} for r in payload["rules"]],
                "coverage": [{"id": c["id"], "answered": False, "where": ""} for c in payload["coverage"]],
                "priorities": [{"priority": p, "addressed": True, "where": ""} for p in payload["priorities"]]}

    def repair(payload):  # every repair really changes the sections it was given
        answer = fake_works.repair(payload)
        for s in answer["sections"]:
            s["paragraphs"] = [*s["paragraphs"], f"This part is now addressed ({len(finals)})."]
        return answer

    client.models.overrides["w_final"] = final
    client.models.overrides["w_repair"] = repair
    work = _approved(client, _coursework(client))
    _, job = _run(client, work["id"], "DRAFT")
    assert len(finals) == 3 and job["status"] == "FAILED" and job["failure"]["code"] == "DOCUMENT_NOT_READY"
    assert get_runtime().store.get(job["id"]).billing.state == "RELEASED" and not _work(client, work["id"])["documents"]
    tasks = client.models.tasks
    assert tasks.index("w_compress") < tasks.index("w_final")  # reviewed after compression, on what would be delivered


# --- #3: a paid plan can always be approved ---------------------------------------------------------


def test_a_plan_that_leaves_part_of_the_question_unplanned_is_completed_by_code(works_client):
    client = works_client

    def plan(payload):
        answer = fake_works.plan(payload)
        for s in answer["sections"]:
            s["coverage"] = []  # the writer forgot the question's parts
        return answer

    client.models.overrides["w_plan"] = plan
    work = _coursework(client, description=QUESTION + " Discuss the role of supervision and explain how funding affects retention.")
    _run(client, work["id"], "PLAN")
    work = _work(client, work["id"])
    planned = {c for s in work["plan"]["sections"] for c in s["coverage"]}
    assert len(work["spec"]["coverage"]) > 1 and planned == {c["id"] for c in work["spec"]["coverage"]}
    approved = client.post(f"/api/works/{work['id']}/plan/approve", headers=STUDENT, json={"baseVersion": work["planVersion"]})
    assert approved.status_code == 200 and approved.json()["planStatus"] == "APPROVED"


def test_a_plan_over_the_hard_limit_is_refused_the_same_way_at_planning_and_approval():
    from app.works.models import PlanSection, WorkPlan

    spec = _spec("COURSEWORK", "ESSAY", answers={"word_limit": "1500", "level": "LATER_UG"})
    plan = WorkPlan(title="t", sections=[PlanSection(key="analysis", heading="Analysis", words=1600, min_words=1600)])
    assert any("your limit is 1,500" in p for p in works_pipeline._plan_problems(plan, spec))


# --- #4: a revision delivers and charges only what passed --------------------------------------------


def test_a_revision_keeps_a_change_that_failed_review_out_and_charges_only_its_share(works_client):
    from app.runtime import get_runtime

    client = works_client
    work = _approved(client, _coursework(client))
    _run(client, work["id"], "DRAFT")
    before = {s["key"]: s["paragraphs"] for s in client.get(f"/api/works/{work['id']}/document", headers=STUDENT).json()["sections"]}
    client.post(f"/api/works/{work['id']}/requests", headers=STUDENT, json={"instruction": "Add a sharper opening.", "sections": ["introduction"]})
    client.post(f"/api/works/{work['id']}/requests", headers=STUDENT, json={"instruction": "Say more about supervision.", "sections": ["conclusion"]})
    work = client.post(f"/api/works/{work['id']}/requests", headers=STUDENT, json={"instruction": "Use more local examples throughout.", "sections": []}).json()

    def evaluate(payload):
        answer = fake_works.answer("w_evaluate", payload)
        for r in answer["results"]:
            if r["key"] == "introduction":  # the revised introduction never passes its review
                r["verdict"] = "REPAIR"
                r["issues"] = [{"type": "clarity", "severity": "major", "instruction": "The opening now contradicts the position."}]
        return answer

    client.models.overrides["w_evaluate"] = evaluate
    _, job = _run(client, work["id"], "REVISE")
    assert job["status"] == "COMPLETED" and job["outcome"] == "PARTIAL", job.get("failure")
    stored = get_runtime().store.get(job["id"])
    assert 0 < stored.delivery["WORK_REVISE"] < 1 and any("Introduction" in w for w in job["warnings"])
    after = {s["key"]: s["paragraphs"] for s in client.get(f"/api/works/{work['id']}/document", headers=STUDENT).json()["sections"]}
    assert after["introduction"] == before["introduction"] and after["conclusion"] != before["conclusion"]
    status = {r["text"]: r["status"] for r in _work(client, work["id"])["requests"]}
    assert status == {"Add a sharper opening.": "OPEN", "Say more about supervision.": "APPLIED", "Use more local examples throughout.": "OPEN"}


# --- #5: limits count what their scope names -------------------------------------------------------


def _doc(words: int, table_words: int = 0) -> WorkDocument:
    table = [["Area", "Detail"], ["x " * table_words, "y"]] if table_words else None
    return WorkDocument(kind="COURSEWORK", variant="ESSAY", title="t", spec_version=1, plan_version=1,
                        sections=[WorkSection(key="analysis", heading="Analysis", paragraphs=["word " * words], table=table)])


def test_a_section_table_counts_toward_the_word_limit():
    spec = _spec("COURSEWORK", "ESSAY", answers={"word_limit": "1000", "level": "LATER_UG"})
    check = VALIDATORS["limits.hard_max"]
    within = check(Context(spec=spec, stage="FINAL", inputs=WorkInputs(title="A work"), doc=_doc(950)), {"id": "SH-004"})
    over = check(Context(spec=spec, stage="FINAL", inputs=WorkInputs(title="A work"), doc=_doc(950, table_words=100)), {"id": "SH-004"})
    assert within[0] == "PASS" and over[0] == "FAIL"


def test_references_count_when_the_scope_names_them_and_are_shown_when_it_is_silent(monkeypatch):
    from app.proposals import evidence as ev

    monkeypatch.setattr(ev, "reference_list", lambda sources, style="APA7": ["ref " * 300])
    base = _spec("COURSEWORK", "ESSAY", answers={"word_limit": "1000", "level": "LATER_UG"})
    check = VALIDATORS["limits.hard_max"]

    def result(scope):
        spec = base.model_copy(update={"limits": [Limit(type="WORD", max=1000, scope=scope)]})
        return check(Context(spec=spec, stage="FINAL", inputs=WorkInputs(title="A work"), doc=_doc(950)), {"id": "SH-004"})

    assert result(["core_narrative", "references"])[0] == "FAIL"  # 950 + 300 against an all-inclusive 1,000
    silent = result(["core"])  # the instructions do not say: a visible warning that does not hold the draft back
    assert silent[0] == "WARN" and "1,250 with the references" in silent[1]
    assert result(["core_narrative"])[0] == "PASS"  # the references are stated not to count


# --- #6: table cells are held to the same rule as prose ---------------------------------------------


def test_an_unsupported_figure_in_a_table_cell_is_withheld():
    from app.proposals.ai import SectionText, Table
    from app.works.models import WorkStepInput

    spec = _spec("COURSEWORK", "ESSAY", answers={"word_limit": "1000", "level": "LATER_UG"})
    inp = WorkStepInput(work_id="wrk_x", step="DRAFT", kind="COURSEWORK", variant="ESSAY", inputs=WorkInputs(title="A work"), spec=spec)
    text = SectionText(key="analysis", paragraphs=["The analysis is careful."],
                       table=Table(caption="Coverage", rows=[["District", "Coverage"], ["Kamuli", "Coverage reached 73.4% in 2019."]]))
    cleaned = works_pipeline._strip(inp, text, {}, "")
    assert cleaned.table.rows[1] == ["Kamuli", ""] and cleaned.paragraphs == ["The analysis is careful."]


def test_a_paragraph_with_many_number_tokens_keeps_its_sentences():
    from app.proposals.ai import SectionText, Table
    from app.works.models import WorkStepInput

    spec = _spec("COURSEWORK", "ESSAY", answers={"word_limit": "1000", "level": "LATER_UG"})
    inp = WorkStepInput(work_id="wrk_x", step="DRAFT", kind="COURSEWORK", variant="ESSAY", inputs=WorkInputs(title="A work"), spec=spec)
    names = ["Training", "Transport", "Salaries", "Supplies", "Printing", "Meetings", "Airtime", "Fuel", "Rent", "Audit", "Insurance", "Security", "Water",
             "Power", "Internet"]
    paragraph = " ".join(f"{name} costs ⟦N:budget.line.B{n}⟧." for n, name in enumerate(names, start=1))  # fifteen tokens, no typed figure
    text = SectionText(key="budget", paragraphs=[paragraph], table=Table(caption="", rows=[]))
    assert works_pipeline._strip(inp, text, {}, "").paragraphs == [paragraph]


# --- #7: long instructions are read in full ---------------------------------------------------------


def test_a_long_brief_is_read_in_parts_so_a_limit_at_the_end_is_found(works_client):
    client = works_client
    work = client.post("/api/works", headers=STUDENT, json={"kind": "COURSEWORK", "variant": "ESSAY", "inputs": {"title": "CHWs", "description": QUESTION}}).json()
    brief = QUESTION + "\n" + ("Background reading about the course and its aims. " * 4000) + "\nYour essay must not exceed 1,500 words."
    work = client.post(f"/api/works/{work['id']}/sources/text", headers=STUDENT, json={"role": "BRIEF", "name": "Brief", "text": brief}).json()
    _, job = _run(client, work["id"], "READ")
    assert job["status"] == "COMPLETED", job.get("failure")
    assert client.models.tasks.count("w_read") >= 2
    work = _work(client, work["id"])
    assert any(r["key"] == "limit.words" and r["number"] == 1500 for r in work["spec"]["requirements"])


def test_a_reading_is_searched_across_its_whole_text():
    text = ("General background on national systems. " * 2000) + " Supervision of community health workers improved retention in Kamuli."
    chunks = works_pipeline._relevant_chunks(text, "supervision retention of community health workers")
    assert len(chunks) == works_pipeline.READING_CHUNKS and "Supervision of community health workers" in chunks[-1]


# --- #8: private names never reach a search ------------------------------------------------------------


def test_names_from_the_students_experience_never_reach_a_search(works_client):
    from app.runtime import get_runtime
    from app.works.models import WorkStepInput

    client = works_client
    experience = "On placement I supported Sister Namuli at the clinic. The midwife Achieng showed me how referrals work in Kamuli, Uganda."
    work = client.post("/api/works", headers=STUDENT, json={"kind": "COURSEWORK", "variant": "REFLECTIVE",
                                                            "inputs": {"title": "My placement in Kamuli",
                                                                       "description": "Reflect on your clinical placement in Kamuli and explain what it taught you about referrals.",
                                                                       "experience": experience}}).json()
    work = client.post(f"/api/works/{work['id']}/answers", headers=STUDENT,
                       json={"answers": {"word_limit": "1500", "level": "LATER_UG", "ai_policy": "NOT_MENTIONED"}, "skipRest": True, "baseVersion": work["specVersion"]}).json()
    assert work["spec"]["gate"] == "PASS", work["spec"]["blockers"]
    client.post(f"/api/works/{work['id']}/spec/confirm", headers=STUDENT, json={"baseVersion": work["specVersion"]})
    quoted = client.post(f"/api/works/{work['id']}/steps", headers=STUDENT, json={"step": "PLAN"}).json()
    rt = get_runtime()
    job = rt.store.get(quoted["job"]["id"])
    inp = WorkStepInput.model_validate_json(rt.files.get(f"{job.storage_prefix()}/internal/work_input.json"))
    # A name in the student's own account is protected even when the topic names it too; a country stays searchable.
    assert {"namuli", "achieng", "student", "kamuli"} <= set(inp.private) and "uganda" not in inp.private


# --- #9: frozen content is enforced -------------------------------------------------------------------


def test_a_step_priced_before_a_rule_changed_fails_without_charge(works_client, monkeypatch):
    from app.rules import library
    from app.runtime import get_runtime

    client = works_client
    work = _coursework(client)
    quoted = client.post(f"/api/works/{work['id']}/steps", headers=STUDENT, json={"step": "PLAN"}).json()
    hashes = library.content_hashes()
    monkeypatch.setattr(library, "content_hashes", lambda: {**hashes, "validators": "validators-v3"})  # a release that changed the validators
    client.post(f"/api/works/{work['id']}/steps/{quoted['job']['id']}/submit", headers=STUDENT, json={"quoteId": quoted["quote"]["id"]})
    from tests.test_api import wait

    job = wait(client, quoted["job"]["id"], timeout=60)
    assert job["status"] == "FAILED" and job["failure"]["code"] == "ENGINE_CHANGED"
    assert get_runtime().store.get(job["id"]).billing.state == "RELEASED" and "w_plan" not in client.models.tasks


# --- #10: a quote verifies the value extracted from it ---------------------------------------------


def test_a_quote_verifies_its_number_and_unit_not_just_its_words():
    # Codex audit, second round: a figure is read whole, and a limit's number is the one next to its unit.
    assert not value_in_quote("ceiling", "USD 50", 50, "Grants of up to USD 50k are available.")
    assert value_in_quote("ceiling", "USD 50,000", 50000, "Grants of up to USD 50k are available.")
    assert not value_in_quote("limit.pages", "50 pages", 50, "A 5-page limit applies to all 50 applicants.")
    assert value_in_quote("limit.pages", "5 pages", 5, "A 5-page limit applies to all 50 applicants.")
    assert not value_in_quote("limit.words", "500", 500, "Essays must not exceed 1,500 words.")
    assert not value_in_quote("ceiling", "1.5", 1.5, "Up to USD 1.5 million.")
    assert value_in_quote("limit.pages", "5 pages", 5, "The concept note has a 5-page maximum.")
    assert not value_in_quote("limit.pages", "50 pages", 50, "The concept note has a 5-page maximum.")
    assert not value_in_quote("limit.words", "1500", 1500, "No more than 1,500 characters.")
    assert value_in_quote("limit.words", "2500", 2500, "Essays of two thousand five hundred words.")
    assert value_in_quote("ceiling", "50000", 50000, "Grants of up to USD 50k are available.")
    assert value_in_quote("duration_months", "24 months", 24, "Projects run for 2 years.")
    assert not value_in_quote("citation_style", "APA7", None, "Use Harvard referencing throughout.")
    source = SourceFile(id="s1", name="Call", role="CALL", words=10, sha256="x", path="p")
    item = {"sourceId": "s1", "key": "limit.pages", "value": "50 pages", "number": 50, "unit": "pages", "hard": True, "quote": "a 5-page maximum",
            "location": "", "weight": None, "countsToward": [], "amends": False}
    found, _ = requirements_from({"requirements": [item]}, [source], {"s1": "The concept note has a 5-page maximum."})
    assert not found[0].verified  # shown to the student to confirm, never locked as read


def test_a_web_found_article_is_cited_by_its_authors_from_its_registered_record(monkeypatch):
    """Real-model pilot 2026-09-30: web-found journal pages were cited by journal name ("BMC Pregnancy
    and Childbirth, 2016"). Crossref's record for the same title and year gives the authors."""
    from app.analysis import fetch
    from app.proposals import pipeline as proposal_pipeline

    record = {"doi": "10.1186/s12884-016-1000-1", "title": "Effect of a community health worker intervention on facility delivery in Uganda",
              "authors": "Nsibambi, K.; Okello, J.", "year": "2016", "container": "BMC Pregnancy and Childbirth"}
    monkeypatch.setattr(fetch, "crossref_search", lambda text, rows=3: [dict(record)])
    assert proposal_pipeline._registered_by_title("Effect of a Community Health Worker Intervention on Facility Delivery in Uganda", "2016")["authors"].startswith("Nsibambi")
    assert proposal_pipeline._registered_by_title("Effect of a community health worker intervention on facility delivery in Uganda", "2019") is None  # another year
    assert proposal_pipeline._registered_by_title("A different article about maternal health in Uganda", "2016") is None


def test_a_final_review_repair_gets_the_sections_evidence_and_brief(works_client):
    """An objection that a part of the question is unanswered or unsupported can only be repaired
    with support: the writer gets the section's evidence, brief and rules, as when it drafted it
    (live coursework failed twice when repairs had no evidence, 2026-10-01)."""
    client = works_client
    calls = []

    def final(payload):
        first = not calls
        return {"rules": [{"rule": r["rule"], "status": "PASS", "note": "Met.", "where": ""} for r in payload["rules"]],
                "coverage": [{"id": c["id"], "answered": not first, "where": ""} for c in payload["coverage"]],
                "priorities": [{"priority": p, "addressed": True, "where": ""} for p in payload["priorities"]]}

    def repair(payload):
        calls.append(payload["sections"])
        answer = fake_works.repair(payload)
        for s in answer["sections"]:
            s["paragraphs"] = [*s["paragraphs"], "This part is now addressed."]
        return answer

    client.models.overrides["w_final"] = final
    client.models.overrides["w_repair"] = repair
    work = _approved(client, _coursework(client))
    _, job = _run(client, work["id"], "DRAFT")
    assert job["status"] == "COMPLETED" and calls
    for section in calls[-1]:
        assert section["evidence"] and {"id", "statement"} <= set(section["evidence"][0])
        assert section["brief"] and "rules" in section and any("Answer this part" in i for i in section["issues"])
