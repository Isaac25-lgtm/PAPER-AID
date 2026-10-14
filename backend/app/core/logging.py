"""Structured JSON logs. Paper text, prompts, secrets and signed URLs must never be logged:
callers pass identifiers and counts only, and fields with risky names are dropped here too."""

import contextvars
import json
import logging
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
job_id: contextvars.ContextVar[str] = contextvars.ContextVar("job_id", default="-")

_FORBIDDEN_FIELDS = {"text", "content", "prompt", "paper", "url", "signedurl", "apikey", "token", "body",
                     "detail", "error", "exception", "password", "authorization", "filename", "title",
                     "problem", "message", "subject", "input", "data", "response", "traceback", "stack"}


def _safe_fields(value: object, depth: int = 0) -> object:
    if depth > 8:
        return "[omitted]"
    if isinstance(value, dict):
        return {str(k): _safe_fields(v, depth + 1) for k, v in value.items()
                if str(k).lower().replace("_", "").replace("-", "") not in _FORBIDDEN_FIELDS
                and not str(k).lower().replace("_", "").endswith(("token", "password", "secret"))}
    if isinstance(value, (list, tuple)):
        return [_safe_fields(v, depth + 1) for v in value[:100]]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return "[omitted]"  # never stringify an arbitrary object/exception containing inputs


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            # Application messages are fixed labels. Interpolated args and external library
            # messages can carry paper text, URLs or credentials, so are never rendered.
            "message": record.msg if isinstance(record.msg, str) and record.name.startswith("paperaid") else "external library event",
            "logger": record.name,
            "requestId": request_id.get(),
            "jobId": job_id.get(),
        }
        safe = _safe_fields(getattr(record, "fields", {}))
        if isinstance(safe, dict):
            entry.update({k: v for k, v in safe.items() if k not in entry})
        if record.exc_info:
            entry["exceptionType"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            entry["frames"] = [{"file": Path(f.filename).name, "function": f.name, "line": f.lineno}
                               for f in traceback.extract_tb(record.exc_info[2])][-20:]
        return json.dumps(entry)


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for noisy in ("httpx", "httpcore", "uvicorn.access", "anthropic", "openai", "google.genai", "google.auth"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def log(logger: logging.Logger, level: int, message: str, **fields: object) -> None:
    logger.log(level, message, extra={"fields": fields})
