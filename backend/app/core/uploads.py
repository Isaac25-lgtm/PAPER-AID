"""Bound HTTP bodies before form parsing; authenticate protected multipart uploads first."""

import asyncio

from starlette.concurrency import run_in_threadpool
from starlette.formparsers import MultiPartException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.auth import current_user
from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import request_id

MULTIPART_OVERHEAD = 1024 * 1024


class UploadGuard:
    def __init__(self, app: ASGIApp, settings: Settings):
        self.app, self.settings = app, settings
        self.slots = asyncio.Semaphore(settings.upload_concurrency)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        multipart = request.headers.get("content-type", "").lower().startswith("multipart/form-data")
        limit = self.settings.max_upload_bytes + MULTIPART_OVERHEAD
        if not multipart:
            limit = min(limit, self.settings.max_request_body_bytes)
        try:
            if multipart:
                await run_in_threadpool(current_user, request, self.settings)
            declared = request.headers.get("content-length")
            if declared is not None:
                try:
                    length = int(declared)
                except ValueError as exc:
                    raise AppError("The request size is invalid.", code="INVALID_REQUEST", status=400) from exc
                if length < 0:
                    raise AppError("The request size is invalid.", code="INVALID_REQUEST", status=400)
                if length > limit:
                    raise AppError("This upload is too large. Please use a smaller file.", code="FILE_TOO_LARGE", status=413)
        except AppError as exc:
            await JSONResponse({"code": exc.code, "message": exc.message, "requestId": request_id.get()}, status_code=exc.status)(scope, receive, send)
            return

        received = 0
        exceeded = False
        replaced = False
        if multipart:
            if self.slots.locked():
                await JSONResponse({"code": "UPLOAD_BUSY", "message": "Other documents are being read. Please try again shortly.",
                                    "requestId": request_id.get()}, status_code=429, headers={"Retry-After": "2"})(scope, receive, send)
                return
            await self.slots.acquire()

        async def bounded_receive():
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    # Starlette closes partial multipart files for this parser exception.
                    # FastAPI translates body parsing errors to 400, so replace that response
                    # below with the specific 413; never consume the remaining request.
                    raise MultiPartException("Request exceeded its transport size limit")
            return message

        async def bounded_send(message):
            nonlocal replaced
            if exceeded:
                if not replaced:
                    replaced = True
                    await JSONResponse({"code": "FILE_TOO_LARGE", "message": "This upload is too large. Please use a smaller file.",
                                        "requestId": request_id.get()}, status_code=413)(scope, receive, send)
                return
            await send(message)

        try:
            await self.app(scope, bounded_receive, bounded_send)
        finally:
            if multipart:
                self.slots.release()
