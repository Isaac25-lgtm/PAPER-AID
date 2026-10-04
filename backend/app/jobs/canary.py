"""The daily canary (owner roadmap 2026-10-03, item 3): once a day a dedicated account runs a writing
check on a short fixed paper, through the same quote, payment, queue and pipeline as anyone else.
Before starting, it looks at the previous run and alerts the owner when that run did not finish
cleanly or is still running. Off until `canary_enabled` and the account are set; each run is capped
at `canary_budget_usd` and paid from the canary account's own credits.

Model answers are cached by their exact input, so every paragraph carries the day's date: each run
reaches the providers instead of replaying yesterday's answers."""

import io
import logging
import secrets
from datetime import timedelta

from docx import Document

from app.core.errors import AppError
from app.core.logging import log
from app.jobs.models import Job, JobStatus, ServiceSelection, utcnow
from app.runtime import Runtime

logger = logging.getLogger("paperaid.canary")
STUCK_AFTER = timedelta(hours=3)  # a writing check that has not finished by then is stuck
SELECTION = ServiceSelection(writing="AI_CHECK")

_PARAGRAPHS = (
    "Field note, {day}: households in the three parishes visited this season collect rainwater mainly from iron roofs into open drums, and "
    "most of them say the water lasts about two weeks after the last heavy rain before they return to the borehole.",
    "Field note, {day}: the households that own a covered tank report fewer trips to the borehole during the short dry season, although "
    "several of them mentioned that gutters break easily and that repairs are often delayed until the next harvest is sold.",
    "Field note, {day}: women and older children carry most of the water, and the time saved by a nearby tank is usually spent on garden "
    "work, on small trade at the trading centre, or on school homework, according to the people we spoke with.",
    "Field note, {day}: the cost of a tank remains the main reason given for not having one, followed by the lack of a strong roof; a few "
    "respondents preferred saving through a village group so that members could buy tanks one after another.",
    "Field note, {day}: these notes are descriptive and come from a small number of conversations, so they suggest questions for a "
    "structured survey rather than conclusions about how common each practice is across the district.",
)


def paper(day: str, run: int = 1) -> bytes:
    """The day's paper. A deliberate second run on the same day says so in every paragraph, so it too
    reaches the providers instead of replaying the day's cached answers."""
    when = day if run == 1 else f"{day}, check {run}"
    doc = Document()
    doc.add_heading(f"Rainwater collection in rural households: field notes ({when})", level=1)
    for text in _PARAGRAPHS:
        doc.add_paragraph(text.format(day=when))
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def history(rt: Runtime) -> list[Job]:
    """The canary account's submitted jobs, newest first."""
    from app.jobs.service import every_job

    uid = rt.settings.canary_uid
    if not uid:
        return []
    jobs = [j for j in every_job(rt, uid, None) if j.status not in (JobStatus.DRAFT, JobStatus.QUOTED)]
    return sorted(jobs, key=lambda j: j.created_at, reverse=True)


def _problem(job: Job) -> str | None:
    """What was wrong with a previous run, in IDs and codes only, or None when it was clean."""
    if job.status in (JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.AWAITING_PAYMENT):
        return f"still {job.status.value} after {STUCK_AFTER}" if utcnow() - job.created_at > STUCK_AFTER else None
    if job.status == JobStatus.COMPLETED and job.outcome != "PARTIAL":
        return None
    code = job.failure.code if job.failure else (job.outcome or "")
    return f"{job.status.value} {code}".strip()


def run(rt: Runtime, rerun: bool = False) -> dict:
    """The day's run. The day is claimed atomically (Codex audit, finding 12): a scheduler retry or a
    second call the same day returns that day's run instead of starting another paid one. `rerun`
    is an explicit extra run (its own claim and its own text)."""
    from app import notify
    from app.jobs import service

    s = rt.settings
    if not (s.canary_enabled and s.canary_uid and s.canary_email):
        return {"skipped": "off"}
    previous = history(rt)
    today = utcnow().date()
    todays = [j for j in previous if j.created_at.date() == today]
    run_number = len(todays) + 1 if rerun else 1
    claim = f"canary:{today.isoformat()}" + (f":{run_number}" if rerun else "")
    token = secrets.token_hex(8)
    if rt.store.claim_once(claim, token) != token:
        return {"skipped": "already run today", "job": todays[0].id if todays else None}
    if previous and (problem := _problem(previous[0])):
        notify.alert(rt, "Daily check: the last run did not finish cleanly", f"Job {previous[0].id}: {problem}.", key=f"canary:{previous[0].id}")
    if previous and previous[0].status in (JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.AWAITING_PAYMENT):
        return {"skipped": "previous run still open", "previous": previous[0].id}

    user = service.User(uid=s.canary_uid, email=s.canary_email, is_admin=False, verified=True)
    day = utcnow().strftime("%d %B %Y").lstrip("0")
    try:
        job_id = service.create_draft(rt, user).id
        service.upload_file(rt, user, job_id, "source", "daily-check.docx", paper(day, run_number))
        quoted = service.request_quote(rt, user, job_id, SELECTION)
        if quoted.quote is None:
            raise AppError("No price was given for the daily check.", code="NO_QUOTE")
        bound = rt.store.get(job_id)
        if bound is None or bound.quote is None or bound.quote.budget_usd > s.canary_budget_usd:
            raise AppError("The daily check would cost more than its budget.", code="OVER_BUDGET")
        service.submit(rt, user, job_id, quoted.quote.id)
    except AppError as exc:  # a run that cannot start is itself the alert
        notify.alert(rt, "Daily check could not start", f"{exc.code}: {exc.message}", key=f"canary-start:{claim}")
        log(logger, logging.ERROR, "canary not started", code=exc.code)
        return {"started": None, "error": exc.code}
    log(logger, logging.INFO, "canary started", job_id=job_id)
    return {"started": job_id}
