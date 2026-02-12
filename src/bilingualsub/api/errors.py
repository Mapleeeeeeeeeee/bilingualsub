"""API error hierarchy."""


class ApiError(Exception):
    """Base API error with HTTP status code and structured detail."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        detail: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)


class JobNotFoundError(ApiError):
    """Raised when a requested job does not exist."""

    def __init__(self, job_id: str) -> None:
        super().__init__(
            status_code=404,
            code="job_not_found",
            message=f"Job {job_id} not found",
        )


class InvalidRequestError(ApiError):
    """Raised when the client sends an invalid request."""

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(
            status_code=422,
            code="invalid_request",
            message=message,
            detail=detail,
        )


class PipelineError(ApiError):
    """Raised when a pipeline stage fails."""

    def __init__(self, code: str, message: str, *, detail: str | None = None) -> None:
        super().__init__(
            status_code=500,
            code=code,
            message=message,
            detail=detail,
        )
