"""Job business rules. Independent of FastAPI: every function takes the runtime and the verified
user, so ownership, pricing and state rules can be unit-tested directly."""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePosixPath
from typing import Literal

from app.core.config import Settings
from app.core.errors import AppError, Conflict, Forbidden, InvalidDocument, LimitExceeded, NotFound
from app.core.logging import log
from app.documents.intake import inspect_upload
from app.formatting.guideline import MAX_GUIDE_WORDS
from app.formatting.presets import PRESETS, PUBLIC_PRESETS
from app.jobs import state
from app.jobs.models import (
    AdminAction,
    AdminJob,
    AdminSummary,
    Billing,
    BoundQuote,
    EstimateRun,
    FileMeta,
    Job,
    JobEvent,
    JobStatus,
    JobView,
    Page,
    PaymentStatus,
    Quote,
    QuoteResponse,
    ServiceSelection,
    Stage,
    StoredFile,
    Wallet,
    WalletSummary,
    WalletView,
    utcnow,
)
from app.pricing import credits
from app.pricing.billing import hold_for_job, refund_job, release_hold
from app.pricing.quote import PRICING_VERSION, ai_cap_usd, estimate_scan_usd, needs_estimate, price, with_margin
from app.runtime import Runtime

logger = logging.getLogger("paperaid.jobs")

BUILT = ("AI_CHECK", "REFINE", "FORMAT", "TEMPLATE_FORMAT")
NEEDS_AI = ("AI_CHECK", "REFINE", "TEMPLATE_FORMAT")


def availability(settings: Settings) -> dict[str, str]:
    """"soon" = not built yet; "not_configured" = built, but the AI keys are not set."""
    result = {}
    for service in ("AI_CHECK", "REFINE", "FORMAT", "TEMPLATE_FORMAT", "REDRAFT", "LATEX"):
        if service not in BUILT:
            result[service] = "soon"
        elif service in NEEDS_AI and not settings.ai_configured:
            result[service] = "not_configured"
        else:
            result[service] = "available"
    return result
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass(frozen=True)
class User:
    uid: str
    email: str
    is_admin: bool
    verified: bool = True


def public_config(rt: Runtime) -> dict:
    return {
        "paymentsEnabled": rt.settings.payments_enabled,
        "availability": availability(rt.settings),
        "creditsEnabled": rt.settings.credits_enabled,
        "minTopUpUgx": rt.settings.min_top_up_ugx,
        "ugxPerUsd": rt.settings.ugx_per_usd,
        "retentionDays": rt.settings.retention_days,
        "presets": PUBLIC_PRESETS,
    }


def pipeline_for(selection: ServiceSelection) -> list[Stage]:
    stages = [Stage.EXTRACTING]
    if selection.writing != "NONE":
        stages.append(Stage.ANALYSING)
    if selection.writing == "REFINE":
        stages += [Stage.PLANNING, Stage.REFINING, Stage.AUDITING]
    if selection.formatting != "NONE":
        stages.append(Stage.FORMATTING)
    stages.append(Stage.EXPORTING)
    return stages


def _estimating(job: Job) -> bool:
    return job.estimate is not None and job.estimate.status == "RUNNING"


ESTIMATE_BUSY = "Your estimate is still running. Wait for it to finish (it takes a minute or two), then make changes."


def _owned(rt: Runtime, user: User, job_id: str) -> Job:
    job = rt.store.get(job_id) if _valid_id(job_id) else None
    if job is None or job.owner_uid != user.uid:
        raise NotFound("We couldn't find this job.")  # same answer whether it exists or belongs to someone else
    return job


def _valid_id(job_id: str) -> bool:
    return job_id.startswith("job_") and job_id[4:].isalnum() and len(job_id) <= 40


def _rate_limit(rt: Runtime, user: User, action: str, limit: int) -> None:
    if rt.store.hit(f"{user.uid}:{action}", 3600) > limit:
        log(logger, logging.WARNING, "rate limit hit", uid=user.uid, action=action)
        raise LimitExceeded("You've reached the limit for this action. Please try again in an hour.", code="RATE_LIMITED")


