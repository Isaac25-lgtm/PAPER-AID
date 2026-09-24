"""Structured JSON logs. Paper text, prompts, secrets and signed URLs must never be logged:
callers pass identifiers and counts only, and fields with risky names are dropped here too."""

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime

request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
job_id: contextvars.ContextVar[str] = contextvars.ContextVar("job_id", default="-")

_FORBIDDEN_FIELDS = {"text", "content", "prompt", "paper", "url", "signed_url", "api_key", "token"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "requestId": request_id.get(),
            "jobId": job_id.get(),
        }
        for key, value in getattr(record, "fields", {}).items():
            if key.lower() not in _FORBIDDEN_FIELDS:
                entry[key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for noisy in ("httpx", "httpcore", "uvicorn.access", "anthropic", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def log(logger: logging.Logger, level: int, message: str, **fields: object) -> None:
    logger.log(level, message, extra={"fields": fields})
