"""The second audit's reproductions. All model and messaging calls are local fakes."""

from types import SimpleNamespace

import httpx
import pytest

from app.works.ai import Classified
from app.works.pipeline import _final_results, _results_decision
from tests.test_audit_20261004 import _results_model, _review


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

    runner = SimpleNamespace(budget_reached=False, final_review_results=review, results=lambda payload: repairs.append(payload),
                             audit_rounds=lambda count, start=0: range(start, start + count))
    monkeypatch.setattr(pipeline, "_results_problems", lambda *args: [])
    monkeypatch.setattr(pipeline, "_results_from", lambda answer: (model, []))
    _, _, decision = _final_results(runner, {}, model, [], [{"rule": "FP-028"}], SimpleNamespace())
    assert len(seen) == 3 and len(repairs) == 1
    assert seen[2]["previousClassified"] == seen[1]["previousClassified"]
    assert "Explain" in seen[2]["previousIssues"][0]
    assert decision.outcome == ("APPROVED" if clarifies else "NOT_REVIEWED")










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


def test_permanently_rejected_sms_does_not_retry_while_an_email_still_can(client, monkeypatch):
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