PAGE_SIZE = 500


def every_job(rt: Runtime, owner_uid: str | None, statuses: set[JobStatus] | None) -> list[Job]:
    """All matching jobs, following cursors page by page (maintenance must never stop at page one)."""
    jobs, cursor = rt.store.list(owner_uid, statuses, None, None, PAGE_SIZE)
    while cursor:
        page, cursor = rt.store.list(owner_uid, statuses, None, cursor, PAGE_SIZE)
        jobs.extend(page)
    return jobs


def task_name(job: Job, suffix: str = "") -> str:
    return f"{job.id}-g{job.generation}-s{len(job.completed_stages)}{suffix}"


# --- owner operations ------------------------------------------------------------------


def create_draft(rt: Runtime, user: User) -> JobView:
    if not user.verified:
        raise Forbidden("Verify your email address before starting a job. Check your inbox for the link.", code="EMAIL_NOT_VERIFIED")
    _rate_limit(rt, user, "draft", rt.settings.quotes_per_hour)
    now = utcnow()
    job = Job(
        id=f"job_{secrets.token_hex(6)}",
        status=JobStatus.DRAFT,
        owner_uid=user.uid,
        owner_email=user.email,
        created_at=now,
        expires_at=now + timedelta(days=rt.settings.retention_days),
        events=[JobEvent(at=now, label="Draft created")],
    )
    rt.store.create(job)
    return job.view()


FileRole = Literal["source", "guideline"]


def upload_file(rt: Runtime, user: User, job_id: str, role: FileRole, filename: str, data: bytes) -> FileMeta:
    """Attach the paper ("source") or the university formatting guide ("guideline") to a draft."""
    job = _owned(rt, user, job_id)
    if job.status not in (JobStatus.DRAFT, JobStatus.QUOTED):
        raise Conflict("This job has already been submitted. Start a new job to upload another file.")
    if _estimating(job):
        raise Conflict(ESTIMATE_BUSY, code="ESTIMATE_RUNNING")
    display_name = PurePosixPath(filename.replace("\\", "/")).name[:180] or role
    guide = role == "guideline"
    min_words = 20 if guide else 50  # guides can be short; papers cannot
    max_words = MAX_GUIDE_WORDS if guide else rt.settings.max_words
    try:
        model = inspect_upload(data, display_name, rt.settings.max_upload_bytes, max_words, rt.settings.max_pdf_pages, min_words=min_words)
    except InvalidDocument as exc:
        if guide and exc.code == "DOCUMENT_TOO_LONG":
            exc.message = f"We can't use this formatting guide. It is longer than {MAX_GUIDE_WORDS:,} words; upload only the section with the formatting rules."
        elif guide:
            exc.message = f"We can't use this formatting guide. {exc.message}"
        raise
    ext = "pdf" if model.format == "PDF" else "docx"
    digest = hashlib.sha256(data).hexdigest()
    # Every upload attempt gets its own immutable object (even for identical bytes), so a quote always
    # points at exactly what it priced and a replaced object can never become current again.
    path = f"{job.storage_prefix()}/input/{role}-{digest[:12]}-{secrets.token_hex(4)}.{ext}"
    rt.files.put(path, data, "application/pdf" if ext == "pdf" else DOCX_TYPE)
    stored = StoredFile(
        name=display_name,
        format=model.format,
        size_bytes=len(data),
        word_count=model.word_count,
        page_estimate=model.page_count or 1,
        heading_count=model.heading_count,
        path=path,
        sha256=digest,
    )
    previous: list[str] = []

    def attach(j: Job) -> Job | None:
        if j.status not in (JobStatus.DRAFT, JobStatus.QUOTED) or _estimating(j):
            return None  # submitted (or being estimated) meanwhile: the new file must not touch it
        current = j.source if role == "source" else j.guideline
        if current and current.path != path:
            previous.append(current.path)
        if role == "source":
            j.source = stored
        else:
            j.guideline = stored
        j.quote = None  # a new file always needs a new quote
        if j.status == JobStatus.QUOTED:
            state.transition(j, JobStatus.DRAFT, "File replaced; quote cleared")
        return j

    if rt.store.update(job.id, attach) is None:
        rt.files.delete(path)  # unique to this attempt and never attached: always safe to remove
        raise Conflict("This job was submitted before the new file arrived. Start a new job to use another file.", code="ALREADY_SUBMITTED")
    for old in previous:
        rt.files.delete(old)
    return FileMeta.model_validate(stored.model_dump())



