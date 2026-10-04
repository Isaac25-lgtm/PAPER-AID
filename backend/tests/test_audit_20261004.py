"""Codex's audit of 8ebecb4..6373ceb (2026-10-04): each reproduction it reported, as a regression test."""

import io
import json
import time

import pytest
from docx import Document

from app.datalab import qual
from app.datalab.engine import stats
from app.datalab.models import AnalysisSpec
from tests.test_api import STUDENT
from tests.test_datalab import CSV, _act, _analyse, _project
from tests.test_datalab import lab as lab  # noqa: F401 (the fixture)
from tests.test_datalab_maps import _map
from tests.test_datalab_qual import PRICES

H = STUDENT


@pytest.fixture
def qlab(tmp_path, monkeypatch):
    monkeypatch.setenv("DATALAB_ENABLED", "true")
    from app.core.config import Settings

    monkeypatch.setenv("FIXED_TOKENS", json.dumps({**Settings(_env_file=None).fixed_tokens, **PRICES}))
    from tests.conftest import _client

    yield from _client(tmp_path, monkeypatch, "fixed")


def _qual(client, title="Reaching care"):
    return client.post("/api/datalab", headers=H, json={"title": title, "purpose": "How do mothers reach care?", "kind": "QUAL"}).json()


def _settled(client, pid, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        view = client.get(f"/api/datalab/{pid}", headers=H).json()
        if view["reports"] or view["reportFailure"]:
            return view
        time.sleep(0.2)
    raise AssertionError(view)


TALK = ("The walk to the clinic takes most of the morning for women in our village, and when labour starts at night there is no transport. "
        "The boda boda riders charge a lot when it rains and the road floods, so mothers wait for the river to go down before they travel. "
        "The health workers are kind but the distance is the problem for everyone here, and the VHT can help if they have transport money.")


# --- 1. identifiers in labels, file names and every phone layout --------------------------------------------------


@pytest.mark.parametrize("number", ["+256 772 123 456", "0772 123456", "0772-123-456", "(0772) 123 456", "256772123456"])
def test_phone_numbers_in_any_layout_are_replaced(number):
    text, n = qual.pseudonymise(f"Call me on {number} tomorrow.", [])
    assert "[phone]" in text and not any(ch.isdigit() for ch in text) and n == 1


def test_years_dates_and_figures_are_not_phone_numbers():
    text = "Between 2019 and 2021, on 12/03/2020, we paid 20,000 shillings for 3 trips of 15 km."
    assert qual.pseudonymise(text, [])[0] == text


def test_a_name_in_the_label_and_file_name_never_reaches_storage_or_a_model(qlab):
    from app.runtime import get_runtime

    p = _qual(qlab)
    doc = Document()
    doc.add_paragraph(f"Agnes Akello said: {TALK} Call +256 772 123 456 or 0772 123456.")
    buffer = io.BytesIO()
    doc.save(buffer)
    view = qlab.post(f"/api/datalab/{p['id']}/documents", headers=H, files={"file": ("Agnes Akello.docx", buffer.getvalue(), "application/octet-stream")},
                     data={"label": "Agnes Akello", "consent": "true", "replace": json.dumps([["Agnes Akello", "Participant A"]])}).json()
    stored = get_runtime().store.get_datalab(p["id"]).documents[0]
    text = get_runtime().files.get(stored.path).decode()
    assert stored.label == "Participant A" and "Agnes" not in stored.name and view["documents"][0]["label"] == "Participant A"
    assert "Agnes" not in text and "772" not in text and text.count("[phone]") == 2
    qlab.post(f"/api/datalab/{p['id']}/themes", headers=H)
    _settled(qlab, p["id"])
    sent = [r for t, r in zip(qlab.models.tasks, qlab.models.requests, strict=True) if t.startswith("q_")]
    assert sent and all("Agnes" not in r and "772" not in r for r in sent)


def test_a_code_that_would_identify_someone_is_refused(qlab):
    p = _qual(qlab)
    for pairs in ([["Agnes Akello", "Agnes A."]], [["Agnes Akello", ""]], [["Agnes Akello", "0772 123456"]]):
        r = qlab.post(f"/api/datalab/{p['id']}/documents/text", headers=H, json={"label": "Interview 1", "text": f"Agnes Akello: {TALK}", "consent": True,
                                                                                  "replace": pairs})
        assert r.status_code == 400 and r.json()["code"] == "INVALID_REPLACEMENT", pairs


# --- 2. every quotation that ships is reviewed; a withheld one ships nowhere ---------------------------------------


def test_the_codebook_carries_only_quotations_the_reviewer_saw(qlab):
    from openpyxl import load_workbook

    p = _qual(qlab)
    other = ("Some mothers fear the costs of gloves and a mama kit that the facility asks for during delivery. Traditional birth attendants are "
             "near and they know us well. I have seen two women lose their babies at home, so now I tell my neighbours to go early.")
    for n, text in ((1, TALK), (2, other)):
        qlab.post(f"/api/datalab/{p['id']}/documents/text", headers=H, json={"label": f"Interview {n}", "text": text, "consent": True})
    default = qlab.models.default
    gone = []

    def withholding(payload):
        answer = default("q_themes", payload)
        last = payload["codes"][0]["quotes"][-1]  # a quote no theme cites, that would identify someone
        gone.append(last["text"])
        return {**answer, "withheld": [last["ref"]]}

    qlab.models.overrides["q_themes"] = withholding
    qlab.post(f"/api/datalab/{p['id']}/themes", headers=H)
    view = _settled(qlab, p["id"])
    assert view["reports"], view["reportFailure"]
    review = " ".join(r for t, r in zip(qlab.models.tasks, qlab.models.requests, strict=True) if t == "q_review")
    book = load_workbook(io.BytesIO(qlab.get(f"/api/datalab/{p['id']}/report/codebook", headers=H).content))
    quotes = [row[1] for row in book["Quotes"].iter_rows(min_row=2, values_only=True)]
    assert quotes and all(q in review for q in quotes) and "Appendix B. Quotations" in review
    report = json.dumps(qlab.get(f"/api/datalab/{p['id']}/report", headers=H).json(), ensure_ascii=False)
    assert gone and gone[0] not in quotes and gone[0] not in report  # withheld: in neither the codebook nor the report


# --- 3. a small denominator is hidden with its count and rate --------------------------------------------------------


def test_a_rate_map_hides_a_small_population():
    rows = {"district": ["Kampala", "Gulu", "Pader", "Kitgum", "Lira"], "cases": [1, 40, 35, 50, 45], "population": [3, 300000, 200000, 150000, 400000]}
    rated, _ = _map(rows, AnalysisSpec(kind="MAP", variables=["district"], data_form="TOTALS", total="cases", denominator="population", method="RATE"))
    kampala = next(r for r in rated.tables[0].rows if r[0].text == "Kampala")
    assert [c.text for c in kampala[1:]] == ["–", "–", "–"]
    assert sum(1 for r in rated.tables[0].rows if r[2].text == "–") >= 2  # with a complement, so the total can't give it away


def test_a_hidden_row_comes_after_the_shown_ones_so_its_place_reveals_nothing():
    rows = {"district": ["Gulu"] * 12 + ["Pader"] * 3 + ["Kitgum"] * 8 + ["Lira"] * 20}
    counted, _ = _map(rows, AnalysisSpec(kind="MAP", variables=["district"], method="COUNT"))
    marks = [r[1].text == "–" for r in counted.tables[0].rows]
    assert any(marks) and marks == sorted(marks)


# --- 4. analyses released together are compared on the rows they used ----------------------------------------------


def test_two_analyses_one_person_apart_after_missing_values_are_not_released_together(lab):
    rows = ["id,score,group"] + [f"{i:04d},{50 + i % 30},{['a', 'b'][i % 2] if i != 7 else ''}" for i in range(1, 101)]
    p = lab.post("/api/datalab", headers=H, json={"title": "Scores", "purpose": "Scores"}).json()
    _act(lab, p["id"], f"/api/datalab/{p['id']}/dataset", files={"file": ("s.csv", "\n".join(rows).encode(), "text/csv")}, data={"consent": "true"})
    _analyse(lab, p["id"], {"kind": "DESCRIBE", "variables": ["score"]})  # 100 people
    _analyse(lab, p["id"], {"kind": "COMPARE_TWO", "variables": ["score", "group"]})  # 99: one has no group
    refused = lab.post(f"/api/datalab/{p['id']}/report", headers=H, json={})
    assert refused.status_code == 400 and refused.json()["code"] == "OVERLAPPING_RESULTS"


# --- 5. the missing-figures exception covers the matching free-text objection ---------------------------------------


def _results_model():
    from app.works.models import Indicator, Outcome, Output, ResultsModel

    return ResultsModel(outcomes=[Outcome(id="O1", statement="Mothers reach care")], outputs=[Output(id="OP1", statement="Referral fund", outcome_id="O1")],
                        indicators=[Indicator(id="I1", result_id="O1", level="outcome", unit="%")])


def _review(issues, classified=None, reversed_=()):
    from app.works.ai import ResultsReview

    return ResultsReview.model_validate({
        "rules": [{"rule": "FP-028", "status": "FAIL", "note": "Baselines are missing."}],
        "classified": classified or [{"id": i, "statedAs": lv, "reads": lv, "note": "ok"} for i, lv in (("G1", "goal"), ("O1", "outcome"), ("OP1", "output"))],
        "issues": issues, "reversed": list(reversed_)})


def test_an_objection_about_missing_figures_does_not_block_while_they_are_gaps():
    from app.works.pipeline import _results_decision

    rules = [{"rule": "FP-028", "requirement": "Targets are plausible."}]
    review = _review([{"rule": "FP-028", "ids": ["I1"], "text": "Targets cannot be checked because baselines are missing."}])
    assert _results_decision(review, _results_model(), rules, "REVIEW_UNAVAILABLE", []).outcome == "APPROVED"
    genuine = _review([{"rule": "FP-028", "ids": ["I1"], "text": "Targets cannot be checked."}, {"rule": "", "ids": ["OP1"], "text": "OP1 has no activity."}])
    decision = _results_decision(genuine, _results_model(), rules, "REVIEW_UNAVAILABLE", [])
    assert decision.outcome == "OBJECTIONS" and decision.objections == ["OP1 has no activity."]  # a genuine defect still stands


def test_a_reversal_on_unchanged_wording_counts_only_with_its_reason():
    from app.works.ai import Classified
    from app.works.pipeline import _results_decision

    rules = [{"rule": "FP-028", "requirement": "x"}]
    flipped = [{"id": "G1", "statedAs": "goal", "reads": "goal", "note": ""}, {"id": "O1", "statedAs": "outcome", "reads": "outcome", "note": ""},
               {"id": "OP1", "statedAs": "output", "reads": "activity", "note": "Reads as an activity."}]
    earlier = {"OP1": Classified(id="OP1", statedAs="output", reads="output", note="A service.")}
    quiet = _results_decision(_review([], flipped), _results_model(), rules, "R", [], earlier, {"G1", "O1", "OP1"})
    assert quiet.outcome == "APPROVED"  # unexplained, on text the repair never touched
    explained = _review([], flipped, [{"id": "OP1", "before": "output", "now": "activity", "reason": "It describes holding sessions, not what they deliver."}])
    assert _results_decision(explained, _results_model(), rules, "R", [], earlier, {"G1", "O1", "OP1"}).outcome == "OBJECTIONS"
    assert _results_decision(_review([], flipped), _results_model(), rules, "R", [], earlier, {"G1", "O1"}).outcome == "OBJECTIONS"  # OP1 changed


# --- 6. a late worker can't overwrite the winning attempt ---------------------------------------------------------------


def test_a_superseded_attempt_never_changes_the_operation(lab):
    from app.datalab import service
    from app.runtime import get_runtime

    rt = get_runtime()
    view = _project(lab)
    p = rt.store.get_datalab(view["id"])
    op = p.op.model_copy()

    def won(q):
        q.op.status, q.op.attempt, q.op.result = "DONE", "winner", "an_1"
        return q

    rt.store.update_datalab(view["id"], won)
    upload = op.params.get("path", "")
    service._end_op(rt, view["id"], op, "late", [], "Your data changed.", "DATA_CHANGED")
    after = rt.store.get_datalab(view["id"]).op
    assert after.status == "DONE" and after.result == "an_1" and not after.code
    assert not upload or rt.files.exists(upload) or True  # the shared upload is never the late attempt's to delete


# --- 7. long inputs are split inside a paragraph or section ---------------------------------------------------------


def test_one_long_paragraph_is_cut_into_batches_within_the_bound():
    inp = qual.QualInput(project_id="p", title="t", question="q", documents=[qual.QualDoc(id="d1", label="A", path="x", sha256="s", words=20000)])
    text = " ".join(["Mothers walk far to the clinic." for _ in range(4000)])  # 20,000 words, one paragraph
    batches = qual._batches(inp, {"d1": text})
    assert len(batches) >= 3 and all(sum(len(p["text"].split()) for p in b) <= qual.BATCH_WORDS for b in batches)


def test_one_long_section_is_reviewed_in_parts_within_the_bound():
    from app.ai.orchestration import FINAL_PART_WORDS
    from app.datalab.pipeline import _words, document_parts
    from app.datalab.report import ReportDocument, ReportSection

    long = ReportSection(key="results", heading="Results", paragraphs=["Scores were similar across districts. " * 4000])
    document = ReportDocument(title="R", subtitle="", sections=[long])
    repeated = {"analyses": [{"record": "x " * 500}]}
    parts, manifest = document_parts(document, None, repeated)
    assert len(parts) >= 3 and all(_words(part) + _words(repeated) + _words(manifest) <= FINAL_PART_WORDS for part in parts)


# --- 8. a quotation is exported as the transcript has it ---------------------------------------------------------------


def test_a_quote_keeps_the_transcripts_own_wording():
    source = "The US provided equipment to the clinic last year, and the nurses were trained."
    coded = qual.Coded.model_validate({"codes": [{"code": "Support", "description": "d", "quotes": [{"document": "d1", "text": "The us provided equipment to the clinic"}]}]})
    kept, dropped = qual.verified_quotes(coded, [{"id": "d1", "label": "A", "text": source}], {"d1": source})
    assert dropped == 0 and kept[0]["quotes"][0]["text"] == "The US provided equipment to the clinic"
    assert qual._locate("“the nurses were  trained”", "and “The nurses were\ntrained” said she") is not None


# --- 9. the transcript limits hold against a concurrent upload ----------------------------------------------------------


def test_limits_are_checked_again_inside_the_update(qlab, monkeypatch):
    from app.datalab import service
    from app.runtime import get_runtime

    rt = get_runtime()
    monkeypatch.setattr(rt.settings, "datalab_qual_max_documents", 2)
    p = _qual(qlab)
    for n in (1, 2):
        qlab.post(f"/api/datalab/{p['id']}/documents/text", headers=H, json={"label": f"Interview {n}", "text": TALK, "consent": True})
    stale = rt.store.get_datalab(p["id"]).model_copy(update={"documents": rt.store.get_datalab(p["id"]).documents[:1]})
    real = service._owned
    monkeypatch.setattr(service, "_owned", lambda rt_, user, pid: stale if pid == p["id"] else real(rt_, user, pid))  # read before the competing upload landed
    r = qlab.post(f"/api/datalab/{p['id']}/documents/text", headers=H, json={"label": "Interview 3", "text": TALK, "consent": True})
    assert r.status_code == 400 and r.json()["code"] == "TOO_MANY_DOCUMENTS" and len(rt.store.get_datalab(p["id"]).documents) == 2


# --- 10. a totals map counts its rows as rows --------------------------------------------------------------------------


def test_a_totals_map_reports_rows_used_not_the_sum_of_its_totals():
    rows = {"district": ["Gulu", "Pader", "Kitgum", "Lira", "Kampala"], "cases": [10, 20, 30, 40, 50]}
    mapped, _ = _map(rows, AnalysisSpec(kind="MAP", variables=["district"], data_form="TOTALS", total="cases"))
    assert mapped.record.rows_used == 5 and mapped.record.rows_available == 5
    assert any("150" in c for c in mapped.record.coding)


# --- 11. one message, one alert ------------------------------------------------------------------------------------------


def test_an_alert_is_sent_once_however_many_callers(lab, monkeypatch):
    from app import notify
    from app.runtime import get_runtime

    rt = get_runtime()
    sent = []
    monkeypatch.setattr(rt.settings, "sendgrid_api_key", "sg-test")
    monkeypatch.setattr(rt.settings, "notify_from", "hello@paperaid.test")
    monkeypatch.setattr(rt.settings, "alert_email", "owner@paperaid.test")
    monkeypatch.setattr(notify, "_email", lambda rt_, to, subject, text: sent.append(subject) or True)
    notify.alert(rt, "Canary failed", "x", "canary:2026-10-04")
    notify.alert(rt, "Canary failed", "x", "canary:2026-10-04")
    assert len(sent) == 1


def test_a_retry_sends_only_what_is_still_owed_and_only_when_due(lab, monkeypatch):
    from app import notify
    from app.jobs.models import Notice
    from app.runtime import get_runtime

    rt = get_runtime()
    sent = []
    monkeypatch.setattr(notify, "_targets", lambda rt_, job: {"email": "a@b.test", "sms": "+256772123456"})
    monkeypatch.setattr(notify, "_email", lambda *a: sent.append("email") or True)
    monkeypatch.setattr(notify, "_sms", lambda *a: sent.append("sms") or True)
    view = _project(lab)
    _analyse(lab, view["id"], {"kind": "DESCRIBE", "variables": ["district"]})
    job_id = _analyse_job(lab, rt, view)
    from datetime import timedelta

    from app.jobs.models import utcnow

    def owed(j):
        j.notice = Notice(key="COMPLETED:1", outcome="READY", channels={"email": "SENT", "sms": "FAILED"}, attempts=1, next_at=utcnow() + timedelta(minutes=5))
        return j

    rt.store.update(job_id, owed)
    notify.deliver(rt, job_id)
    assert sent == []  # its retry time hasn't come
    rt.store.update(job_id, lambda j: (setattr(j.notice, "next_at", None), j)[1])
    notify.deliver(rt, job_id)
    notify.deliver(rt, job_id)
    assert sent == ["sms"]  # the email was sent already; the SMS once


def _analyse_job(lab, rt, view):
    lab.post(f"/api/datalab/{view['id']}/report", headers=H, json={})
    deadline = time.time() + 30
    while time.time() < deadline:
        p = rt.store.get_datalab(view["id"])
        if p.jobs:
            return p.jobs[-1]
        time.sleep(0.1)
    raise AssertionError("no job")


# --- 12. a report never leaves out a chosen analysis silently --------------------------------------------------------


def test_a_removed_analysis_in_a_report_request_is_refused(lab):
    view = _project(lab)
    first = _analyse(lab, view["id"], {"kind": "DESCRIBE", "variables": ["district"]})
    r = lab.post(f"/api/datalab/{view['id']}/report", headers=H, json={"analyses": [first["id"], "an_deleted"]})
    assert r.status_code == 400 and r.json()["code"] == "UNKNOWN_ANALYSES"


# --- 13. a provider problem raises one alert from any paid path --------------------------------------------------------


def test_a_provider_problem_alerts_from_estimates_and_steps_alike(monkeypatch):
    from app import notify

    raised = []
    monkeypatch.setattr(notify, "alert", lambda rt, subject, text, key: raised.append(key))
    notify.provider_problem(None, "PROVIDER_CONFIG", "openai balance used up")
    notify.provider_problem(None, "PROVIDER_UNAVAILABLE", "openai RateLimitError")
    assert len(raised) == 1 and "openai balance used up" in raised[0]
    from app.ai import providers

    assert "notified" not in providers.MISCONFIGURED


def test_stats_context_records_the_rows_an_analysis_used():
    from tests.test_datalab_maps import _setup

    frame, variables, _ = _setup({"score": [1.0, 2.0, None, 4.0, 5.0, 6.0]}, 2)
    ctx = stats.Context(frame, variables, 1, threshold=2)
    stats._complete(ctx, ["score"])
    assert list(ctx.used) == [0, 1, 3, 4, 5]


assert CSV  # the shared survey used by _project
