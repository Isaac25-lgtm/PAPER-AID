"""The private reliability view (owner roadmap, 2026-10-03): for each service, how often jobs finish,
where they stop, how long they take, and what they cost against what was charged. Admins only.
Built from job records alone: IDs, codes and numbers, never paper text, titles or file names."""

import statistics
from collections import Counter, defaultdict
from datetime import timedelta

from app.jobs.models import Camel, Job, JobStatus, utcnow
from app.runtime import Runtime


class StopCount(Camel):
    code: str
    stage: str
    count: int


class ServiceReliability(Camel):
    service: str
    jobs: int
    completed: int
    partial: int
    failed: int
    cancelled: int
    running: int
    completion_rate: float | None  # completed of finished (completed + failed); None with nothing finished
    stops: list[StopCount]
    median_minutes: float | None
    slowest_tenth_minutes: float | None  # the 90th percentile of completed jobs' time to finish
    cost_usd: float
    charged_credits: float
    refunded_credits: float
    margin_credits: float  # charged minus AI cost, at each quote's frozen rate
    admin_retries: int


class JobLine(Camel):
    id: str
    service: str
    status: str
    outcome: str | None
    failure: str | None
    stage: str | None
    minutes: float | None
    cost_usd: float
    charged_credits: float
    created_at: str


class Reliability(Camel):
    days: int
    services: list[ServiceReliability]
    jobs: list[JobLine]
    canary_enabled: bool
    canary: list[JobLine]  # the daily check's runs in the period, kept out of the figures above


def service_of(job: Job) -> str:
    """One name per kind of job, as admins read it."""
    s = job.selection
    if s.datalab != "NONE":
        return "Data Lab report"
    if s.work != "NONE":
        kind = {"COURSEWORK": "Coursework", "CONCEPT_NOTE": "Concept note", "FUNDING_PROPOSAL": "Funding proposal"}.get(s.work_kind, s.work_kind)
        return f"{kind}: {s.work.lower()}"
    if s.proposal != "NONE":
        return "Proposal review" if s.proposal == "REVIEW" else f"Proposal: {s.proposal.lower().replace('_', ' ')}"
    parts = [s.writing.replace("_", " ").title()] if s.writing != "NONE" else []
    if s.formatting != "NONE":
        parts.append("Formatting" if s.formatting == "FORMAT" else "University template")
    if s.latex:
        parts.append("LaTeX")
    return "Paper Check: " + " + ".join(parts) if parts else "Other"


def _stage(job: Job) -> str:
    detail = job.failure_detail or ""
    return detail.split()[0].removeprefix("stage=") if detail.startswith("stage=") else (job.stage.value if job.stage else "")


def _minutes(job: Job) -> float | None:
    if job.completed_at is None:
        return None
    return round((job.completed_at - job.created_at).total_seconds() / 60, 1)


def report(rt: Runtime, days: int) -> Reliability:
    from app.jobs.service import every_job  # the job service imports this module's callers

    since = utcnow() - timedelta(days=days)
    submitted = [j for j in every_job(rt, None, None) if j.created_at >= since and j.status not in (JobStatus.DRAFT, JobStatus.QUOTED)]
    canary_uid = rt.settings.canary_uid
    jobs = [j for j in submitted if not canary_uid or j.owner_uid != canary_uid]
    canary = sorted((j for j in submitted if canary_uid and j.owner_uid == canary_uid), key=lambda j: j.created_at, reverse=True)
    per = rt.settings.ugx_per_token
    grouped: dict[str, list[Job]] = defaultdict(list)
    for job in jobs:
        grouped[service_of(job)].append(job)
    services = []
    for name, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        completed = [j for j in items if j.status == JobStatus.COMPLETED]
        failed = [j for j in items if j.status == JobStatus.FAILED]
        stops = Counter((j.failure.code if j.failure else "UNKNOWN", _stage(j)) for j in failed)
        durations = sorted(m for j in completed if (m := _minutes(j)) is not None)
        cost = sum(j.cost_usd for j in items)
        charged = sum(j.billing.charged + j.billing.fee_paid for j in items)
        cost_ugx = sum(j.cost_usd * (j.quote.ugx_per_usd if j.quote and j.quote.ugx_per_usd else rt.settings.ugx_per_usd) for j in items)
        finished = len(completed) + len(failed)
        services.append(ServiceReliability(
            service=name, jobs=len(items), completed=len(completed), partial=sum(1 for j in completed if j.outcome == "PARTIAL"), failed=len(failed),
            cancelled=sum(1 for j in items if j.status == JobStatus.CANCELLED), running=sum(1 for j in items if j.status in (JobStatus.QUEUED, JobStatus.PROCESSING)),
            completion_rate=round(len(completed) / finished, 3) if finished else None,
            stops=[StopCount(code=c, stage=s, count=n) for (c, s), n in stops.most_common(8)],
            median_minutes=round(statistics.median(durations), 1) if durations else None,
            slowest_tenth_minutes=round(durations[min(len(durations) - 1, int(0.9 * len(durations)))], 1) if durations else None,
            cost_usd=round(cost, 3), charged_credits=round(charged / per, 1), refunded_credits=round(sum(j.billing.refunded for j in items) / per, 1),
            margin_credits=round((charged - cost_ugx) / per, 1), admin_retries=sum(1 for j in items for a in j.admin_actions if a.action == "Retried"),
        ))
    def line(j: Job) -> JobLine:
        return JobLine(id=j.id, service=service_of(j), status=j.status.value, outcome=j.outcome, failure=j.failure.code if j.failure else None, stage=_stage(j) or None,
                       minutes=_minutes(j), cost_usd=round(j.cost_usd, 3), charged_credits=round((j.billing.charged + j.billing.fee_paid) / per, 1), created_at=j.created_at.isoformat())

    lines = [line(j) for j in sorted(jobs, key=lambda j: j.created_at, reverse=True)[:100]]
    return Reliability(days=days, services=services, jobs=lines, canary_enabled=rt.settings.canary_enabled, canary=[line(j) for j in canary[:60]])