def remove_guideline(rt: Runtime, user: User, job_id: str) -> None:
    """Detach the formatting guide from a draft. Idempotent; clears any quote that priced it."""
    job = _owned(rt, user, job_id)
    removed: list[str] = []

    def detach(j: Job) -> Job | None:
        if j.status not in (JobStatus.DRAFT, JobStatus.QUOTED) or _estimating(j):
            return None
        if j.guideline is None:
            return j
        removed.append(j.guideline.path)
        j.guideline = None
        j.quote = None
        if j.status == JobStatus.QUOTED:
            state.transition(j, JobStatus.DRAFT, "Guide removed; quote cleared")
        return j

    if job.status not in (JobStatus.DRAFT, JobStatus.QUOTED) or rt.store.update(job.id, detach) is None:
        raise Conflict("This job has already been submitted.", code="ALREADY_SUBMITTED")
    for path in removed:
        rt.files.delete(path)


def request_quote(rt: Runtime, user: User, job_id: str, selection: ServiceSelection, start_estimate: bool = False) -> QuoteResponse:
    """Price a selection. Refinement first needs a paid AI estimate: without `start_estimate` this
    only reports what the estimate can cost; with it, the estimate is started (the worker finishes
    it). Everything else is priced from length at once. Either way the student needs credits: no
    estimate without a balance (owner decision 2026-09-24)."""
    job = _owned(rt, user, job_id)
    if job.status not in (JobStatus.DRAFT, JobStatus.QUOTED):
        raise Conflict("This job has already been submitted.")
    if job.source is None:
        raise AppError("Upload your paper first.", code="NO_FILE")
    services = selection.services()
    if not services:
        raise AppError("Choose at least one service.", code="NO_SERVICE")
    offered = availability(rt.settings)
    if any(offered.get(s.value) != "available" for s in services):
        raise AppError("That service is not available right now.", code="SERVICE_UNAVAILABLE")
    if job.source.format == "PDF" and any(s.value != "AI_CHECK" for s in services):
        raise AppError("PDF files can use AI Check only. Upload the Word file to refine or format it.", code="PDF_AI_CHECK_ONLY")
    if selection.formatting == "TEMPLATE_FORMAT" and job.guideline is None:
        raise AppError("Upload your university's formatting guide to use University templates.", code="NO_GUIDELINE")
    guideline_sha = job.guideline.sha256 if selection.formatting == "TEMPLATE_FORMAT" and job.guideline else None
    if selection.formatting == "FORMAT" and selection.preset not in PRESETS:
        raise AppError("Choose an available formatting style.", code="INVALID_PRESET")
    if _estimating(job):
        if job.estimate and job.estimate.selection == selection:
            return QuoteResponse(estimate=job.estimate)
        raise Conflict(ESTIMATE_BUSY, code="ESTIMATE_RUNNING")
    now = utcnow()
    existing = job.quote
    if (
        existing
        and existing.selection == selection
        and existing.source_sha256 == job.source.sha256
        and existing.guideline_sha256 == guideline_sha
        and existing.expires_at > now + timedelta(minutes=2)
    ):
        return QuoteResponse(quote=Quote.model_validate(existing.model_dump()), estimate=job.estimate)
    wallet = rt.store.get_wallet(user.uid)
    available = wallet.available if wallet else 0
    if needs_estimate(selection):
        if not start_estimate:
            return QuoteResponse(estimate_fee_cap=_estimate_fee_cap(rt, job, selection), estimate=job.estimate)
        return _start_estimate(rt, user, job, selection, guideline_sha)
    if available <= 0 and rt.settings.credits_enabled:
        raise credits.InsufficientCredits(rt.settings.min_top_up_ugx, available)
    _rate_limit(rt, user, "quote", rt.settings.quotes_per_hour)
    settings = rt.settings
    priced = price(settings, selection, job.source.word_count, job.guideline.word_count if guideline_sha and job.guideline else 0)
    quote = BoundQuote(
        id=f"quote_{secrets.token_hex(6)}",
        lines=priced.lines,
        amount=sum(line.amount for line in priced.lines),
        pricing_version=PRICING_VERSION,
        expires_at=now + timedelta(minutes=settings.quote_ttl_minutes),
        selection=selection,
        source_sha256=job.source.sha256,
        guideline_sha256=guideline_sha,
        word_count=job.source.word_count,
        fixed_ugx=priced.fixed_ugx,
        ugx_per_usd=settings.ugx_per_usd,
        multiplier=settings.price_multiplier,
    )

    def save(j: Job) -> Job | None:
        if j.status not in (JobStatus.DRAFT, JobStatus.QUOTED) or j.source is None or j.source.sha256 != quote.source_sha256 or _estimating(j):
            return None
        if guideline_sha is not None and (j.guideline is None or j.guideline.sha256 != guideline_sha):
            return None
        j.quote = quote
        j.selection = selection
        j.billing = Billing()  # a length-priced job has no estimate to count toward it
        return state.transition(j, JobStatus.QUOTED, "Quote issued")

    if rt.store.update(job.id, save) is None:
        raise Conflict("Your files changed while we were pricing them. We'll price the new ones.", code="FILES_CHANGED")
    return QuoteResponse(quote=Quote.model_validate(quote.model_dump()))


