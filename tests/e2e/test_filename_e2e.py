"""E2E test: real yt-dlp download validates info_dict title flows into Content-Disposition.

This test hits the real YouTube network but mocks Groq (no API key needed).
Goal: verify the bug fix where video_title was previously sourced from ffprobe
MP4 container tags (which are empty) rather than yt-dlp info_dict.title.

Gate: set ENABLE_LIVE_DOWNLOAD=1 to run. Skipped by default in CI.
"""

from __future__ import annotations

import os
import time
import urllib.parse
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from bilingualsub.api.app import create_app

if TYPE_CHECKING:
    from collections.abc import Generator

# ---------------------------------------------------------------------------
# Environment gate
# ---------------------------------------------------------------------------

ENABLE_LIVE_DOWNLOAD = os.getenv("ENABLE_LIVE_DOWNLOAD") == "1"

pytestmark = pytest.mark.skipif(
    not ENABLE_LIVE_DOWNLOAD,
    reason="ENABLE_LIVE_DOWNLOAD not set; skipping live yt-dlp download E2E",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# YouTube's first public video — 19 seconds, stable, public.
_TEST_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
_EXPECTED_TITLE = "Me at the zoo"

# How long (seconds) to wait for the download phase to complete.
_DOWNLOAD_TIMEOUT_SECONDS = 90
_POLL_INTERVAL_SECONDS = 1.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filename_from_disposition(header: str) -> str:
    """Extract filename from Content-Disposition header.

    Handles RFC 5987 ``filename*=utf-8''<pct-encoded>`` and
    the plain ``filename="..."`` fallback.
    """
    marker_rfc5987 = "filename*=utf-8''"
    if marker_rfc5987 in header:
        return urllib.parse.unquote(header.split(marker_rfc5987, 1)[1])
    marker_plain = 'filename="'
    if marker_plain in header:
        return header.split(marker_plain, 1)[1].rstrip('"')
    raise AssertionError(f"Unrecognized Content-Disposition header: {header}")


def _poll_until_download_complete(
    client: TestClient,
    job_id: str,
    timeout: float = _DOWNLOAD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Poll GET /api/jobs/{job_id} until status is download_complete or failed.

    Returns the final status response dict.
    Raises pytest.fail if timeout is exceeded or network error is detected.
    """
    deadline = time.monotonic() + timeout
    last_status: dict[str, Any] = {}

    while time.monotonic() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        if resp.status_code != 200:
            pytest.fail(
                f"GET /api/jobs/{job_id} returned {resp.status_code}: {resp.text}"
            )

        last_status = resp.json()
        status = last_status.get("status")

        if status in ("download_complete", "failed"):
            return last_status

        time.sleep(_POLL_INTERVAL_SECONDS)

    pytest.fail(
        f"Timed out after {timeout}s waiting for download_complete. "
        f"Last status: {last_status.get('status')!r}. "
        "Check network connectivity or increase _DOWNLOAD_TIMEOUT_SECONDS."
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def live_client() -> Generator[TestClient, None, None]:
    """Create a TestClient for live download tests.

    Must enter the context manager so Starlette starts the lifespan and
    populates ``app.state.job_manager``; without this every request fails
    with ``AttributeError`` on ``app.state``.
    """

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_source_video_content_disposition_uses_info_dict_title(
    live_client: TestClient,
) -> None:
    """Real yt-dlp download: source_video Content-Disposition uses info_dict title.

    Arrange: submit "Me at the zoo" URL (19-second public YouTube video).
    Act:
        1. POST /api/jobs with source_url.
        2. Poll until status == download_complete (stops before Whisper/Groq).
        3. GET /api/jobs/{id}/download/source_video.
    Assert:
        - Download phase completes without error.
        - Content-Disposition filename == "Me at the zoo (original).mp4".

    This test covers the regression where video_title was sourced from the
    ffprobe MP4 container tag (empty string) instead of yt-dlp info_dict.title,
    which caused filenames to fall back to "video (original).mp4".
    """
    # 1. Create job.
    create_resp = live_client.post("/api/jobs", json={"source_url": _TEST_URL})
    assert create_resp.status_code == 200, create_resp.text
    job_id = create_resp.json()["job_id"]

    # 2. Poll until download_complete.
    status_data = _poll_until_download_complete(live_client, job_id)
    if status_data["status"] == "failed":
        error = status_data.get("error", {})
        pytest.fail(
            f"Live download failed; cannot verify info_dict.title regression. "
            f"{error.get('code')} — {error.get('detail')}. "
            "If the CI runner cannot reach YouTube, disable this test via the "
            "ENABLE_LIVE_DOWNLOAD gate instead of silently skipping."
        )

    assert status_data["status"] == "download_complete"

    # 3. Download source_video and check Content-Disposition.
    dl_resp = live_client.get(f"/api/jobs/{job_id}/download/source_video")
    assert dl_resp.status_code == 200, dl_resp.text

    disposition = dl_resp.headers.get("content-disposition", "")
    assert disposition, "Expected Content-Disposition header to be present"

    actual_filename = _filename_from_disposition(disposition)
    assert actual_filename == f"{_EXPECTED_TITLE} (original).mp4", (
        f"Expected '{_EXPECTED_TITLE} (original).mp4', got {actual_filename!r}. "
        "This likely means video_title is sourced from an empty ffprobe container "
        "tag instead of yt-dlp info_dict.title."
    )


@pytest.mark.e2e
def test_audio_content_disposition_uses_info_dict_title(
    live_client: TestClient,
) -> None:
    """Real yt-dlp download: audio Content-Disposition uses info_dict title.

    Reuses the same video; creates a separate job to keep tests independent.

    Arrange: submit "Me at the zoo" URL.
    Act:
        1. POST /api/jobs.
        2. Poll until download_complete.
        3. GET /api/jobs/{id}/download/audio.
    Assert: filename == "Me at the zoo (original).mp3".
    """
    # 1. Create job.
    create_resp = live_client.post("/api/jobs", json={"source_url": _TEST_URL})
    assert create_resp.status_code == 200, create_resp.text
    job_id = create_resp.json()["job_id"]

    # 2. Poll until download_complete.
    status_data = _poll_until_download_complete(live_client, job_id)
    if status_data["status"] == "failed":
        error = status_data.get("error", {})
        pytest.fail(
            f"Live download failed; cannot verify info_dict.title regression. "
            f"{error.get('code')} — {error.get('detail')}. "
            "If the CI runner cannot reach YouTube, disable this test via the "
            "ENABLE_LIVE_DOWNLOAD gate instead of silently skipping."
        )

    assert status_data["status"] == "download_complete"

    # 3. Download audio and check Content-Disposition.
    dl_resp = live_client.get(f"/api/jobs/{job_id}/download/audio")
    assert dl_resp.status_code == 200, dl_resp.text

    disposition = dl_resp.headers.get("content-disposition", "")
    assert disposition, "Expected Content-Disposition header to be present"

    actual_filename = _filename_from_disposition(disposition)
    assert actual_filename == f"{_EXPECTED_TITLE} (original).mp3", (
        f"Expected '{_EXPECTED_TITLE} (original).mp3', got {actual_filename!r}. "
        "This likely means video_title is sourced from an empty ffprobe container "
        "tag instead of yt-dlp info_dict.title."
    )
