"""Integration tests for the visual description subtitle pipeline.

Covers three causal chains:
1. Happy path: POST /api/jobs → inject state → POST subtitle → poll → COMPLETED
2. Video too long: duration > 5400 s → job fails with "video_too_long"
3. Missing API key: no GEMINI_API_KEY → job fails with "invalid_input"
"""

from __future__ import annotations

import time
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from pathlib import Path

from bilingualsub.api.app import create_app
from bilingualsub.api.constants import FileType, JobStatus
from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.utils.config import get_settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _noop_run_download(*_args: object, **_kwargs: object) -> None:
    """Async no-op that prevents the real download pipeline from running."""


# ---------------------------------------------------------------------------
# Mock subtitle data
# ---------------------------------------------------------------------------


def _make_described_subtitle() -> Subtitle:
    return Subtitle(
        entries=[
            SubtitleEntry(
                index=1,
                start=timedelta(seconds=0),
                end=timedelta(seconds=5),
                text="Product showcase",
            ),
            SubtitleEntry(
                index=2,
                start=timedelta(seconds=5),
                end=timedelta(seconds=10),
                text="Brand logo appears",
            ),
            SubtitleEntry(
                index=3,
                start=timedelta(seconds=10),
                end=timedelta(seconds=15),
                text="Contact information",
            ),
        ]
    )


