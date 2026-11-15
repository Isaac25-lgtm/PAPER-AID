"""Codex's audit of 8ebecb4..6373ceb (2026-10-04): each reproduction it reported, as a regression test."""



from tests.test_api import STUDENT

H = STUDENT








TALK = ("The walk to the clinic takes most of the morning for women in our village, and when labour starts at night there is no transport. "
        "The boda boda riders charge a lot when it rains and the road floods, so mothers wait for the river to go down before they travel. "
        "The health workers are kind but the distance is the problem for everyone here, and the VHT can help if they have transport money.")


# --- 1. identifiers in labels, file names and every phone layout --------------------------------------------------










# --- 2. every quotation that ships is reviewed; a withheld one ships nowhere ---------------------------------------




# --- 3. a small denominator is hidden with its count and rate --------------------------------------------------------






# --- 4. analyses released together are compared on the rows they used ----------------------------------------------




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
    assert quiet.outcome == "NOT_REVIEWED" and quiet.reason == "REVIEW_CLARIFICATION"
    explained = _review([], flipped, [{"id": "OP1", "before": "output", "now": "activity", "reason": "It describes holding sessions, not what they deliver."}])
    assert _results_decision(explained, _results_model(), rules, "R", [], earlier, {"G1", "O1", "OP1"}).outcome == "OBJECTIONS"
    assert _results_decision(_review([], flipped), _results_model(), rules, "R", [], earlier, {"G1", "O1"}).outcome == "OBJECTIONS"  # OP1 changed


# --- 6. a late worker can't overwrite the winning attempt ---------------------------------------------------------------




# --- 7. long inputs are split inside a paragraph or section ---------------------------------------------------------






# --- 8. a quotation is exported as the transcript has it ---------------------------------------------------------------




# --- 9. the transcript limits hold against a concurrent upload ----------------------------------------------------------




# --- 10. a totals map counts its rows as rows --------------------------------------------------------------------------




# --- 11. one message, one alert ------------------------------------------------------------------------------------------


def test_an_alert_is_sent_once_however_many_callers(client, monkeypatch):
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


def test_a_retry_sends_only_what_is_still_owed_and_only_when_due(client, monkeypatch):
    from app import notify
    from app.jobs.models import Notice
    from app.runtime import get_runtime

    rt = get_runtime()
    sent = []
    monkeypatch.setattr(notify, "_targets", lambda rt_, job: {"email": "a@b.test", "sms": "+256772123456"})
    monkeypatch.setattr(notify, "_email", lambda *a: sent.append("email") or True)
    monkeypatch.setattr(notify, "_sms", lambda *a: sent.append("sms") or True)
    from datetime import timedelta

    from app.jobs.models import Job, JobStatus, utcnow

    job_id = "job_retry_owed"  # any finished job owes its notice the same way
    rt.store.create(Job(id=job_id, owner_uid="test", owner_email="test@example.com", status=JobStatus.COMPLETED, expires_at=utcnow()))

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




# --- 12. a report never leaves out a chosen analysis silently --------------------------------------------------------




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




