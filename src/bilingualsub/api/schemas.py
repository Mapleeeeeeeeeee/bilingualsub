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


class StartSubtitleRequest(BaseModel):
    """Request body for subtitle generation trigger."""

    source_lang: str | None = None
    target_lang: str | None = None


class PartialRetranslateEntry(BaseModel):
    """A subtitle entry used for partial re-translation."""

    index: int
    original: str
    translated: str = ""


class PartialRetranslateRequest(BaseModel):
    """Request body for partial re-translation."""

    selected_indices: list[int]
    entries: list[PartialRetranslateEntry]
    user_context: str | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        if not self.selected_indices:
            raise ValueError("selected_indices cannot be empty")
        if not self.entries:
            raise ValueError("entries cannot be empty")

        known = {entry.index for entry in self.entries}
        missing = [idx for idx in self.selected_indices if idx not in known]
        if missing:
            raise ValueError(f"selected_indices not found in entries: {missing}")
        return self


class PartialRetranslateItem(BaseModel):
    """Single re-translated item."""

    index: int
    translated: str


class PartialRetranslateResponse(BaseModel):
    """Response body for partial re-translation."""

    results: list[PartialRetranslateItem]


class SSEProgressData(BaseModel):
    """Payload sent in SSE progress events."""

    status: JobStatus
    progress: float
    current_step: str | None = None
    message: str | None = None
