"""Integration tests for the API contract introduced in feat/readable-filename-multiplatform.

Covers:
- JobCreateRequest schema: source_url field, extra="forbid" enforcement
- URL extractor acceptance (yt-dlp supported platforms)
- Async error path for unsupported URLs (invalid_input pipeline error)
- Download filename Content-Disposition header format
"""

from __future__ import annotations

import time
import urllib.parse
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

from bilingualsub.api.app import create_app
from bilingualsub.api.constants import FileType, JobStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filename_from_disposition(header: str) -> str:
    """Extract filename from Content-Disposition header.

    Handles both RFC 5987 ``filename*=utf-8''<pct-encoded>`` and
    the plain ``filename="..."`` fallback.
    """
    marker_rfc5987 = "filename*=utf-8''"
    if marker_rfc5987 in header:
        return urllib.parse.unquote(header.split(marker_rfc5987, 1)[1])
    marker_plain = 'filename="'
    if marker_plain in header:
        return header.split(marker_plain, 1)[1].rstrip('"')
    raise AssertionError(f"Unrecognized Content-Disposition header: {header}")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """Create a TestClient that runs the full app lifespan (sets app.state).

    Must be used as a context manager internally — yielding ensures lifespan
    teardown runs after the test.
    """
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def completed_job_factory(tmp_path: Path) -> Generator[Any, None, None]:
    """Factory that injects a completed Job directly into JobManager.

    Yields a callable ``make(title, source_lang, target_lang) -> (client, job_id)``.
    The TestClient is kept alive (via context manager) for the fixture's lifetime
    so ``app.state.job_manager`` is accessible and the injected job persists.
    """
    _app = create_app()

    with TestClient(_app, raise_server_exceptions=False) as _client:

        def make(
            title: str,
            source_lang: str,
            target_lang: str,
        ) -> tuple[TestClient, str]:
            manager = _app.state.job_manager
            job = manager.create_job(
                source_url="https://www.youtube.com/watch?v=x",
                source_lang=source_lang,
                target_lang=target_lang,
            )
            job.video_title = title
            job.status = JobStatus.COMPLETED

            # Create a dummy file for every FileType so all download routes work.
            # Use unique subdirs per call to avoid filename collisions across
            # parametrize iterations.
            job_tmp = tmp_path / job.id
            job_tmp.mkdir(parents=True, exist_ok=True)
            for ft in (
                FileType.SRT,
                FileType.ASS,
                FileType.VIDEO,
                FileType.AUDIO,
                FileType.SOURCE_VIDEO,
            ):
                p = job_tmp / f"{ft.value}.bin"
                p.write_bytes(b"x")
                job.output_files[ft] = p

            return _client, job.id

        yield make


# ===========================================================================
# 1. JobCreateRequest schema contract
# ===========================================================================


@pytest.mark.integration
class TestJobCreateRequestSchema:
    """Verify that the POST /api/jobs endpoint enforces the new schema contract."""

    def test_valid_source_url_returns_job_id(self, client: TestClient) -> None:
        """POST with source_url returns 200 and a non-empty job_id string.

        Arrange: valid JobCreateRequest body using the new source_url field.
        Act:     POST /api/jobs.
        Assert:  status 200, response contains string job_id.
        """
        response = client.post(
            "/api/jobs",
            json={"source_url": "https://www.youtube.com/watch?v=abc"},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["job_id"], str)
        assert data["job_id"]

    def test_old_field_youtube_url_rejected(self, client: TestClient) -> None:
        """POST with the old youtube_url field is rejected with 422 (extra='forbid').

        Arrange: body uses youtube_url (the previous field name).
        Act:     POST /api/jobs.
        Assert:  status 422 — Pydantic extra='forbid' disallows unknown fields.
        """
        response = client.post(
            "/api/jobs",
            json={"youtube_url": "https://www.youtube.com/watch?v=abc"},
        )

        assert response.status_code == 422

    def test_both_fields_rejected(self, client: TestClient) -> None:
        """POST with both source_url and youtube_url fields is rejected with 422.

        Arrange: body contains source_url (valid) AND youtube_url (extra field).
        Act:     POST /api/jobs.
        Assert:  status 422 — extra='forbid' triggers even when source_url is present.
        """
        response = client.post(
            "/api/jobs",
            json={
                "source_url": "https://www.youtube.com/watch?v=abc",
                "youtube_url": "https://www.youtube.com/watch?v=abc",
            },
        )

        assert response.status_code == 422

    def test_non_url_source_url_rejected(self, client: TestClient) -> None:
        """POST with a non-URL string in source_url is rejected with 422.

        Arrange: source_url is plain text, not a valid HTTP URL.
        Act:     POST /api/jobs.
        Assert:  status 422 — Pydantic HttpUrl rejects the value.
        """
        response = client.post(
            "/api/jobs",
            json={"source_url": "not-a-url"},
        )

        assert response.status_code == 422

    def test_empty_body_rejected(self, client: TestClient) -> None:
        """POST with an empty body is rejected with 422 (missing required field).

        Arrange: empty JSON object.
        Act:     POST /api/jobs.
        Assert:  status 422 — source_url is required.
        """
        response = client.post("/api/jobs", json={})

        assert response.status_code == 422


