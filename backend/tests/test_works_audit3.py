"""Codex's audit of c6ba362 (2026-10-01): a Results Model approved despite a failed code check, a short
draft delivered after its repairs, final-review repairs aimed at the whole document or at nothing, a
model-written target date surviving an edit, and review parts over their bound."""

import pytest

from app.works import pipeline as works_pipeline
from tests import fake_works
from tests.test_single_reviewer import _requests
from tests.test_single_reviewer_audit import _funding
from tests.test_works import _coursework, _run, _work
from tests.test_works_audit import _approved


@pytest.fixture
def works_client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKS_ENABLED", '["CONCEPT_NOTE","COURSEWORK","FUNDING_PROPOSAL"]')
    from tests.conftest import _client

    yield from _client(tmp_path, monkeypatch, "cost")


def _broken_link(payload):
    answer = fake_works.results(payload)
    answer["outputs"][1]["outcomeId"] = "O9"  # an outcome that does not exist (FP-019)
    return answer


# --- 1: the Results Model's code checks are part of its approval -----------------------------------------


def test_a_results_model_failing_a_code_check_is_not_approved_or_charged(works_client):
    from app.runtime import get_runtime

    client = works_client
    client.models.overrides["w_results"] = _broken_link  # every repair keeps the broken link
    work = _funding(client)
    _, job = _run(client, work["id"], "PLAN")
    review = _work(client, work["id"])["resultsReview"]
    assert review["outcome"] == "OBJECTIONS" and review["reason"] == "CODE_RULE" and any(o.startswith("FP-019") for o in review["objections"])
    assert client.models.tasks.count("w_results") >= 2  # repaired (an identical second repair request replays from the response cache)
    assert job["outcome"] == "PARTIAL" and set(get_runtime().store.get(job["id"]).delivery.values()) == {0.0}


def test_a_results_model_link_paperaid_broke_is_repaired_then_approved(works_client):
    client = works_client
    calls = []

    def results(payload):
        calls.append(payload.get("critique"))
        return _broken_link(payload) if len(calls) == 1 else fake_works.results(payload)

    client.models.overrides["w_results"] = results
    work = _funding(client)
    _, job = _run(client, work["id"], "PLAN")
    assert any(c.startswith("FP-019") for c in calls[1])  # code's finding reached the repair
    assert _work(client, work["id"])["resultsReview"]["outcome"] == "APPROVED" and job["outcome"] == "FULL"


def test_the_applicants_missing_figures_never_block_the_results_approval():
    """Baselines, targets, quantities and costs are the student's: their absence is not PaperAid's defect."""
    from app.works.models import ResultsModel

    model, lines = works_pipeline._results_from(fake_works.results({"spec": {"duration": 12}}))
    assert all(i.target is None and i.baseline is None for i in model.indicators) and all(li.unit_cost == 0 for li in lines)
    spec = fake_works_spec()
    assert works_pipeline._results_problems(ResultsModel.model_validate(model.model_dump()), lines, spec) == []


def fake_works_spec():
    from tests.test_works_golden import _spec

    return _spec("FUNDING_PROPOSAL", "NGO_PROJECT")


# --- 2: a new draft still well under its length after the repairs is not delivered or charged -----------


def test_a_draft_still_too_short_after_its_repairs_fails_without_charge(works_client):
    from app.runtime import get_runtime

    client = works_client

    def short(payload):
        answer = fake_works.draft(payload)
        for s in answer["sections"]:
            words = " ".join(s["paragraphs"]).split()
            s["paragraphs"] = [" ".join(words[: int(len(words) * 0.6)]).rstrip(".,;") + "."]
        return answer

    client.models.overrides["w_draft"] = short
    client.models.overrides["w_repair"] = lambda payload: {"sections": [{"key": s["key"], "paragraphs": [*s["text"], "One more sentence."], "table": {"caption": "", "rows": []}}
                                                                        for s in payload["sections"]]}  # repairs that never reach the length
    work = _approved(client, _coursework(client))
    _, job = _run(client, work["id"], "DRAFT")
    assert job["status"] == "FAILED" and job["failure"]["code"] == "DOCUMENT_NOT_READY"
    assert "CW-007" in get_runtime().store.get(job["id"]).failure_detail
    assert get_runtime().store.get(job["id"]).billing.state == "RELEASED" and not _work(client, work["id"])["documents"]


# --- 3: final-review repairs are aimed, and funder priorities repaired ------------------------------------


def test_a_blank_location_names_no_section():
    from app.works.models import PlanSection

    sections = [PlanSection(key="introduction", heading="Introduction", brief="b", words=200), PlanSection(key="body", heading="Main discussion", brief="b", words=900)]
    assert works_pipeline._where_keys("", sections) == [] and works_pipeline._where_keys("  ", sections) == []
    assert works_pipeline._where_keys("Main discussion", sections) == ["body"]


def test_a_document_wide_objection_repairs_the_main_section_only(works_client):
    client = works_client
    rounds = []

    def final(payload):
        first = not rounds
        rounds.append(1)
        return {"rules": [{"rule": r["rule"], "status": "FAIL" if first and r["rule"] == "CW-008" else "PASS", "note": "The command word is not fulfilled.", "where": ""}
                          for r in payload["rules"]],
                "coverage": [{"id": c["id"], "answered": True, "where": ""} for c in payload["coverage"]],
                "priorities": [{"priority": p, "addressed": True, "where": ""} for p in payload["priorities"]]}

    def repair(payload):
        answer = fake_works.repair(payload)
        for s in answer["sections"]:
            s["paragraphs"] = [*s["paragraphs"], "The evaluation now reaches a judgement."]
        return answer

    client.models.overrides["w_final"] = final
    client.models.overrides["w_repair"] = repair
    work = _approved(client, _coursework(client))
    plan = _work(client, work["id"])["plan"]
    _, job = _run(client, work["id"], "DRAFT")
    assert job["status"] == "COMPLETED", job.get("failure")
    asked = [s for r in _requests(client, "w_repair") for s in r["sections"] if any(i.startswith("CW-008") for i in s["issues"])]
    largest = max(plan["sections"], key=lambda s: s["words"])["key"]
    assert [s["key"] for s in asked] == [largest]