def _estimate_fee_cap(rt: Runtime, job: Job, selection: ServiceSelection) -> int:
    assert job.source is not None
    return with_margin(estimate_scan_usd(rt.settings, job.source.word_count, selection.intensity), rt.settings)


def _start_estimate(rt: Runtime, user: User, job: Job, selection: ServiceSelection, guideline_sha: str | None) -> QuoteResponse:
    """Hold the most the scan can cost, then let the worker run it."""
    assert job.source is not None
    settings = rt.settings
    fee_cap = _estimate_fee_cap(rt, job, selection)
    _rate_limit(rt, user, "estimate", settings.quotes_per_hour)
    run = EstimateRun(
        id=f"est{secrets.token_hex(5)}",
        status="RUNNING",
        fee_cap=fee_cap,
        selection=selection,
        source_sha256=job.source.sha256,
        guideline_sha256=guideline_sha,
        budget_usd=ai_cap_usd(fee_cap, settings),
    )

    def start(j: Job, w: Wallet) -> tuple[Job, Wallet] | None:
        if j.status not in (JobStatus.DRAFT, JobStatus.QUOTED) or _estimating(j) or j.source is None or j.source.sha256 != run.source_sha256:
            return None
        if guideline_sha is not None and (j.guideline is None or j.guideline.sha256 != guideline_sha):
            return None
        if settings.credits_enabled:
            credits.hold(w, fee_cap, j.id, "AI estimate (the most it can cost)")
        run.held = settings.credits_enabled
        run.cost_base_usd = j.estimate_cost_usd
        j.estimate = run
        j.selection = selection
        j.quote = None
        j.billing = Billing()
        if j.status == JobStatus.QUOTED:
            state.transition(j, JobStatus.DRAFT, "New estimate requested; previous quote cleared")
        j.events.append(JobEvent(label=f"Estimate started (up to UGX {fee_cap:,} held)"))
        return j, w

    result = rt.store.update_job_and_wallet(job.id, start)
    if result is None:
        raise Conflict("Your files changed while we were pricing them. We'll price the new ones.", code="FILES_CHANGED")
    rt.queue.enqueue(job.id, f"{job.id}-e{run.id}")
    return QuoteResponse(estimate=run)