# ===========================================================================
# 2. URL extractor acceptance
# ===========================================================================


@pytest.mark.integration
@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://x.com/elonmusk/status/1234567890123456789",
        "https://twitter.com/jack/status/20",
        "https://www.tiktok.com/@user/video/1234567890",
        "https://vimeo.com/12345678",
    ],
)
def test_valid_http_urls_return_job_id(client: TestClient, url: str) -> None:
    """POST with any syntactically valid HttpUrl returns 200 at the HTTP layer.

    HttpUrl is the only synchronous URL check; yt-dlp extractor matching runs
    inside the background ``run_download`` task. So this test only proves the
    schema accepts these URL shapes — it does NOT prove yt-dlp has an
    extractor for any of them. Extractor-level coverage lives in
    tests/unit/core/test_downloader.py::TestIsSupportedUrl and in
    test_unsupported_url_fails_with_invalid_input below.
    """
    response = client.post("/api/jobs", json={"source_url": url})

    assert response.status_code == 200
    assert "job_id" in response.json()


# ===========================================================================
# 3. Async error path: unsupported URL
# ===========================================================================


@pytest.mark.integration
def test_unsupported_url_fails_with_invalid_input(client: TestClient) -> None:
    """An unsupported URL creates a job then fails asynchronously with invalid_input.

    Arrange: URL that passes HttpUrl validation but has no yt-dlp extractor.
    Act:
        1. POST /api/jobs → 200, job_id returned.
        2. Poll GET /api/jobs/{id} until status=failed (max 10s — the check
           itself is in-memory but runs inside asyncio.to_thread, which can
           queue behind other threads on a loaded CI runner).
    Assert:
        - job status is "failed".
        - error.code == "invalid_input".
        - error.detail contains "yt-dlp".
    """
    response = client.post(
        "/api/jobs",
        json={"source_url": "https://example.com/some-random-page.html"},
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    # Poll until failed or timeout.
    deadline = time.monotonic() + 10.0
    status_data: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status_resp = client.get(f"/api/jobs/{job_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        if status_data["status"] == "failed":
            break
        time.sleep(0.2)

    assert status_data.get("status") == "failed", (
        f"Expected status=failed, got {status_data.get('status')!r}"
    )
    error = status_data.get("error")
    assert error is not None, "Expected error detail in response"
    assert error["code"] == "invalid_input"
    assert "yt-dlp" in (error.get("detail") or "")


# ===========================================================================
# 4. Download filename Content-Disposition format
# ===========================================================================


@pytest.mark.integration
@pytest.mark.parametrize(
    "title,source_lang,target_lang,file_type,expected_filename",
    [
        # Translated subtitle files use (src_to_tgt) suffix.
        (
            "Me at the zoo",
            "en",
            "zh-TW",
            FileType.SRT,
            "Me at the zoo (en_to_zh-TW).srt",
        ),
        (
            "Me at the zoo",
            "en",
            "zh-TW",
            FileType.ASS,
            "Me at the zoo (en_to_zh-TW).ass",
        ),
        # Source video and audio always use (original).
        (
            "Me at the zoo",
            "en",
            "zh-TW",
            FileType.SOURCE_VIDEO,
            "Me at the zoo (original).mp4",
        ),
        (
            "Me at the zoo",
            "en",
            "zh-TW",
            FileType.AUDIO,
            "Me at the zoo (original).mp3",
        ),
        # Same src/tgt lang → (original) even for SRT.
        ("My Video", "en", "en", FileType.SRT, "My Video (original).srt"),
        # Empty title → fallback to "video".
        ("", "en", "zh-TW", FileType.SRT, "video (en_to_zh-TW).srt"),
        # Illegal filesystem chars are stripped.
        ('Bad: <chars>"/', "en", "zh-TW", FileType.SRT, "Bad chars (en_to_zh-TW).srt"),
    ],
)
def test_content_disposition_filename(
    completed_job_factory: Any,
    title: str,
    source_lang: str,
    target_lang: str,
    file_type: FileType,
    expected_filename: str,
) -> None:
    """Content-Disposition header carries the correctly formatted filename.

    Arrange: inject a completed job with the given title/langs, pre-create
             dummy output files.
    Act:     GET /api/jobs/{id}/download/{file_type}.
    Assert:  filename extracted from Content-Disposition matches expected_filename.
    """
    _client, job_id = completed_job_factory(title, source_lang, target_lang)

    response = _client.get(f"/api/jobs/{job_id}/download/{file_type.value}")

    assert response.status_code == 200, response.text
    disposition = response.headers.get("content-disposition", "")
    assert disposition, "Expected Content-Disposition header to be present"

    actual_filename = _filename_from_disposition(disposition)
    assert actual_filename == expected_filename, (
        f"Expected {expected_filename!r}, got {actual_filename!r} "
        f"(full header: {disposition!r})"
    )
