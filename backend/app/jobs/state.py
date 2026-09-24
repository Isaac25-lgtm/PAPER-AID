"""The only place job status changes are decided. Everything else asks `transition()`."""

from app.core.errors import Conflict
from app.jobs.models import Job, JobEvent, JobStatus, utcnow

S = JobStatus
ALLOWED: dict[JobStatus, set[JobStatus]] = {
    S.DRAFT: {S.QUOTED, S.CANCELLED},
    S.QUOTED: {S.DRAFT, S.QUOTED, S.AWAITING_PAYMENT, S.QUEUED, S.CANCELLED},
    S.AWAITING_PAYMENT: {S.QUEUED, S.CANCELLED},
    S.QUEUED: {S.PROCESSING, S.CANCELLED, S.FAILED},
    S.PROCESSING: {S.COMPLETED, S.FAILED},
    S.FAILED: {S.QUEUED},  # admin retry of a retryable failure only
    S.COMPLETED: set(),
    S.CANCELLED: set(),
}

TERMINAL = {S.COMPLETED, S.FAILED, S.CANCELLED}
ACTIVE = {S.AWAITING_PAYMENT, S.QUEUED, S.PROCESSING}
SUBMITTED = {S.AWAITING_PAYMENT, S.QUEUED, S.PROCESSING, S.COMPLETED, S.FAILED, S.CANCELLED}


def can_transition(current: JobStatus, target: JobStatus) -> bool:
    return target in ALLOWED[current]


def transition(job: Job, target: JobStatus, event: str | None = None) -> Job:
    if not can_transition(job.status, target):
        raise Conflict(f"A job that is {job.status.lower()} cannot become {target.lower()}.", code="ILLEGAL_TRANSITION")
    if target == S.FAILED and job.failure is None:
        raise Conflict("A job can only fail with a recorded reason.", code="ILLEGAL_TRANSITION")
    now = utcnow()
    job.status = target
    if target == S.QUEUED:
        job.queued_at = now
    if target == S.COMPLETED:
        if set(job.completed_stages) != set(job.pipeline):
            raise Conflict("A job cannot complete before every stage has run.", code="ILLEGAL_TRANSITION")
        job.completed_at = now
    if target in TERMINAL:
        job.stage = None
        job.lease_until = None
    job.events.append(JobEvent(at=now, label=event or target.capitalize()))
    return job