def submit(rt: Runtime, user: User, job_id: str, quote_id: str) -> JobView:
    job = _owned(rt, user, job_id)
    if job.status in state.SUBMITTED and job.quote and job.quote.id == quote_id:
        return job.view()  # double click or retried request: the same submission, nothing new
    if job.status != JobStatus.QUOTED or job.quote is None or job.quote.id != quote_id:
        raise Conflict("Your quote changed. Review the new price and submit again.", code="QUOTE_MISMATCH")
    if job.quote.expires_at < utcnow():
        raise Conflict("Your quote expired. Request a new one.", code="QUOTE_EXPIRED")
    if job.source is None or job.quote.source_sha256 != job.source.sha256:
        raise Conflict("Your file changed after it was priced. Request a new quote.", code="QUOTE_MISMATCH")
    if any(availability(rt.settings).get(service.value) != "available" for service in job.quote.selection.services()):
        raise AppError("That service is not available right now.", code="SERVICE_UNAVAILABLE")
    if rt.store.count_active(user.uid) >= rt.settings.max_active_jobs_per_user:
        raise LimitExceeded(
            f"You already have {rt.settings.max_active_jobs_per_user} jobs in progress. Submit this one when one of them finishes.",
            code="ACTIVE_JOB_LIMIT",
        )
    _rate_limit(rt, user, "submit", rt.settings.submits_per_hour)
    settings = rt.settings

    def accept(j: Job, w: Wallet) -> tuple[Job, Wallet] | None:
        # Re-checked inside the transaction: a concurrent upload or submit may have changed the job.
        if j.status != JobStatus.QUOTED or j.quote is None or j.quote.id != quote_id or j.source is None or j.quote.source_sha256 != j.source.sha256:
            return None
        if any(availability(settings).get(service.value) != "available" for service in j.quote.selection.services()):
            return None
        if j.quote.guideline_sha256 is not None and (j.guideline is None or j.guideline.sha256 != j.quote.guideline_sha256):
            return None
        q = j.quote
        j.services = q.selection.services()
        j.pipeline = pipeline_for(q.selection)
        # The provider-spend cap keeps the margin: the quote's AI part at its frozen rate and multiplier.
        j.budget_usd = max(0, q.amount - q.paid - q.fixed_ugx) / q.ugx_per_usd / q.multiplier if q.ugx_per_usd and q.multiplier else 0.0
        if settings.credits_enabled:
            held = hold_for_job(j, w)  # raises InsufficientCredits, which aborts the whole transaction
            state.transition(j, JobStatus.QUEUED, f"Queued (UGX {held:,} held)")
        else:
            j.payment_status = PaymentStatus.NOT_REQUIRED
            state.transition(j, JobStatus.QUEUED, "Queued (testing: not charged)")
        return j, w

    result = rt.store.update_job_and_wallet(job.id, accept)
    updated = result[0] if result else None
    if updated is None:
        current = _owned(rt, user, job_id)
        if current.status in state.SUBMITTED and current.quote and current.quote.id == quote_id:
            return current.view()  # a concurrent identical submit won; same result
        raise Conflict("Your quote changed. Review the new price and submit again.", code="QUOTE_MISMATCH")
    if updated.status == JobStatus.QUEUED:
        rt.queue.enqueue(updated.id, task_name(updated))
    log(logger, logging.INFO, "job submitted", jobId=updated.id, services=[s.value for s in updated.services], words=updated.source.word_count if updated.source else 0)
    return updated.view()


def get_job(rt: Runtime, user: User, job_id: str) -> JobView:
    return _owned(rt, user, job_id).view()


