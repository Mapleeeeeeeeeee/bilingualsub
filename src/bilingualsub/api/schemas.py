"""Pydantic v2 request/response schemas."""

from pydantic import BaseModel, HttpUrl

from bilingualsub.api.constants import FileType, JobStatus


class JobCreateRequest(BaseModel):
    """Request body for creating a new subtitle generation job."""

    youtube_url: HttpUrl
    source_lang: str = "en"
    target_lang: str = "zh-TW"


class JobCreateResponse(BaseModel):
    """Response body after creating a job."""

    job_id: str


class ErrorDetail(BaseModel):
    """Structured error information."""

    code: str
    message: str
    detail: str | None = None


class JobStatusResponse(BaseModel):
    """Response body for job status queries."""

    model_config = {"from_attributes": True}

    job_id: str
    status: JobStatus
    progress: float
    current_step: str | None = None
    error: ErrorDetail | None = None
    output_files: dict[FileType, str] = {}


class SSEProgressData(BaseModel):
    """Payload sent in SSE progress events."""

    status: JobStatus
    progress: float
    current_step: str | None = None
    message: str | None = None
