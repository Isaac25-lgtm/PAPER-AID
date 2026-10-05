"""The second audit's reproductions. All model and messaging calls are local fakes."""

import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest

from app.core.errors import PermanentStageError
from app.datalab import qual
from app.datalab.pipeline import DataRunner, _words, bounded_parts
from app.works.ai import Classified
from app.works.pipeline import _final_results, _results_decision
from tests.test_api import STUDENT
from tests.test_audit_20261004 import TALK, _qual, _results_model, _review
from tests.test_audit_20261004 import qlab as qlab  # noqa: F401
from tests.test_datalab import _analyse, _project
from tests.test_datalab import lab as lab  # noqa: F401


@pytest.mark.parametrize("text,count,tail", [
    ("Call 0772 123456 2025", 1, "2025"),
    ("0772123456 0773123456", 2, ""),
    ("Call 0772 123456. 2025 was difficult.", 1, "2025 was difficult."),
    ("+256 772 123 456, +256 773 123 456", 2, ""),
    ("(0772) 123 456; 0773-123-456", 2, ""),
    ("00256 772 123 456 in 2025", 1, "2025"),
])
def test_adjacent_figures_and_multiple_phones_are_redacted(text, count, tail):
    cleaned, replaced = qual.pseudonymise(text, [])
    assert replaced == count and cleaned.count("[phone]") == count
    assert "772" not in cleaned and "773" not in cleaned and tail in cleaned
    assert qual.leaks(text, []) and not qual.leaks(cleaned, [])


@pytest.mark.parametrize("text", ["scores were 0.25 0.30 0.45 0.10 at baseline", "rates of 0.5, 0.75 and 0.9 per 1,000", "In 2019 and 2021 we paid 20,000 shillings"])
def test_decimals_and_figures_are_not_taken_for_phone_numbers(text):
    """Claude's audit 2026-10-05: a run of decimals was read as a phone number and partly replaced."""
    assert qual.pseudonymise(text, [])[0] == text and not qual.leaks(text, [])


def test_phone_followed_by_year_is_never_stored_or_sent(qlab):
    from app.runtime import get_runtime
    from tests.test_audit_20261004 import _settled

    p = _qual(qlab)
    r = qlab.post(f"/api/datalab/{p['id']}/documents/text", headers=STUDENT,
                  json={"label": "Interview A", "text": TALK + " Call 0772 123456 2025.", "consent": True})
    assert r.status_code == 200
    rt = get_runtime()
    doc = rt.store.get_datalab(p["id"]).documents[0]
    assert "0772" not in rt.files.get(doc.path).decode()
    qlab.post(f"/api/datalab/{p['id']}/themes", headers=STUDENT)
    assert _settled(qlab, p["id"])["reports"]
    assert all("0772" not in payload for task, payload in zip(qlab.models.tasks, qlab.models.requests, strict=True) if task.startswith("q_"))


def test_legacy_labels_stop_before_any_model_call_or_hold(qlab):
    from app.runtime import get_runtime

    p = _qual(qlab)
    qlab.post(f"/api/datalab/{p['id']}/documents/text", headers=STUDENT, json={"label": "Interview A", "text": TALK, "consent": True})
    rt = get_runtime()

    def legacy(q):
        q.documents[0].label = "Agnes Akello"
        q.documents[0].anonymisation_version = 0
        return q

    rt.store.update_datalab(p["id"], legacy)
    uid = rt.store.get_datalab(p["id"]).owner_uid
    before = rt.store.get_wallet(uid).model_dump()
    r = qlab.post(f"/api/datalab/{p['id']}/themes", headers=STUDENT)
    assert r.status_code == 400 and r.json()["code"] == "TRANSCRIPTS_NEED_REUPLOAD"
    assert not qlab.models.tasks and rt.store.get_wallet(uid).model_dump() == before


def test_a_legacy_frozen_qual_job_stops_before_reaching_a_model():
    inp = qual.QualInput(project_id="p", title="T", question="Q", documents=[qual.QualDoc(id="d", label="Agnes Akello", path="p", sha256="s", words=20)])
    ctx = SimpleNamespace(job=SimpleNamespace(quote=None), get_json=lambda name: inp.model_dump())
    with pytest.raises(PermanentStageError, match="TRANSCRIPTS_NEED_REUPLOAD"):
        qual._input(ctx)