def list_jobs(rt: Runtime, user: User, status: str | None, service: str | None, cursor: str | None, limit: int) -> Page[JobView]:
    statuses = {JobStatus(status)} if status and status != "ALL" else state.SUBMITTED
    jobs, next_cursor = rt.store.list(user.uid, statuses, service if service and service != "ALL" else None, cursor, min(limit, 50))
    return Page[JobView](items=[j.view() for j in jobs], next_cursor=next_cursor)


def cancel(rt: Runtime, user: User, job_id: str, actor: str | None = None) -> JobView:
    job = _owned(rt, user, job_id) if actor is None else _require(rt, job_id)
    if job.status == JobStatus.CANCELLED:
        return job.view()
    if job.status not in (JobStatus.DRAFT, JobStatus.QUOTED, JobStatus.AWAITING_PAYMENT, JobStatus.QUEUED):
        raise Conflict("This job has already started, so it can't be cancelled.", code="CANNOT_CANCEL")
    if _estimating(job):
        raise Conflict(ESTIMATE_BUSY, code="ESTIMATE_RUNNING")

    def do_cancel(j: Job, w: Wallet) -> tuple[Job, Wallet] | None:
        if j.status not in (JobStatus.DRAFT, JobStatus.QUOTED, JobStatus.AWAITING_PAYMENT, JobStatus.QUEUED) or _estimating(j):
            return None
        if actor:
            j.admin_actions.append(AdminAction(actor=actor, action="Cancelled"))
            refund_job(j, w, "Cancelled by PaperAid, so nothing was charged")  # our decision: everything back
        else:
            release_hold(j, w, "You cancelled before the job started")  # a finished estimate stays paid
        state.transition(j, JobStatus.CANCELLED, "Cancelled by admin" if actor else "Cancelled by user")
        return j, w

    result = rt.store.update_job_and_wallet(job.id, do_cancel)
    if result is None:
        raise Conflict("This job has already started, so it can't be cancelled.", code="CANNOT_CANCEL")
    return result[0].view()


def delete(rt: Runtime, user: User, job_id: str) -> None:
    job = rt.store.get(job_id) if _valid_id(job_id) else None
    if job is None:
        return  # already gone: deletion is idempotent
    if job.owner_uid != user.uid:
        raise NotFound("We couldn't find this job.")
    if job.status in (JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.AWAITING_PAYMENT):
        raise Conflict("Cancel the job or wait for it to finish before deleting it.", code="JOB_ACTIVE")
    if _estimating(job):
        raise Conflict(ESTIMATE_BUSY, code="ESTIMATE_RUNNING")
    rt.files.delete_prefix(job.storage_prefix())
    rt.store.delete(job.id)
    log(logger, logging.INFO, "job deleted", jobId=job.id)


def output_file(rt: Runtime, user: User, job_id: str, output_id: str) -> tuple[str, str, str]:
    """Returns (storage path, download name, content type) for an owned, unexpired output."""
    job = _owned(rt, user, job_id)
    if job.expires_at < utcnow():
        raise AppError("These files were deleted under our retention policy.", code="FILES_EXPIRED", status=410)
    output = next((o for o in job.outputs if o.id == output_id), None)
    if output is None or not rt.files.exists(output.path):
        raise NotFound("That file is not available.")
    return output.path, output.name, output.content_type


def delete_account(rt: Runtime, user: User) -> int:
    """Delete every job and file the user owns. Refuses while a job is mid-processing."""
    jobs = every_job(rt, user.uid, None)
    if any(j.status in (JobStatus.QUEUED, JobStatus.PROCESSING) or _estimating(j) for j in jobs):
        raise Conflict("One of your jobs is being processed. Delete your account when it finishes.", code="JOB_ACTIVE")
    for job in jobs:
        rt.files.delete_prefix(job.storage_prefix())
        rt.store.delete(job.id)
    rt.store.delete_wallet(user.uid)
    log(logger, logging.WARNING, "account deleted", uid=user.uid, jobs=len(jobs))
    return len(jobs)


