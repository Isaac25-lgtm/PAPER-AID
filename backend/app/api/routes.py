"""HTTP routes. Deliberately thin: parse input, call app.jobs.service, return its result."""

from typing import Literal

from fastapi import APIRouter, Body, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import Field

from app.api.public import student_json
from app.core.auth import current_user, optional_user, require_admin
from app.core.errors import AppError, Forbidden
from app.jobs import service, workspace
from app.jobs.models import (
    AdminJob,
    AdminSummary,
    Camel,
    FileMeta,
    ImageMeta,
    JobView,
    Page,
    QuoteResponse,
    ServiceSelection,
    Wallet,
    WalletSummary,
    WalletView,
)
from app.jobs.pipeline import run_step
from app.jobs.service import User
from app.runtime import Runtime, get_runtime

api = APIRouter(prefix="/api")
tasks = APIRouter(prefix="/tasks", include_in_schema=False)


@api.get("/health")
def health() -> dict:
    return {"status": "ok"}


@api.get("/ready")
def ready(rt: Runtime = Depends(get_runtime)) -> dict:
    rt.store.get_flag("processing_enabled", True)  # proves the store is reachable; never calls an AI provider
    return {"status": "ready", "processingEnabled": service.processing_enabled(rt)}


@api.get("/config")
def config(rt: Runtime = Depends(get_runtime), user: User | None = Depends(optional_user)) -> dict:
    return service.public_config(rt, user)


@api.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"uid": user.uid, "email": user.email, "isAdmin": user.is_admin}


class NotificationChoice(Camel):
    notify_email: bool | None = None
    notify_sms: bool | None = None
    phone: str | None = Field(default=None, max_length=20)


def _notifications(rt: Runtime, user: User) -> dict:
    from app import notify

    wallet = rt.store.get_wallet(user.uid)
    return {"available": notify.channels(rt), "notifyEmail": wallet.notify_email if wallet else True, "notifySms": wallet.notify_sms if wallet else False,
            "phone": wallet.phone if wallet else ""}


class TermsAcceptance(Camel):
    version: str = Field(max_length=40)