def test_filtered_complete_case_populations_are_compared_by_original_identity(lab):
    from app.datalab import service
    from app.runtime import get_runtime

    csv = "eligibility,x,y\n" + "\n".join(f"{i},{i if i > 5 else ''},{i if i not in range(101, 105) else ''}" for i in range(1, 111))
    p = _project(lab, csv, "test.csv")
    pid = p["id"]
    for variable, low, high in (("x", "1", "100"), ("y", "6", "105")):
        _analyse(lab, pid, {"kind": "DESCRIBE", "variables": [variable],
                            "filters": [{"variable": "eligibility", "op": "BETWEEN", "low": low, "high": high}]})
    rt = get_runtime()
    masks = [service._unpack(rt.files.get(ref.rows), 110) for ref in rt.store.get_datalab(pid).analyses]
    assert [int(m.sum()) for m in masks] == [95, 96] and int((masks[0] ^ masks[1]).sum()) == 1
    for suffix in ("report", "workbook"):
        r = lab.post(f"/api/datalab/{pid}/{suffix}", headers=STUDENT, json={}) if suffix == "report" else lab.get(f"/api/datalab/{pid}/workbook", headers=STUDENT)
        assert r.status_code == 400 and r.json()["code"] == "OVERLAPPING_RESULTS", r.text


def test_old_row_masks_are_out_of_date_even_when_the_data_did_not_change(lab):
    from app.datalab import service
    from app.runtime import get_runtime

    p = _project(lab)
    result = _analyse(lab, p["id"], {"kind": "DESCRIBE", "variables": ["score"]})
    rt = get_runtime()
    stored = rt.store.get_datalab(p["id"])
    ref = stored.analyses[0]
    # The pre-fix fingerprint had no rowIdentity version.
    variables = {v.name: v for v in service.variables_of(rt, stored)}
    entry = next(v for v in stored.versions if v.version == stored.current)
    old = {"data": entry.sha256, "alpha": stored.alpha, "threshold": stored.threshold, "rules": service.RULES_VERSION,
           "survey": sorted((n, s.survey) for n, s in stored.settings.items() if s.survey),
           "variables": [(n, variables[n].kind, variables[n].excluded, variables[n].title()) for n in ref.variables], "spec": ref.spec_sha}

    def legacy(q):
        q.analyses[0].fingerprint = hashlib.sha256(json.dumps(old, sort_keys=True, default=str).encode()).hexdigest()
        return q

    rt.store.update_datalab(p["id"], legacy)
    assert lab.get(f"/api/datalab/{p['id']}", headers=STUDENT).json()["analyses"][0]["stale"]
    r = lab.post(f"/api/datalab/{p['id']}/report", headers=STUDENT, json={"analyses": [result["id"]]})
    assert r.status_code == 400 and r.json()["code"] == "STALE_ANALYSES"


@pytest.mark.parametrize("quote", ["four people live in Istanbul today", "people live in Istanbul today", "Istanbul today and tomorrow."])
def test_unicode_case_expansion_keeps_exact_source_spans(quote):
    source = "İ four people live in Istanbul today and tomorrow."
    assert qual._locate(quote, source) == quote
    assert qual._locate("i̇ four people live", source) == "İ four people live"


def test_a_wrong_reversal_explanation_cannot_be_used_as_approval():
    flipped = [{"id": i, "statedAs": level, "reads": "activity" if i == "OP1" else level, "note": ""}
               for i, level in (("G1", "goal"), ("O1", "outcome"), ("OP1", "output"))]
    review = _review([], flipped, [{"id": "OP1", "before": "outcome", "now": "activity", "reason": "Changed."}])
    previous = {"OP1": Classified(id="OP1", statedAs="output", reads="output", note="A service.")}
    decision = _results_decision(review, _results_model(), [{"rule": "FP-028"}], "R", [], previous, {"OP1"})
    assert decision.outcome == "NOT_REVIEWED" and decision.reason == "REVIEW_CLARIFICATION"