def test_a_priority_the_reviewer_found_unaddressed_is_repaired(works_client, monkeypatch):
    client = works_client
    real_spec = works_pipeline._spec
    monkeypatch.setattr(works_pipeline, "_spec", lambda inp: real_spec(inp).model_copy(update={"priorities": ["Gender equality"]}))
    rounds = []

    def final(payload):
        first = not rounds
        rounds.append(1)
        return {"rules": [{"rule": r["rule"], "status": "PASS", "note": "Met.", "where": ""} for r in payload["rules"]],
                "coverage": [{"id": c["id"], "answered": True, "where": ""} for c in payload["coverage"]],
                "priorities": [{"priority": p, "addressed": not first, "where": ""} for p in payload["priorities"]]}

    def repair(payload):
        answer = fake_works.repair(payload)
        for s in answer["sections"]:
            s["paragraphs"] = [*s["paragraphs"], "Women's and girls' needs shape every activity."]
        return answer

    client.models.overrides["w_final"] = final
    client.models.overrides["w_repair"] = repair
    work = _approved(client, _coursework(client))
    _, job = _run(client, work["id"], "DRAFT")
    assert job["status"] == "COMPLETED", job.get("failure")
    asked = [s["key"] for r in _requests(client, "w_repair") for s in r["sections"] if any(i.startswith("Address this priority of the call") for i in s["issues"])]
    assert len(asked) == 1 and len(rounds) == 2


# --- 4: a model-written target date is cleared ------------------------------------------------------------


def test_model_written_target_dates_are_cleared_like_other_applicant_figures():
    answer = fake_works.results({"spec": {"duration": 12}})
    for indicator in answer["indicators"]:
        indicator["targetDate"] = "2027-12"
    model, _ = works_pipeline._results_from(answer)
    assert all(i.target_date == "" for i in model.indicators)


# --- 5: every review part is within its bound --------------------------------------------------------------


def test_a_paragraph_or_table_longer_than_a_part_is_split_within_the_bound():
    paragraph = " ".join(f"Sentence {n} carries a handful of words." for n in range(1500))  # about 9,000 words
    table = {"caption": "Workplan", "rows": [["Activity", "Months"], *[["Train village health teams", "1 to 3"]] * 900]}
    pieces = works_pipeline._split_entry({"key": "body", "heading": "Main discussion", "text": [paragraph], "tables": [table]}, 7000)
    assert len(pieces) >= 3 and all(works_pipeline._words_of_entry(p) <= 7000 for p in pieces)
    assert " ".join(t for p in pieces for t in p["text"]).split() == paragraph.split()  # nothing lost or reordered
    assert sum(len(t["rows"]) - 1 for p in pieces for t in p["tables"]) == 900


def test_every_final_review_part_is_within_the_bound(works_client, monkeypatch):
    from app.ai.orchestration import payload_words

    monkeypatch.setattr(works_pipeline, "FINAL_PART_WORDS", 900)  # whole requests: about 460 words of every one are repeated context (Codex review 2026-10-07, finding 8)
    client = works_client

    def one_long_paragraph(payload):
        answer = fake_works.draft(payload)
        for s in answer["sections"]:
            s["paragraphs"] = [" ".join(s["paragraphs"])]
        return answer

    client.models.overrides["w_draft"] = one_long_paragraph
    work = _approved(client, _coursework(client))
    _, job = _run(client, work["id"], "DRAFT")
    assert job["status"] == "COMPLETED", job.get("failure")
    parts = _requests(client, "w_final")
    assert len(parts) > 1 and all(payload_words(part) <= 900 for part in parts), [payload_words(p) for p in parts]


# --- Codex's re-check of the fixes (2026-10-01) ------------------------------------------------------------


def test_a_missing_field_the_writer_supplies_or_no_budget_lines_block_the_results_approval():
    answer = fake_works.results({"spec": {"duration": 12}})
    answer["indicators"][0]["meansOfVerification"] = ""
    model, lines = works_pipeline._results_from(answer)
    problems = works_pipeline._results_problems(model, lines, fake_works_spec())
    assert any(p.startswith("FP-030") and "I1" in p for p in problems) and not any("target" in p or "baseline" in p for p in problems)
    model, _ = works_pipeline._results_from(fake_works.results({"spec": {"duration": 12}}))
    assert any(p.startswith("FP-037: Activities with no budget line: A1, A2, A3") for p in works_pipeline._results_problems(model, [], fake_works_spec()))


def test_a_single_table_row_longer_than_a_part_is_split_within_the_bound():
    row = ["A1", " ".join(["word"] * 7100)]
    pieces = works_pipeline._split_entry({"key": "workplan", "heading": "Workplan", "text": ["Short."], "tables": [{"caption": "Plan", "rows": [["Activity", "Detail"], row]}]}, 7000)
    assert all(works_pipeline._words_of_entry(p) <= 7000 for p in pieces)
    assert sum(len(r[1].split()) for p in pieces for t in p["tables"] for r in t["rows"][1:]) == 7100
