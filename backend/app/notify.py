"""Telling a person their work is ready, or that it stopped (owner roadmap 2026-10-03, item 4). Email
through SendGrid and SMS through Africa's Talking, each only when its key is set (Secret Manager);
with neither, nothing is sent and the settings page offers nothing. A message names the service and
links to the work: it never carries paper text, titles or content.

Durable since Codex's audit (finding 11): the message a job owes is recorded on the job in the same
transaction as its outcome (`state.transition`), each channel's delivery is recorded, a failed send
is tried again a few times with growing waits, and maintenance (`sweep`) delivers anything still
pending, so neither a crash nor a provider outage loses it. One sender at a time per job, and a
channel already sent is never sent again. A failure to send never affects the work itself."""

import logging
import secrets
from datetime import timedelta
from typing import Literal

import httpx

from app.core.logging import log
from app.jobs.models import Job, Notice, utcnow
from app.runtime import Runtime

logger = logging.getLogger("paperaid.notify")
Outcome = Literal["READY", "STOPPED"]
ATTEMPTS = 5  # sends tried per channel before the message is given up (logged)
LEASE = timedelta(minutes=2)


def channels(rt: Runtime) -> dict[str, bool]:
    s = rt.settings
    return {"email": bool(s.sendgrid_api_key and s.notify_from), "sms": bool(s.africastalking_username and s.africastalking_api_key)}


def _what(job: Job) -> str:
    s = job.selection
    if s.datalab != "NONE":
        return "analysis report"
    if s.work_kind != "NONE":
        return {"COURSEWORK": "coursework", "CONCEPT_NOTE": "concept note", "FUNDING_PROPOSAL": "funding proposal"}[s.work_kind]
    if s.proposal == "CONCEPT":
        return "concept paper"
    if s.proposal.startswith("CHAPTER_"):
        return f"Chapter {s.proposal[-1]}"
    if s.proposal != "NONE":
        return "proposal"
    return "paper"


def _link(rt: Runtime, job: Job) -> str:
    base = rt.settings.app_url.rstrip("/")
    if job.work_id:
        return f"{base}/app/works/{job.work_id}"
    if job.project_id:
        return f"{base}/app/projects/{job.project_id}"
    if job.datalab_id:
        return f"{base}/app/datalab/{job.datalab_id}"
    return f"{base}/app/jobs/{job.id}"


def _targets(rt: Runtime, job: Job) -> dict[str, str]:
    """Where this job's message goes: nowhere for the daily canary, for an internal step of one Start
    that completed (reading, the plan), for a closing account, or with no channel set up."""
    notice = job.notice
    if notice is None or job.owner_uid == rt.settings.canary_uid:
        return {}
    internal = job.selection.bundled and (job.selection.work in ("READ", "PLAN") or job.selection.proposal == "PLAN")
    if notice.outcome == "READY" and internal:
        return {}
    on = channels(rt)
    wallet = rt.store.get_wallet(job.owner_uid)
    if wallet is None or wallet.closing:
        return {}
    out = {}
    if on["email"] and wallet.notify_email and job.owner_email:
        out["email"] = job.owner_email
    if on["sms"] and wallet.notify_sms and wallet.phone:
        out["sms"] = wallet.phone
    return out


def _message(rt: Runtime, job: Job, outcome: Outcome) -> tuple[str, str]:
    what, link = _what(job), _link(rt, job)
    if outcome == "READY":
        return f"Your {what} is ready", f"Your {what} is ready. Open it here: {link}"
    return f"Your {what} stopped", f"PaperAid couldn't finish your {what}. Nothing extra was charged. See what happened: {link}"


def deliver(rt: Runtime, job_id: str) -> None:
    """Send what the job still owes, if anything, recording each channel's result. What is still owed and
    whether its retry time has come are decided inside the claim, from the record as it stands then, and
    only the claim holding the lease records the results (Codex audit 2026-10-04, finding 11: two
    overlapping calls sent the same email twice)."""
    job = rt.store.get(job_id)
    if job is None or job.notice is None or not job.notice.pending:
        return
    targets = _targets(rt, job)
    key = job.notice.key
    sender = secrets.token_hex(8)
    wanted: dict[str, str] = {}

    def claim(j: Job) -> Job | None:
        n = j.notice
        now = utcnow()
        if n is None or n.key != key or not n.pending or (n.lease_until is not None and n.lease_until > now) or (n.next_at is not None and n.next_at > now):
            return None
        wanted.clear()
        wanted.update({ch: to for ch, to in targets.items() if n.channels.get(ch) != "SENT"})
        if not wanted:  # nothing (more) to send: done
            n.pending = False
            return j
        n.lease_until, n.sender = now + LEASE, sender
        return j

    claimed = rt.store.update(job_id, claim)
    if claimed is None or claimed.notice is None or not wanted:
        return
    subject, line = _message(rt, claimed, claimed.notice.outcome)
    settings_link = rt.settings.app_url.rstrip("/") + "/app/settings"
    results = {}
    for channel, to in wanted.items():
        if channel == "email":
            results[channel] = _email(rt, to, subject, f"{line}\n\nYou can turn these messages off in your settings: {settings_link}\n\nPaperAid")
        else:
            results[channel] = _sms(rt, to, f"PaperAid: {line}")

    def record(j: Job) -> Job | None:
        n = j.notice
        if n is None or n.key != key or n.sender != sender:
            return None
        for channel, ok in results.items():
            n.channels[channel] = "SENT" if ok else "FAILED"
        n.attempts += 1
        n.lease_until, n.sender = None, ""
        done = all(n.channels.get(ch) == "SENT" for ch in targets)
        if done or n.attempts >= ATTEMPTS:
            n.pending = False
            if not done:
                log(logger, logging.WARNING, "message given up", jobId=j.id, attempts=n.attempts)
        else:
            n.next_at = utcnow() + timedelta(minutes=2 ** n.attempts)
        return j

    rt.store.update(job_id, record)


