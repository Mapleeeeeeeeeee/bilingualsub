"""Tests for API routes."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from bilingualsub.api.app import create_app
from bilingualsub.api.constants import FileType, JobStatus
from bilingualsub.api.jobs import JobManager


@pytest.fixture
def app():
    """Create a fresh app with manually initialised state."""
    application = create_app()
    application.state.job_manager = JobManager()
    return application


@pytest.fixture
async def client(app):
    """Async HTTP client for testing (pipeline mocked to prevent side effects)."""
    with (
        patch("bilingualsub.api.routes.run_download", new_callable=AsyncMock),
        patch("bilingualsub.api.routes.run_subtitle", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


@pytest.mark.unit
@pytest.mark.asyncio
class TestHealthEndpoint:
    async def test_health_check(self, client: AsyncClient) -> None:
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateJob:
    async def test_create_job_valid(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/jobs",
            json={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert len(data["job_id"]) == 12

    async def test_create_job_invalid_url(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/jobs",
            json={"youtube_url": "not-a-url"},
        )
        assert response.status_code == 422


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetJobStatus:
    async def test_get_existing_job(self, client: AsyncClient) -> None:
        # First create a job
        create_resp = await client.post(
            "/api/jobs",
            json={"youtube_url": "https://www.youtube.com/watch?v=test123"},
        )
        job_id = create_resp.json()["job_id"]

        # Then query it
        response = await client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "status" in data

    async def test_get_nonexistent_job(self, client: AsyncClient) -> None:
        response = await client.get("/api/jobs/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "job_not_found"


@pytest.mark.unit
@pytest.mark.asyncio
class TestDownload:
    async def test_download_invalid_file_type(self, client: AsyncClient) -> None:
        # Create a job first
        create_resp = await client.post(
            "/api/jobs",
            json={"youtube_url": "https://www.youtube.com/watch?v=test123"},
        )
        job_id = create_resp.json()["job_id"]

        response = await client.get(f"/api/jobs/{job_id}/download/invalid")
        assert response.status_code == 422

    async def test_download_nonexistent_job(self, client: AsyncClient) -> None:
        response = await client.get("/api/jobs/nonexistent/download/srt")
        assert response.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
class TestErrorResponseFormat:
    async def test_404_error_format(self, client: AsyncClient) -> None:
        response = await client.get("/api/jobs/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "code" in data
        assert "message" in data
        # detail can be null
        assert "detail" in data


@pytest.mark.unit
@pytest.mark.asyncio
class TestStartSubtitle:
    async def test_start_subtitle_wrong_status(self, client: AsyncClient, app) -> None:
        """Should return 422 when job is not in download_complete state."""
        create_resp = await client.post(
            "/api/jobs",
            json={"youtube_url": "https://www.youtube.com/watch?v=test123"},
        )
        job_id = create_resp.json()["job_id"]

        response = await client.post(f"/api/jobs/{job_id}/subtitle")
        assert response.status_code == 422

    async def test_start_subtitle_success(self, client: AsyncClient, app) -> None:
        """Should start subtitle when job is download_complete."""
        create_resp = await client.post(
            "/api/jobs",
            json={"youtube_url": "https://www.youtube.com/watch?v=test123"},
        )
        job_id = create_resp.json()["job_id"]

        # Manually set job status to download_complete
        job = app.state.job_manager.get_job(job_id)
        job.status = JobStatus.DOWNLOAD_COMPLETE

        response = await client.post(f"/api/jobs/{job_id}/subtitle")
        assert response.status_code == 200
        assert response.json()["status"] == "subtitle_started"

    async def test_start_subtitle_with_language_override(
        self, client: AsyncClient, app
    ) -> None:
        """Should update source/target language when triggering subtitle."""
        create_resp = await client.post(
            "/api/jobs",
            json={"youtube_url": "https://www.youtube.com/watch?v=test123"},
        )
        job_id = create_resp.json()["job_id"]

        job = app.state.job_manager.get_job(job_id)
        job.status = JobStatus.DOWNLOAD_COMPLETE
        job.source_lang = "en"
        job.target_lang = "zh-TW"

        response = await client.post(
            f"/api/jobs/{job_id}/subtitle",
            json={"source_lang": "ja", "target_lang": "ko"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "subtitle_started"
        assert job.source_lang == "ja"
        assert job.target_lang == "ko"


@pytest.mark.unit
@pytest.mark.asyncio
class TestPartialRetranslate:
    async def test_partial_retranslate_success(self, client: AsyncClient, app) -> None:
        create_resp = await client.post(
            "/api/jobs",
            json={"youtube_url": "https://www.youtube.com/watch?v=test123"},
        )
        job_id = create_resp.json()["job_id"]

        job = app.state.job_manager.get_job(job_id)
        job.output_files[FileType.SOURCE_VIDEO] = Path("/tmp/source.mp4")
        job.source_lang = "en"
        job.target_lang = "zh-TW"

        with patch("bilingualsub.api.routes.retranslate_entries") as mock_retranslate:
            mock_retranslate.return_value = {2: "修正版第二句"}
            response = await client.post(
                f"/api/jobs/{job_id}/retranslate",
                json={
                    "selected_indices": [2],
                    "entries": [
                        {"index": 1, "original": "Line 1", "translated": "第一句"},
                        {"index": 2, "original": "Line 2", "translated": "第二句"},
                    ],
                    "user_context": "主題是太空探索",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == [{"index": 2, "translated": "修正版第二句"}]

    async def test_partial_retranslate_requires_pipeline_complete(
        self, client: AsyncClient
    ) -> None:
        create_resp = await client.post(
            "/api/jobs",
            json={"youtube_url": "https://www.youtube.com/watch?v=test123"},
        )
        job_id = create_resp.json()["job_id"]

        response = await client.post(
            f"/api/jobs/{job_id}/retranslate",
            json={
                "selected_indices": [1],
                "entries": [
                    {"index": 1, "original": "Line 1", "translated": "第一句"},
                ],
            },
        )
        assert response.status_code == 422
