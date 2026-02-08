"""Tests for API schemas."""

import pytest
from pydantic import ValidationError

from bilingualsub.api.constants import JobStatus
from bilingualsub.api.schemas import (
    ErrorDetail,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
    SSEProgressData,
)


@pytest.mark.unit
class TestJobCreateRequest:
    def test_valid_youtube_url(self) -> None:
        req = JobCreateRequest(
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
        assert str(req.youtube_url) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_default_languages(self) -> None:
        req = JobCreateRequest(youtube_url="https://www.youtube.com/watch?v=test123")
        assert req.source_lang == "en"
        assert req.target_lang == "zh-TW"

    def test_custom_languages(self) -> None:
        req = JobCreateRequest(
            youtube_url="https://www.youtube.com/watch?v=test",
            source_lang="ja",
            target_lang="en",
        )
        assert req.source_lang == "ja"
        assert req.target_lang == "en"

    def test_invalid_url_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JobCreateRequest(youtube_url="not-a-url")

    def test_default_time_range_is_none(self) -> None:
        req = JobCreateRequest(youtube_url="https://www.youtube.com/watch?v=test123")
        assert req.start_time is None
        assert req.end_time is None

    def test_valid_time_range(self) -> None:
        req = JobCreateRequest(
            youtube_url="https://www.youtube.com/watch?v=test123",
            start_time=10.0,
            end_time=30.0,
        )
        assert req.start_time == 10.0
        assert req.end_time == 30.0

    def test_start_time_only(self) -> None:
        req = JobCreateRequest(
            youtube_url="https://www.youtube.com/watch?v=test123",
            start_time=10.0,
        )
        assert req.start_time == 10.0
        assert req.end_time is None

    def test_end_time_only(self) -> None:
        req = JobCreateRequest(
            youtube_url="https://www.youtube.com/watch?v=test123",
            end_time=30.0,
        )
        assert req.start_time is None
        assert req.end_time == 30.0

    def test_negative_start_time_rejected(self) -> None:
        with pytest.raises(ValidationError, match="start_time must be non-negative"):
            JobCreateRequest(
                youtube_url="https://www.youtube.com/watch?v=test123",
                start_time=-1.0,
            )

    def test_negative_end_time_rejected(self) -> None:
        with pytest.raises(ValidationError, match="end_time must be non-negative"):
            JobCreateRequest(
                youtube_url="https://www.youtube.com/watch?v=test123",
                end_time=-5.0,
            )

    def test_start_time_greater_than_end_time_rejected(self) -> None:
        with pytest.raises(
            ValidationError, match="start_time must be less than end_time"
        ):
            JobCreateRequest(
                youtube_url="https://www.youtube.com/watch?v=test123",
                start_time=30.0,
                end_time=10.0,
            )

    def test_start_time_equal_to_end_time_rejected(self) -> None:
        with pytest.raises(
            ValidationError, match="start_time must be less than end_time"
        ):
            JobCreateRequest(
                youtube_url="https://www.youtube.com/watch?v=test123",
                start_time=10.0,
                end_time=10.0,
            )


@pytest.mark.unit
class TestJobCreateResponse:
    def test_basic(self) -> None:
        resp = JobCreateResponse(job_id="abc123")
        assert resp.job_id == "abc123"


@pytest.mark.unit
class TestJobStatusResponse:
    def test_minimal(self) -> None:
        resp = JobStatusResponse(
            job_id="abc123",
            status=JobStatus.PENDING,
            progress=0.0,
        )
        assert resp.job_id == "abc123"
        assert resp.status == JobStatus.PENDING
        assert resp.error is None
        assert resp.output_files == {}

    def test_with_error(self) -> None:
        resp = JobStatusResponse(
            job_id="abc123",
            status=JobStatus.FAILED,
            progress=50.0,
            error=ErrorDetail(code="download_failed", message="Failed"),
        )
        assert resp.error is not None
        assert resp.error.code == "download_failed"


@pytest.mark.unit
class TestSSEProgressData:
    def test_basic(self) -> None:
        data = SSEProgressData(
            status=JobStatus.DOWNLOADING,
            progress=10.0,
            current_step="download",
            message="Downloading video",
        )
        assert data.status == JobStatus.DOWNLOADING
        assert data.progress == 10.0