# --- credits ---------------------------------------------------------------------------------


def _wallet_view(rt: Runtime, wallet: Wallet) -> WalletView:
    return WalletView(
        available=wallet.available,
        held=wallet.held,
        entries=list(reversed(wallet.entries[-50:])),
        ugx_per_usd=rt.settings.ugx_per_usd,
        test_credits=rt.settings.env == "local",
    )


def my_wallet(rt: Runtime, user: User) -> WalletView:
    """The student's balance. Opening it records their email, so an admin can find them."""
    wallet = rt.store.update_wallet(user.uid, user.email, lambda w: w if w.email else w.model_copy(update={"email": user.email}))
    assert wallet is not None
    return _wallet_view(rt, wallet)


# --- admin operations ------------------------------------------------------------------


def admin_grant(rt: Runtime, admin: User, email: str, amount: int, note: str) -> WalletSummary:
    """Add credits by hand: test credits locally, refunds or goodwill in production. Payments will
    add credits through the aggregator instead."""
    term = email.strip().lower()
    match = next((w for w in rt.store.find_wallets(term, 5) if w.email.lower() == term), None)
    if match is None:
        raise NotFound("No PaperAid account with that email has opened its credits yet. Ask them to sign in once, then try again.")
    default_note = "Test credits added by an admin" if rt.settings.env == "local" else "Credits added by PaperAid"
    wallet = rt.store.update_wallet(match.uid, match.email, lambda w: credits.top_up(w, amount, (note.strip() or default_note)[:120]))
    assert wallet is not None
    log(logger, logging.WARNING, "credits granted", actor=admin.email, amount=amount, uid=wallet.uid)
    return WalletSummary(email=wallet.email, available=wallet.available, held=wallet.held, updated_at=wallet.updated_at)


def admin_wallets(rt: Runtime, search: str | None) -> list[WalletSummary]:
    return [WalletSummary(email=w.email, available=w.available, held=w.held, updated_at=w.updated_at) for w in rt.store.find_wallets(search, 50)]




def _require(rt: Runtime, job_id: str) -> Job:
    job = rt.store.get(job_id) if _valid_id(job_id) else None
    if job is None:
        raise NotFound("Job not found.")
    return job


def _admin_view(job: Job) -> AdminJob:
    duration = int((job.completed_at - job.created_at).total_seconds()) if job.completed_at else None
    return AdminJob(
        job=job.view(),
        owner_email=job.owner_email,
        cost_usd=round(job.cost_usd, 6),
        duration_sec=duration,
        model_calls=job.model_calls,
        events=job.events,
        admin_actions=job.admin_actions,
        failure_detail=job.failure_detail,
    )


def admin_summary(rt: Runtime) -> AdminSummary:
    jobs = every_job(rt, None, state.SUBMITTED)
    day_ago = utcnow() - timedelta(days=1)
    recent = [j for j in jobs if j.created_at > day_ago]
    finished = [j for j in jobs if j.status in (JobStatus.COMPLETED, JobStatus.FAILED)]
    return AdminSummary(
        jobs24h=len(recent),
        active=sum(1 for j in jobs if j.status == JobStatus.PROCESSING),
        queued=sum(1 for j in jobs if j.status == JobStatus.QUEUED),
        completion_rate=(sum(1 for j in finished if j.status == JobStatus.COMPLETED) / len(finished)) if finished else 1.0,
        failures24h=sum(1 for j in recent if j.status == JobStatus.FAILED),
        spend24h_usd=round(sum(j.cost_usd for j in recent), 4),
        processing_enabled=processing_enabled(rt),
    )


