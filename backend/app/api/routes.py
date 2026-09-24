"""HTTP routes. Deliberately thin: parse input, call app.jobs.service, return its result."""

from fastapi import APIRouter, Body, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from app.core.auth import current_user, require_admin
from app.core.errors import AppError, Forbidden
from app.jobs import service
from app.jobs.models import AdminJob, AdminSummary, FileMeta, JobView, Page, QuoteResponse, ServiceSelection, WalletSummary, WalletView
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
def config(rt: Runtime = Depends(get_runtime)) -> dict:
    return service.public_config(rt)


@api.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"uid": user.uid, "email": user.email, "isAdmin": user.is_admin}


@api.delete("/me", status_code=204)
def delete_me(user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> Response:
    service.delete_account(rt, user)
    if rt.settings.auth_mode == "firebase":
        from firebase_admin import auth

        auth.delete_user(user.uid)
    return Response(status_code=204)


@api.post("/jobs", response_model=JobView)
def create_job(user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> JobView:
    return service.create_draft(rt, user)


@api.post("/jobs/{job_id}/files/{role}", response_model=FileMeta)
async def upload(job_id: str, role: str, file: UploadFile = File(...), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> FileMeta:
    if role not in ("source", "guideline"):
        raise AppError("Unknown file type.", code="NOT_FOUND", status=404)
    service.ensure_valid_upload_name(file.filename or "")
    data = await file.read(rt.settings.max_upload_bytes + 1)
    return service.upload_file(rt, user, job_id, role, file.filename or role, data)  # type: ignore[arg-type]


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


@api.get("/wallet", response_model=WalletView)
def wallet(user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> WalletView:
    return service.my_wallet(rt, user)


@api.post("/jobs/{job_id}/submit", response_model=JobView)
def submit(job_id: str, quote_id: str = Body(..., embed=True, alias="quoteId"), user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> JobView:
    return service.submit(rt, user, job_id, quote_id)


@api.get("/jobs", response_model=Page[JobView])
def list_jobs(
    status: str | None = None,
    service_id: str | None = Query(None, alias="service"),
    cursor: str | None = None,
    limit: int = 10,
    user: User = Depends(current_user),
    rt: Runtime = Depends(get_runtime),
) -> Page[JobView]:
    return service.list_jobs(rt, user, status, service_id, cursor, limit)


@api.get("/jobs/{job_id}", response_model=JobView)
def get_job(job_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> JobView:
    return service.get_job(rt, user, job_id)


@api.post("/jobs/{job_id}/cancel", response_model=JobView)
def cancel(job_id: str, user: User = Depends(current_user), rt: Runtime = Depends(get_runtime)) -> JobView:
    return service.cancel(rt, user, job_id)


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


# --- admin -------------------------------------------------------------------------------


@api.get("/admin/summary", response_model=AdminSummary)
def admin_summary(_: User = Depends(require_admin), rt: Runtime = Depends(get_runtime)) -> AdminSummary:
    return service.admin_summary(rt)


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
    admin: User = Depends(require_admin),
    rt: Runtime = Depends(get_runtime),
) -> WalletSummary:
    return service.admin_grant(rt, admin, email, amount, note)


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
    return {"requeued": service.reconcile(rt)}


@tasks.post("/cleanup", dependencies=[Depends(_require_task_caller)])
def task_cleanup(rt: Runtime = Depends(get_runtime)) -> dict:
    return {"expired": service.cleanup_expired(rt)}