def after_job(rt: Runtime, job: Job) -> None:
    """Called whenever a job reaches its final state."""
    deliver(rt, job.id)


def stopped(rt: Runtime, job_id: str) -> None:
    """A one-Start plan that completed but whose work stopped there (PaperAid's review or checks didn't
    approve it): the job owes a "stopped" message instead of nothing."""

    def owe(j: Job) -> Job | None:
        key = f"STOPPED:{j.generation}"
        if j.notice is not None and j.notice.key == key:
            return None
        j.notice = Notice(key=key, outcome="STOPPED")
        return j

    if rt.store.update(job_id, owe) is not None:
        deliver(rt, job_id)


def sweep(rt: Runtime, limit: int = 200) -> int:
    """Maintenance: deliver every message still pending (after a crash, or a failed send's wait)."""
    ids = rt.store.pending_notice_ids(limit)
    for job_id in ids:
        deliver(rt, job_id)
    return len(ids)


def provider_problem(rt: Runtime, code: str, detail: str) -> None:
    """A key or a provider balance the owner must fix, from any paid path (a job's step or an estimate):
    one alert a day per problem (Codex audit 2026-10-04, finding 13: estimates raised none)."""
    if code == "PROVIDER_CONFIG":
        alert(rt, "AI provider can't be used", f"{detail}. Jobs and estimates stop and are refunded until it is fixed.", f"provider:{utcnow():%Y-%m-%d}:{detail}")


def alert(rt: Runtime, subject: str, text: str, key: str) -> None:
    """An operations alert for the owner (the daily canary): always logged at ERROR (Cloud Monitoring
    alerts on it), and emailed to `alert_email` when email is set up, once per key. IDs and codes only."""
    token = secrets.token_hex(8)
    if rt.store.claim_once(f"alert:{key}", token) != token:  # a constant value let every caller through (Codex audit 2026-10-04)
        return
    log(logger, logging.ERROR, "alert", subject=subject, detail=text)
    if channels(rt)["email"] and rt.settings.alert_email:
        _email(rt, rt.settings.alert_email, f"PaperAid: {subject}", f"{text}\n\nSee the reliability page: {rt.settings.app_url.rstrip('/')}/admin/reliability")


def _email(rt: Runtime, to: str, subject: str, text: str) -> bool:
    s = rt.settings
    try:
        r = httpx.post("https://api.sendgrid.com/v3/mail/send", timeout=15, headers={"Authorization": f"Bearer {s.sendgrid_api_key}"},
                       json={"personalizations": [{"to": [{"email": to}]}], "from": {"email": s.notify_from, "name": "PaperAid"}, "subject": subject,
                             "content": [{"type": "text/plain", "value": text}]})
    except httpx.HTTPError as exc:  # a message that can't be sent never affects the work; it is tried again
        log(logger, logging.WARNING, "email not sent", error=type(exc).__name__)
        return False
    if r.status_code >= 300:
        log(logger, logging.WARNING, "email not sent", status=r.status_code)
        return False
    return True


def _sms(rt: Runtime, phone: str, text: str) -> bool:
    s = rt.settings
    try:
        r = httpx.post("https://api.africastalking.com/version1/messaging", timeout=15, headers={"apiKey": s.africastalking_api_key, "Accept": "application/json"},
                       data={"username": s.africastalking_username, "to": phone, "message": text[:300], **({"from": s.sms_sender} if s.sms_sender else {})})
    except httpx.HTTPError as exc:
        log(logger, logging.WARNING, "sms not sent", error=type(exc).__name__)
        return False
    if r.status_code >= 300:
        log(logger, logging.WARNING, "sms not sent", status=r.status_code)
        return False
    return True
