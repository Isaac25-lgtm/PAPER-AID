class AppError(Exception):
    """A failure we expect and can explain to the user. Rendered as {code, message, requestId}."""

    status = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.status = status or self.status


class Unauthorized(AppError):
    status, code = 401, "UNAUTHENTICATED"


class Forbidden(AppError):
    status, code = 403, "FORBIDDEN"


class NotFound(AppError):
    status, code = 404, "NOT_FOUND"


class Conflict(AppError):
    status, code = 409, "CONFLICT"


class InvalidDocument(AppError):
    status, code = 422, "INVALID_DOCUMENT"


class LimitExceeded(AppError):
    status, code = 429, "LIMIT_EXCEEDED"


class CapacityWait(Exception):  # noqa: N818 - a signal, not an error
    """No Gemini capacity is free right now (the shared limit is full, or the limiter cannot be reached): the stage
    pauses, keeps everything it has done, and is delivered again after a short wait. It never uses up the stage's
    retries for provider failures (speed plan 2026-10-08)."""

    def __init__(self, reason: str, delay_sec: int | None = None, kind: str = "CAPACITY"):
        super().__init__(reason)
        self.reason = reason
        self.delay_sec = delay_sec  # how long to wait before the stage is delivered again (None: the usual short wait)
        self.kind = kind  # CAPACITY, or REVIEW: the final editor's model cannot answer now (algorithm revision 2026-10-09)


class LimiterUnavailable(Exception):
    """The shared Gemini limiter could not be read or written. Treated as "no capacity": nothing bypasses it."""


class StageError(Exception):
    """Raised inside a processing stage. `retryable` decides whether the queue tries again."""

    retryable = False

    def __init__(self, code: str, user_message: str, detail: str = ""):
        super().__init__(f"{code}: {detail or user_message}")
        self.code = code
        self.user_message = user_message
        self.detail = detail


class RetryableStageError(StageError):
    retryable = True


class PermanentStageError(StageError):
    retryable = False
