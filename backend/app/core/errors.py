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