@pytest.mark.parametrize("clarifies", [True, False])
def test_reversal_clarification_is_bounded_and_never_invokes_another_writer(monkeypatch, clarifies):
    from app.works import pipeline

    model = _results_model()
    replies = [_review([{"rule": "", "ids": ["I1"], "text": "Repair indicator."}])]
    flipped = [{"id": i, "statedAs": lv, "reads": "activity" if i == "OP1" else lv, "note": ""}
               for i, lv in (("G1", "goal"), ("O1", "outcome"), ("OP1", "output"))]
    replies += [_review([], flipped), _review([]) if clarifies else _review([], flipped)]
    seen, repairs = [], []

    def review(payload):
        seen.append(payload)
        return replies[len(seen) - 1]

    runner = SimpleNamespace(budget_reached=False, final_review_results=review, results=lambda payload: repairs.append(payload))
    monkeypatch.setattr(pipeline, "_results_problems", lambda *args: [])
    monkeypatch.setattr(pipeline, "_results_from", lambda answer: (model, []))
    _, _, decision = _final_results(runner, {}, model, [], [{"rule": "FP-028"}], SimpleNamespace())
    assert len(seen) == 3 and len(repairs) == 1
    assert seen[2]["previousClassified"] == seen[1]["previousClassified"]
    assert "Explain" in seen[2]["previousIssues"][0]
    assert decision.outcome == ("APPROVED" if clarifies else "NOT_REVIEWED")


@pytest.mark.parametrize("size", [6100, 6900, 7500])
def test_repeated_context_never_escapes_the_review_bound(size):
    from app.ai.orchestration import FINAL_PART_WORDS

    entry = {"key": "results", "heading": "Results", "paragraphs": ["A sentence. " * 700], "bullets": [], "tables": [], "notes": []}
    repeated = {"chapterThree": "context " * size}
    try:
        parts, manifest = bounded_parts([entry], repeated)
    except PermanentStageError as exc:
        assert exc.code == "REVIEW_INPUT_TOO_LARGE"
    else:
        assert all(_words({"context": repeated, "manifest": manifest, "sections": p}) <= FINAL_PART_WORDS for p in parts)


@pytest.mark.parametrize("runner_class", [DataRunner, qual.QualRunner])
def test_actual_review_methods_refuse_an_oversized_request_before_calling_any_provider(monkeypatch, runner_class):
    called = []
    monkeypatch.setattr(runner_class, "_call", lambda *args: called.append(args))
    runner = object.__new__(runner_class)
    with pytest.raises(PermanentStageError, match="REVIEW_INPUT_TOO_LARGE"):
        runner.final_review({"context": "word " * 8000})
    assert not called


def test_a_single_oversized_table_heading_is_refused_not_sent():
    entry = {"key": "t", "heading": "Table", "paragraphs": [], "tables": [{"title": "Table", "columns": ["word " * 8000], "rows": [["value"]]}]}
    with pytest.raises(PermanentStageError, match="REVIEW_INPUT_TOO_LARGE"):
        bounded_parts([entry], {})


def test_oversized_shared_evidence_fails_the_job_and_returns_its_hold(lab, monkeypatch):
    from app.datalab import pipeline
    from app.runtime import get_runtime
    from tests.test_datalab import _wait

    p = _project(lab)
    _analyse(lab, p["id"], {"kind": "DESCRIBE", "variables": ["score"]})
    rt = get_runtime()
    uid = rt.store.get_datalab(p["id"]).owner_uid
    before = rt.store.get_wallet(uid)
    monkeypatch.setattr(pipeline, "_dataset", lambda inp: {"preparation": "supporting evidence " * 4000})
    started = lab.post(f"/api/datalab/{p['id']}/report", headers=STUDENT, json={})
    assert started.status_code == 200, started.text
    view = _wait(lab, p["id"], lambda v: bool(v["reportFailure"]) or bool(v["reports"]))
    job = rt.store.get(started.json()["id"])
    after = rt.store.get_wallet(uid)
    assert not view["reports"] and job.status == "FAILED" and job.failure.code == "REVIEW_INPUT_TOO_LARGE"
    assert job.billing.charged == 0 and job.billing.state == "RELEASED"
    entries = [e for e in after.entries if e.job_id == job.id]
    assert [e.kind for e in entries] == ["HOLD", "RELEASE"] and entries[0].amount == entries[1].amount > 0
    assert (after.available, after.held) == (before.available, before.held)
    assert "d_report" in lab.models.tasks and "d_report_review" not in lab.models.tasks


