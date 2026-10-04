"""The daily canary: a real writing check from a dedicated account, alerts on a bad previous run,
and its runs kept apart from the reliability figures."""

import hashlib
import time

from tests.conftest import grant

CANARY = "canary@example.com"
CANARY_UID = "u_" + hashlib.sha256(CANARY.encode()).hexdigest()[:20]
ADMIN = {"Authorization": "Dev demo@paperaid.app"}


def _setup(monkeypatch, alerts: list, sent: list):
    from app import notify
    from app.runtime import get_runtime

    rt = get_runtime()
    for name, value in {"canary_enabled": True, "canary_uid": CANARY_UID, "canary_email": CANARY, "alert_email": "owner@example.com",
                        "sendgrid_api_key": "sg-test", "notify_from": "hello@paperaid.test"}.items():
        monkeypatch.setattr(rt.settings, name, value)
    monkeypatch.setattr(notify, "_email", lambda rt_, to, subject, text: (alerts if to == "owner@example.com" else sent).append((subject, text)))
    grant(CANARY, 1_000_000)
    return rt


def _finished(rt, job_id: str, timeout: float = 60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = rt.store.get(job_id)
        if job.status.value in ("COMPLETED", "FAILED", "CANCELLED"):
            return job
        time.sleep(0.2)
    raise AssertionError("canary did not finish")


def test_the_canary_is_off_until_its_account_is_set(fixed_client):
    assert fixed_client.post("/tasks/canary").json() == {"skipped": "off"}


def test_a_canary_run_is_a_real_paid_writing_check_kept_out_of_the_figures(fixed_client, monkeypatch):
    alerts, sent = [], []
    rt = _setup(monkeypatch, alerts, sent)
    started = fixed_client.post("/tasks/canary").json()["started"]
    job = _finished(rt, started)
    assert job.status.value == "COMPLETED" and job.outcome == "FULL" and job.selection.writing == "AI_CHECK"
    assert job.owner_uid == CANARY_UID and job.billing.charged > 0  # paid from its own credits, like anyone
    assert sent == [] and alerts == []  # the canary's own results are not "your work is ready" messages
    report = fixed_client.get("/api/admin/reliability?days=7", headers=ADMIN).json()
    assert [r["id"] for r in report["canary"]] == [started] and report["canaryEnabled"] is True
    assert all(line["id"] != started for line in report["jobs"]) and report["services"] == []


def test_a_bad_previous_run_is_alerted_once_and_a_new_run_starts(fixed_client, monkeypatch):
    from app.jobs.models import JobFailure, JobStatus

    alerts, sent = [], []
    rt = _setup(monkeypatch, alerts, sent)
    first = fixed_client.post("/tasks/canary").json()["started"]
    _finished(rt, first)

    def failed(j):
        j.status, j.failure = JobStatus.FAILED, JobFailure(code="PROVIDER_DOWN", user_message="x", retryable=False)
        return j

    rt.store.update(first, failed)
    assert fixed_client.post("/tasks/canary").json() == {"skipped": "already run today", "job": first}  # a scheduler retry: the day's run, not another
    second = fixed_client.post("/tasks/canary?rerun=true").json()["started"]  # a deliberate extra run
    assert second and second != first
    assert len(alerts) == 1 and first in alerts[0][1] and "PROVIDER_DOWN" in alerts[0][1]
    _finished(rt, second)
    assert fixed_client.post("/tasks/canary?rerun=true").json()["started"]  # the clean run raises nothing
    assert len(alerts) == 1


def test_two_calls_on_one_day_start_one_paid_run(fixed_client, monkeypatch):
    """Finding 12: the day is claimed atomically, so a retry never starts a second paid job."""
    alerts, sent = [], []
    rt = _setup(monkeypatch, alerts, sent)
    first = fixed_client.post("/tasks/canary").json()["started"]
    _finished(rt, first)
    again = fixed_client.post("/tasks/canary").json()
    assert again == {"skipped": "already run today", "job": first}
    from app.jobs import canary

    assert [j.id for j in canary.history(rt)] == [first]


def test_a_rerun_uses_its_own_text_so_answers_are_not_replayed():
    from app.jobs import canary

    assert canary.paper("4 October 2026", 1) != canary.paper("4 October 2026", 2)


def test_a_run_that_would_cost_more_than_its_budget_does_not_start(fixed_client, monkeypatch):
    alerts, sent = [], []
    rt = _setup(monkeypatch, alerts, sent)
    monkeypatch.setattr(rt.settings, "canary_budget_usd", 0.0)
    assert fixed_client.post("/tasks/canary").json() == {"started": None, "error": "OVER_BUDGET"}
    assert len(alerts) == 1 and "OVER_BUDGET" in alerts[0][1]
    assert rt.store.get_wallet(CANARY_UID).held == 0  # nothing reserved for a run that never started


def test_every_paragraph_carries_the_day_so_answers_are_never_replayed():
    from app.jobs import canary

    assert canary.paper("4 October 2026") != canary.paper("5 October 2026")
    assert all("{day}" in p for p in canary._PARAGRAPHS)