def admin_list(rt: Runtime, status: str | None, service: str | None, search: str | None, cursor: str | None, limit: int) -> Page[AdminJob]:
    if search:
        term = search.strip().lower()
        if _valid_id(term):
            job = rt.store.get(term)
            return Page[AdminJob](items=[_admin_view(job)] if job else [])
        jobs = every_job(rt, None, state.SUBMITTED)
        matches = [j for j in jobs if term in j.owner_email.lower() or (j.source and term in j.source.name.lower())]
        return Page[AdminJob](items=[_admin_view(j) for j in matches[:limit]])
    statuses = {JobStatus(status)} if status and status != "ALL" else state.SUBMITTED
    jobs, next_cursor = rt.store.list(None, statuses, service if service and service != "ALL" else None, cursor, min(limit, 50))
    return Page[AdminJob](items=[_admin_view(j) for j in jobs], next_cursor=next_cursor)


def admin_get(rt: Runtime, job_id: str) -> AdminJob:
    return _admin_view(_require(rt, job_id))


def admin_retry(rt: Runtime, admin: User, job_id: str) -> AdminJob:
    job = _require(rt, job_id)
    if job.status != JobStatus.FAILED or not (job.failure and job.failure.retryable):
        raise Conflict("Only retryable failures can be retried.", code="NOT_RETRYABLE")

    def retry(j: Job, w: Wallet) -> tuple[Job, Wallet] | None:
        if j.status != JobStatus.FAILED:
            return None
        if j.billing.state != "NONE":  # a charged job's failure returned everything, so the retry needs its own hold
            hold_for_job(j, w)
        j.generation += 1
        j.attempts = 0
        j.failure = None
        j.failure_detail = None
        j.admin_actions.append(AdminAction(actor=admin.email, action="Retried"))
        state.transition(j, JobStatus.QUEUED, "Retried by admin — resumes from last completed stage")
        return j, w

    result = rt.store.update_job_and_wallet(job.id, retry)
    updated = result[0] if result else None
    if updated is None:
        return admin_get(rt, job_id)
    rt.queue.enqueue(updated.id, task_name(updated))
    return _admin_view(updated)


def set_processing_enabled(rt: Runtime, admin: User, enabled: bool) -> bool:
    rt.store.set_flag("processing_enabled", enabled)
    log(logger, logging.WARNING, "processing switch changed", enabled=enabled, actor=admin.email)
    return enabled


def processing_enabled(rt: Runtime) -> bool:
    return rt.store.get_flag("processing_enabled", rt.settings.processing_enabled)


# --- maintenance --------------------------------------------------------------------------


def reconcile(rt: Runtime) -> int:
    """Re-enqueue jobs that should be running but have no live worker (lost task, restart)."""
    now = utcnow()
    jobs = every_job(rt, None, {JobStatus.QUEUED, JobStatus.PROCESSING})
    stuck = [j for j in jobs if j.lease_until is None or j.lease_until < now]
    for job in stuck:
        rt.queue.enqueue(job.id, task_name(job, f"-r{int(now.timestamp()) // 300}"))
    estimates = [j for j in every_job(rt, None, {JobStatus.DRAFT}) if _estimating(j) and j.estimate and (j.estimate.lease_until is None or j.estimate.lease_until < now)]
    for job in estimates:
        rt.queue.enqueue(job.id, f"{job.id}-e{job.estimate.id}-r{int(now.timestamp()) // 300}" if job.estimate else job.id)
    return len(stuck) + len(estimates)


def cleanup_expired(rt: Runtime) -> int:
    """Delete files of jobs past retention. The job record stays so history shows 'files expired'."""
    now = utcnow()
    jobs = every_job(rt, None, {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED})
    expired = [j for j in jobs if j.expires_at < now and not j.files_deleted]
    for job in expired:
        rt.files.delete_prefix(job.storage_prefix())

        def strip_files(j: Job) -> Job:
            j.files_deleted = True
            j.events.append(JobEvent(label="Files deleted under retention policy"))
            return j

        rt.store.update(job.id, strip_files)
    return len(expired)


def ensure_valid_upload_name(filename: str) -> None:
    if not filename or len(filename) > 255:
        raise InvalidDocument("That file name isn't valid.", code="INVALID_NAME")