@api.post("/me/terms", status_code=204)
def accept_terms(body: TermsAcceptance, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    """The person accepted the current terms (at sign-up, or when asked again): recorded with the time."""
    service.accept_terms(rt, user, body.version)
    return Response(status_code=204)


@api.get("/me/notifications")
def get_notifications(user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> dict:
    """"Your work is ready" messages (owner roadmap 2026-10-03): which channels exist and the person's choices."""
    return _notifications(rt, user)


@api.post("/me/notifications")
def set_notifications(body: NotificationChoice, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> dict:
    import re

    phone = None if body.phone is None else re.sub(r"[\s-]", "", body.phone)
    if phone and not re.fullmatch(r"\+\d{9,15}", phone):
        raise AppError("Enter the phone number with its country code, for example +256 7XX XXX XXX.", code="INVALID_PHONE")
    if body.notify_sms and not (phone or (rt.store.get_wallet(user.uid) or Wallet(uid=user.uid, email=user.email)).phone):
        raise AppError("Add a phone number for text messages first.", code="NO_PHONE")

    def apply(w: Wallet) -> Wallet:
        if w.closing:
            return w
        if body.notify_email is not None:
            w.notify_email = body.notify_email
        if phone is not None:
            w.phone = phone
            if not phone:
                w.notify_sms = False  # no number, no texts
        if body.notify_sms is not None:
            w.notify_sms = body.notify_sms and bool(w.phone)
        return w

    rt.store.update_wallet(user.uid, user.email, apply)
    return _notifications(rt, user)


@api.delete("/me", status_code=204)
def delete_me(user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    service.delete_account(rt, user)
    if rt.settings.auth_mode == "firebase":
        from firebase_admin import auth

        auth.delete_user(user.uid)
    return Response(status_code=204)


@api.post("/jobs", response_model=JobView)
def create_job(user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return student_json(rt, service.create_draft(rt, user))


@api.post("/jobs/{job_id}/files/logo", response_model=ImageMeta)
def upload_logo(job_id: str, file: UploadFile = File(...), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> ImageMeta:
    data = file.file.read(service.MAX_LOGO_BYTES + 1)
    return service.upload_logo(rt, user, job_id, file.filename or "logo", data)


@api.post("/jobs/{job_id}/files/{role}", response_model=FileMeta)
def upload(job_id: str, role: str, file: UploadFile = File(...), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> FileMeta:
    # Plain (threadpool) routes: parsing a paper must not block the event loop (Codex audit 56c4f83 M21).
    if role not in ("source", "guideline"):
        raise AppError("Unknown file type.", code="NOT_FOUND", status=404)
    service.ensure_valid_upload_name(file.filename or "")
    data = file.file.read(rt.settings.max_upload_bytes + 1)
    return service.upload_file(rt, user, job_id, role, file.filename or role, data)  # type: ignore[arg-type]


@api.delete("/jobs/{job_id}/files/logo", status_code=204)
def remove_logo(job_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> None:
    service.remove_logo(rt, user, job_id)


@api.delete("/jobs/{job_id}/files/guideline", status_code=204)
def remove_guideline(job_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> None:
    service.remove_guideline(rt, user, job_id)


@api.post("/jobs/{job_id}/quote", response_model=QuoteResponse)
def quote(
    job_id: str,
    selection: ServiceSelection = Body(..., embed=True),
    start_estimate: bool = Body(False, embed=True, alias="startEstimate"),
    user: User = Depends(current_user),
    rt: Runtime = Depends(get_runtime),
) -> QuoteResponse:
    return service.request_quote(rt, user, job_id, selection, start_estimate)


@api.get("/wallet/history", response_model=service.LedgerPage)
def wallet_history(before: str | None = Query(None, max_length=80), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> service.LedgerPage:
    return service.wallet_history(rt, user, before)


@api.get("/wallet", response_model=WalletView)
def wallet(user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WalletView:
    return service.my_wallet(rt, user)


@api.post("/jobs/{job_id}/submit", response_model=JobView)
def submit(job_id: str, quote_id: str = Body(..., embed=True, alias="quoteId"), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return student_json(rt, service.submit(rt, user, job_id, quote_id))


@api.get("/jobs", response_model=Page[JobView])
def list_jobs(
    status: str | None = None,
    service_id: str | None = Query(None, alias="service"),
    cursor: str | None = None,
    limit: int = 10,
    user: User = Depends(current_user),
    rt: Runtime = Depends(get_runtime),
) -> Response:
    return student_json(rt, service.list_jobs(rt, user, status, service_id, cursor, limit))


@api.get("/jobs/{job_id}", response_model=JobView)
def get_job(job_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return student_json(rt, service.get_job(rt, user, job_id))


@api.post("/jobs/{job_id}/cancel", response_model=JobView)
def cancel(job_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return student_json(rt, service.cancel(rt, user, job_id))


@api.delete("/jobs/{job_id}", status_code=204)
def delete(job_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    service.delete(rt, user, job_id)
    return Response(status_code=204)


@api.get("/jobs/{job_id}/outputs/{output_id}")
def download(job_id: str, output_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    """Locally the file is streamed. In production the API returns a 10-minute signed link as JSON
    and the browser navigates to it directly — a navigation needs no CORS, unlike fetch()."""
    path, name, content_type = service.output_file(rt, user, job_id, output_id)
    local = rt.files.local_path(path)
    if local is not None:
        return FileResponse(local, media_type=content_type, filename=name, headers={"Cache-Control": "no-store"})
    url = rt.files.signed_url(path, name)
    if url is None:
        raise AppError("That file is not available.", code="NOT_FOUND", status=404)
    return JSONResponse({"url": url}, headers={"Cache-Control": "no-store"})


# --- the review workspace ----------------------------------------------------------------


@api.get("/jobs/{job_id}/document")
def job_document(job_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return JSONResponse(workspace.document(rt, user, job_id), headers={"Cache-Control": "no-store"})


@api.post("/jobs/{job_id}/findings/{finding_id}", response_model=JobView)
def job_finding(job_id: str, finding_id: str, dismissed: bool = Body(..., embed=True), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return student_json(rt, workspace.set_finding(rt, user, job_id, finding_id, dismissed))


@api.post("/jobs/{job_id}/changes/{change_id}", response_model=JobView)
def job_change(job_id: str, change_id: str, accepted: bool = Body(..., embed=True), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return student_json(rt, workspace.set_change(rt, user, job_id, change_id, accepted))


@api.post("/jobs/{job_id}/rebuild", response_model=JobView)
def job_rebuild(job_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return student_json(rt, workspace.rebuild(rt, user, job_id))


class ContinueRequest(Camel):
    origin: Literal["original", "result"] = "original"
    instruction: str = Field(default="", max_length=2000)
    blocks: list[str] = Field(default=[], max_length=3000)


@api.post("/jobs/{job_id}/continue", response_model=JobView)
def continue_job(job_id: str, body: ContinueRequest, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    return student_json(rt, workspace.continue_from(rt, user, job_id, body.origin, body.instruction, body.blocks))


@api.post("/jobs/{job_id}/fix", response_model=JobView)
def job_fix(
    job_id: str,
    finding_ids: list[str] = Body(default=[], embed=True, alias="findingIds", max_length=500),
    safe_only: bool = Body(default=False, embed=True, alias="safeOnly"),
    user: User = Depends(current_user),
    rt: Runtime = Depends(get_runtime),
) -> Response:
    return student_json(rt, workspace.fix_draft(rt, user, job_id, finding_ids, safe_only))


# --- admin -------------------------------------------------------------------------------


@api.get("/admin/summary", response_model=AdminSummary)
def admin_summary(_: User = Depends(require_admin), rt: Runtime = Depends(get_runtime)) -> AdminSummary:
    return service.admin_summary(rt)


@api.get("/admin/reliability")
def admin_reliability(days: int = Query(30, ge=1, le=365), _: User = Depends(require_admin), rt: Runtime = Depends(get_runtime)) -> Response:
    """Completion, stops, time and money per service (owner roadmap 2026-10-03): numbers and codes only."""
    from app.jobs import reliability

    return JSONResponse(reliability.report(rt, days).model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})


@api.get("/admin/jobs", response_model=Page[AdminJob])
def admin_jobs(
    status: str | None = None,
    service_id: str | None = Query(None, alias="service"),
    search: str | None = None,
    cursor: str | None = None,
    limit: int = 12,
    _: User = Depends(require_admin),
    rt: Runtime = Depends(get_runtime),
) -> Page[AdminJob]:
    return service.admin_list(rt, status, service_id, search, cursor, limit)


@api.get("/admin/jobs/{job_id}", response_model=AdminJob)
def admin_job(job_id: str, _: User = Depends(require_admin), rt: Runtime = Depends(get_runtime)) -> AdminJob:
    return service.admin_get(rt, job_id)


@api.post("/admin/jobs/{job_id}/retry", response_model=AdminJob)
def admin_retry(job_id: str, admin: User = Depends(require_admin), rt: Runtime = Depends(get_runtime)) -> AdminJob:
    return service.admin_retry(rt, admin, job_id)


@api.post("/admin/jobs/{job_id}/cancel", response_model=AdminJob)
def admin_cancel(job_id: str, admin: User = Depends(require_admin), rt: Runtime = Depends(get_runtime)) -> AdminJob:
    service.cancel(rt, admin, job_id, actor=admin.email)
    return service.admin_get(rt, job_id)


@api.get("/admin/wallets", response_model=list[WalletSummary])
def admin_wallets(search: str | None = None, _: User = Depends(require_admin), rt: Runtime = Depends(get_runtime)) -> list[WalletSummary]:
    return service.admin_wallets(rt, search)


@api.post("/admin/credits", response_model=WalletSummary)
def admin_credits(
    email: str = Body(..., embed=True),
    amount: int = Body(..., embed=True),
    note: str = Body("", embed=True),
    op_id: str = Body(..., embed=True, alias="opId", min_length=8, max_length=64),
    admin: User = Depends(require_admin),
    rt: Runtime = Depends(get_runtime),
) -> WalletSummary:
    return service.admin_grant(rt, admin, email, amount, note, op_id)


@api.post("/admin/processing")
def admin_processing(enabled: bool = Body(..., embed=True), admin: User = Depends(require_admin), rt: Runtime = Depends(get_runtime)) -> dict:
    return {"processingEnabled": service.set_processing_enabled(rt, admin, enabled)}


# --- internal worker endpoints (Cloud Tasks / Cloud Scheduler only) ----------------------


def _require_task_caller(request: Request, rt: Runtime = Depends(get_runtime)) -> None:
    """Cloud Run IAM already limits the worker to the task invoker account. This verifies the
    same Google-signed OIDC token again in code, so a misconfigured deployment still refuses
    anyone else. Headers alone prove nothing and are not trusted."""
    settings = rt.settings
    if settings.env != "production":
        return
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise Forbidden("Internal endpoint.")
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_oauth2_token(header[7:], GoogleRequest(), audience=settings.worker_url)
    except ValueError as exc:
        raise Forbidden("Internal endpoint.") from exc
    if claims.get("email") != settings.tasks_invoker_email or not claims.get("email_verified"):
        raise Forbidden("Internal endpoint.")


@tasks.post("/run-step", dependencies=[Depends(_require_task_caller)])
def task_run_step(job_id: str = Body(..., embed=True, alias="jobId"), rt: Runtime = Depends(get_runtime)) -> dict:
    run_step(rt, job_id)
    return {"ok": True}  # always 200: our own retry policy re-enqueues, so Cloud Tasks never retries on top


@tasks.post("/reconcile", dependencies=[Depends(_require_task_caller)])
def task_reconcile(rt: Runtime = Depends(get_runtime)) -> dict:
    from app import notify

    return {"requeued": service.reconcile(rt), "messages": notify.sweep(rt)}


@tasks.post("/canary", dependencies=[Depends(_require_task_caller)])
def task_canary(rerun: bool = Query(False), rt: Runtime = Depends(get_runtime)) -> dict:
    """The scheduler's daily call; `?rerun=true` is a deliberate extra run (never a scheduler retry)."""
    from app.jobs import canary

    return canary.run(rt, rerun)


@tasks.post("/cleanup", dependencies=[Depends(_require_task_caller)])
def task_cleanup(rt: Runtime = Depends(get_runtime)) -> dict:
    return {
        "expired": service.cleanup_expired(rt),
        "projectsExpired": service.cleanup_expired_projects(rt),
        "worksExpired": service.cleanup_expired_works(rt),
        "datalabExpired": service.cleanup_expired_datalab(rt),
        "datalabOrphans": service.sweep_datalab_files(rt),
        "projectsMigrated": service.migrate_legacy_project_files(rt),
        "ledgersBackfilled": service.backfill_ledgers(rt),
    }
