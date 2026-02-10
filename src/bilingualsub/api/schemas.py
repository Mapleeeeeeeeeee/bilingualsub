"""Pydantic v2 request/response schemas."""

from typing import Self

from pydantic import BaseModel, HttpUrl, model_validator

from bilingualsub.api.constants import FileType, JobStatus


class JobCreateRequest(BaseModel):
    """Request body for creating a new subtitle generation job."""

    youtube_url: HttpUrl
    source_lang: str = "en"
    target_lang: str = "zh-TW"
    start_time: float | None = None
    end_time: float | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        if self.start_time is not None and self.start_time < 0:
            raise ValueError("start_time must be non-negative")
        if self.end_time is not None and self.end_time < 0:
            raise ValueError("end_time must be non-negative")
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time >= self.end_time
        ):
            raise ValueError("start_time must be less than end_time")
        return self


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


class BurnRequest(BaseModel):
    """Request body for on-demand subtitle burn."""

    srt_content: str


class SSEProgressData(BaseModel):
    """Payload sent in SSE progress events."""

    status: JobStatus
    progress: float
    current_step: str | None = None
    message: str | None = None
