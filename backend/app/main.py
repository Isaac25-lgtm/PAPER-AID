import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import api, tasks
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import log, request_id, setup_logging
from app.jobs import service
from app.runtime import get_runtime

logger = logging.getLogger("paperaid.http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = get_runtime()
    if runtime.settings.queue_backend == "local":
        requeued = service.reconcile(runtime)  # resume jobs interrupted by a restart
        log(logger, logging.INFO, "local worker ready", requeued=requeued, concurrency=runtime.settings.queue_concurrency)
    yield


def resolve_role(env: str, role: str | None) -> str:
    """Which routes this process serves. Production must say explicitly: the public API must never
    expose worker endpoints, and the worker must never expose the public API."""
    if env == "production":
        if role not in ("api", "worker"):
            raise RuntimeError("SERVICE_ROLE must be 'api' or 'worker' in production.")
        return role
    return role or "all"


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    role = resolve_role(settings.env, os.environ.get("SERVICE_ROLE"))
    app = FastAPI(title="PaperAid API", version="0.1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Firebase-AppCheck"],
    )
    if role in ("api", "all"):
        app.include_router(api)
    if role in ("worker", "all"):
        app.include_router(tasks)

    def error_body(code: str, message: str) -> dict:
        return {"code": code, "message": message, "requestId": request_id.get()}

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(error_body("INVALID_REQUEST", "Some of the information sent was not valid."), status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error")
        return JSONResponse(error_body("INTERNAL", "Something went wrong on our side. Please try again."), status_code=500)

    @app.middleware("http")
    async def correlate(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request_id.set(rid)
        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        if not request.url.path.endswith(("/health", "/ready")):
            log(logger, logging.INFO, "request", method=request.method, path=request.url.path, status=response.status_code, durationMs=int((time.monotonic() - started) * 1000))
        return response

    return app


app = create_app()