def _make_translated_subtitle() -> Subtitle:
    return Subtitle(
        entries=[
            SubtitleEntry(
                index=1,
                start=timedelta(seconds=0),
                end=timedelta(seconds=5),
                text="產品展示",
            ),
            SubtitleEntry(
                index=2,
                start=timedelta(seconds=5),
                end=timedelta(seconds=10),
                text="品牌標誌出現",
            ),
            SubtitleEntry(
                index=3,
                start=timedelta(seconds=10),
                end=timedelta(seconds=15),
                text="聯絡資訊",
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Polling helper
# ---------------------------------------------------------------------------


def _poll_until_terminal(
    client: TestClient, job_id: str, deadline_seconds: float = 10.0
) -> dict[str, Any]:
    """Poll GET /api/jobs/{job_id} until status is completed or failed."""
    deadline = time.monotonic() + deadline_seconds
    status_data: dict[str, Any] = {}
    while time.monotonic() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        status_data = resp.json()
        if status_data["status"] in ("completed", "failed"):
            return status_data
        time.sleep(0.1)
    return status_data


# ===========================================================================
# Tests
# ===========================================================================


@pytest.mark.integration
class TestVisualDescriptionPipeline:
    """Integration tests for the visual_description processing mode."""

    def test_visual_description_journey_produces_srt(
        self,
        tmp_path: Path,
    ) -> None:
        """Happy path: visual description pipeline completes and writes SRT file.

        Causal chain:
        1. POST /api/jobs (visual_description) → 200, job_id
        2. Inject DOWNLOAD_COMPLETE state + fake files into job_manager
        3. Mock describe_video + translate_subtitle
        4. POST /api/jobs/{job_id}/subtitle → 200
        5. Poll until completed
        6. Assert subtitle_source, SRT exists and non-empty, ASS absent
        """
        app = create_app()

        with TestClient(app, raise_server_exceptions=False) as client:
            # Step 1: create job — patch run_download so it never runs and can't
            # race with the state we inject below.
            with patch("bilingualsub.api.routes.run_download", _noop_run_download):
                create_resp = client.post(
                    "/api/jobs",
                    json={
                        "source_url": "https://example.com/video.mp4",
                        "processing_mode": "visual_description",
                    },
                )
            assert create_resp.status_code == 200
            job_id = create_resp.json()["job_id"]

            # Step 2: inject state directly into job
            job = app.state.job_manager.get_job(job_id)
            assert job is not None, "Job should exist in manager after creation"

            video_path = tmp_path / "video.mp4"
            video_path.write_bytes(b"fake video content")
            audio_path = tmp_path / "audio.wav"
            audio_path.write_bytes(b"fake audio content")

            job.status = JobStatus.DOWNLOAD_COMPLETE
            job.video_duration = 60.0
            job.output_files[FileType.SOURCE_VIDEO] = video_path
            job.output_files[FileType.AUDIO] = audio_path

            # Step 3 + 4: mock pipeline functions, then trigger subtitle step
            with (
                patch("bilingualsub.api.pipeline.describe_video") as mock_describe,
                patch("bilingualsub.api.pipeline.translate_subtitle") as mock_translate,
            ):
                mock_describe.return_value = _make_described_subtitle()
                mock_translate.return_value = _make_translated_subtitle()

                subtitle_resp = client.post(
                    f"/api/jobs/{job_id}/subtitle",
                    json={"processing_mode": "visual_description"},
                )
                assert subtitle_resp.status_code == 200

                # Step 5: poll for completion
                status_data = _poll_until_terminal(client, job_id)

            # Step 6: assertions
            assert status_data["status"] == "completed", (
                f"Expected completed, got {status_data['status']!r}. "
                f"Error: {status_data.get('error')}"
            )

            # Reload job from manager to inspect final state
            job = app.state.job_manager.get_job(job_id)
            assert job is not None

            assert job.subtitle_source == "visual_description", (
                f"Expected subtitle_source='visual_description', got {job.subtitle_source!r}"
            )

            assert FileType.SRT in job.output_files, (
                "Expected SRT file in output_files after visual description"
            )
            srt_path = job.output_files[FileType.SRT]
            assert srt_path.exists(), f"SRT file does not exist at {srt_path}"
            assert srt_path.stat().st_size > 0, "SRT file should be non-empty"

            assert FileType.ASS not in job.output_files, (
                "Visual description mode should NOT produce an ASS file"
            )

    def test_visual_description_video_too_long_fails(
        self,
        tmp_path: Path,
    ) -> None:
        """Video duration > 5400 s causes job to fail with 'video_too_long' error.

        Causal chain:
        1. POST /api/jobs (visual_description) → 200
        2. Inject DOWNLOAD_COMPLETE + duration 5401.0 s
        3. POST /api/jobs/{job_id}/subtitle → 200
        4. Poll until failed
        5. Assert error.code == "video_too_long"
        """
        app = create_app()

        with TestClient(app, raise_server_exceptions=False) as client:
            # Step 1: create job — prevent download from racing with state injection
            with patch("bilingualsub.api.routes.run_download", _noop_run_download):
                create_resp = client.post(
                    "/api/jobs",
                    json={
                        "source_url": "https://example.com/long-video.mp4",
                        "processing_mode": "visual_description",
                    },
                )
            assert create_resp.status_code == 200
            job_id = create_resp.json()["job_id"]

            # Step 2: inject state with a video that exceeds the limit
            job = app.state.job_manager.get_job(job_id)
            assert job is not None

            video_path = tmp_path / "long_video.mp4"
            video_path.write_bytes(b"fake long video")

            job.status = JobStatus.DOWNLOAD_COMPLETE
            job.video_duration = 5401.0
            job.output_files[FileType.SOURCE_VIDEO] = video_path

            # Step 3: trigger subtitle step
            subtitle_resp = client.post(
                f"/api/jobs/{job_id}/subtitle",
                json={"processing_mode": "visual_description"},
            )
            assert subtitle_resp.status_code == 200

            # Step 4: poll until failed
            status_data = _poll_until_terminal(client, job_id)

        # Step 5: verify error
        assert status_data["status"] == "failed", (
            f"Expected failed, got {status_data['status']!r}"
        )
        error = status_data.get("error")
        assert error is not None, "Expected error detail in response"
        assert error["code"] == "video_too_long", (
            f"Expected error code 'video_too_long', got {error['code']!r}"
        )

    def test_visual_description_missing_api_key_fails(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Missing GEMINI_API_KEY causes job to fail with 'invalid_input' error.

        The ValueError raised by get_gemini_api_key() maps to 'invalid_input'
        via _ERROR_MAP in pipeline.py.

        Causal chain:
        1. Remove GEMINI_API_KEY from env + clear settings cache
        2. POST /api/jobs (visual_description) → 200
        3. Inject DOWNLOAD_COMPLETE state
        4. POST /api/jobs/{job_id}/subtitle → 200
        5. Poll until failed (describe_video raises ValueError for missing key)
        6. Assert error.code in {"invalid_input", "visual_description_failed"}
        """
        # Step 1: remove the API key so describe_video raises ValueError
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        get_settings.cache_clear()

        app = create_app()

        with TestClient(app, raise_server_exceptions=False) as client:
            # Step 2: create job — prevent download from racing with state injection
            with patch("bilingualsub.api.routes.run_download", _noop_run_download):
                create_resp = client.post(
                    "/api/jobs",
                    json={
                        "source_url": "https://example.com/video.mp4",
                        "processing_mode": "visual_description",
                    },
                )
            assert create_resp.status_code == 200
            job_id = create_resp.json()["job_id"]

            # Step 3: inject DOWNLOAD_COMPLETE state (no mocking of describe_video —
            # let it attempt to fetch the real API key and raise ValueError)
            job = app.state.job_manager.get_job(job_id)
            assert job is not None

            video_path = tmp_path / "video_no_key.mp4"
            video_path.write_bytes(b"fake video")
            audio_path = tmp_path / "audio_no_key.wav"
            audio_path.write_bytes(b"fake audio")

            job.status = JobStatus.DOWNLOAD_COMPLETE
            job.video_duration = 60.0
            job.output_files[FileType.SOURCE_VIDEO] = video_path
            job.output_files[FileType.AUDIO] = audio_path

            # Step 4: trigger subtitle step (no mock — real describe_video will
            # raise ValueError because GEMINI_API_KEY is absent)
            subtitle_resp = client.post(
                f"/api/jobs/{job_id}/subtitle",
                json={"processing_mode": "visual_description"},
            )
            assert subtitle_resp.status_code == 200

            # Step 5: poll until failed
            status_data = _poll_until_terminal(client, job_id)

        # Step 6: verify error
        assert status_data["status"] == "failed", (
            f"Expected failed, got {status_data['status']!r}"
        )
        error = status_data.get("error")
        assert error is not None, "Expected error detail in response"
        # ValueError → "invalid_input"; VisualDescriptionError → "visual_description_failed"
        assert error["code"] in {"invalid_input", "visual_description_failed"}, (
            f"Expected error code 'invalid_input' or 'visual_description_failed', "
            f"got {error['code']!r}"
        )