@pytest.mark.parametrize("code", [100, 101, 102, "101"])
def test_sms_acceptance_is_read_from_the_recipient_response(monkeypatch, code):
    from app import notify

    rt = SimpleNamespace(settings=SimpleNamespace(africastalking_api_key="test", africastalking_username="test", sms_sender=""))
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **k: httpx.Response(201, json={"SMSMessageData": {"Recipients": [{"number": "+256772123456", "statusCode": code}]}}))
    assert notify._sms(rt, "+256772123456", "test")


@pytest.mark.parametrize("code", [403, 404, 406])
def test_permanent_sms_rejection_is_not_a_success_or_an_endless_retry(monkeypatch, code):
    from app import notify

    rt = SimpleNamespace(settings=SimpleNamespace(africastalking_api_key="test", africastalking_username="test", sms_sender=""))
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **k: httpx.Response(201, json={"SMSMessageData": {"Recipients": [{"number": "+256772123456", "statusCode": code}]}}))
    with pytest.raises(notify.SmsRejected):
        notify._sms(rt, "+256772123456", "test")


@pytest.mark.parametrize("body", [{}, {"SMSMessageData": {"Recipients": []}}, {"SMSMessageData": {"Recipients": [{"number": "+256773123456", "statusCode": 101}]}},
                                  {"SMSMessageData": {"Recipients": [{"number": "+256772123456", "statusCode": 407}]}}])
def test_invalid_or_temporary_sms_responses_do_not_become_sent(monkeypatch, body):
    from app import notify

    rt = SimpleNamespace(settings=SimpleNamespace(africastalking_api_key="test", africastalking_username="test", sms_sender=""))
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **k: httpx.Response(201, json=body))
    assert not notify._sms(rt, "+256772123456", "test")


def test_sms_balance_rejection_alerts_the_owner_and_remains_unsent(monkeypatch):
    from app import notify

    rt = SimpleNamespace(settings=SimpleNamespace(africastalking_api_key="test", africastalking_username="test", sms_sender=""))
    alerts = []
    monkeypatch.setattr(notify, "alert", lambda *args: alerts.append(args))
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **k: httpx.Response(201, json={"SMSMessageData": {"Recipients": [{"number": "+256772123456", "statusCode": 405}]}}))
    assert not notify._sms(rt, "+256772123456", "test") and len(alerts) == 1


def test_permanently_rejected_sms_does_not_retry_while_an_email_still_can(lab, monkeypatch):
    from app import notify
    from app.jobs.models import Job, JobStatus, Notice, utcnow
    from app.runtime import get_runtime

    rt = get_runtime()
    job = Job(id="job_sms_rejection", owner_uid="test", owner_email="test@example.com", status=JobStatus.COMPLETED,
              expires_at=utcnow(), notice=Notice(key="READY:1", outcome="READY"))
    rt.store.create(job)
    sent = []
    monkeypatch.setattr(notify, "_targets", lambda *args: {"email": "test@example.com", "sms": "+256772123456"})
    monkeypatch.setattr(notify, "_email", lambda *args: sent.append("email") or False)

    def reject(*args):
        sent.append("sms")
        raise notify.SmsRejected("403")

    monkeypatch.setattr(notify, "_sms", reject)
    notify.deliver(rt, job.id)
    notice = rt.store.get(job.id).notice
    assert notice.channels == {"email": "FAILED", "sms": "PERMANENT_FAILURE"} and notice.pending
    rt.store.update(job.id, lambda j: (setattr(j.notice, "next_at", None), j)[1])
    monkeypatch.setattr(notify, "_email", lambda *args: sent.append("email") or True)
    notify.deliver(rt, job.id)
    assert sent == ["email", "sms", "email"]
    assert not rt.store.get(job.id).notice.pending
