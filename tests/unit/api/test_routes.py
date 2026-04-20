"""Tests for API routes."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from bilingualsub.api.app import create_app
from bilingualsub.api.constants import FileType, JobStatus
from bilingualsub.api.jobs import Job, JobManager
from bilingualsub.api.routes import _build_download_filename, _sanitize_filename
from bilingualsub.core.glossary import GlossaryManager


@pytest.fixture
def app(tmp_path):
    """Create a fresh app with manually initialised state."""
    application = create_app()
    application.state.job_manager = JobManager()
    application.state.glossary_manager = GlossaryManager(tmp_path / "glossary.json")
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
            json={"source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert len(data["job_id"]) == 12

    async def test_create_job_invalid_url(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/jobs",
            json={"source_url": "not-a-url"},
        )
        assert response.status_code == 422


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetJobStatus:
    async def test_get_existing_job(self, client: AsyncClient) -> None:
        # First create a job
        create_resp = await client.post(
            "/api/jobs",
            json={"source_url": "https://www.youtube.com/watch?v=test123"},
        )
        job_id = create_resp.json()["job_id"]

        # Then query it
        response = await client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "pending"

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
            json={"source_url": "https://www.youtube.com/watch?v=test123"},
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
            json={"source_url": "https://www.youtube.com/watch?v=test123"},
        )
        job_id = create_resp.json()["job_id"]

        response = await client.post(f"/api/jobs/{job_id}/subtitle")
        assert response.status_code == 422

    async def test_start_subtitle_success(self, client: AsyncClient, app) -> None:
        """Should start subtitle when job is download_complete."""
        create_resp = await client.post(
            "/api/jobs",
            json={"source_url": "https://www.youtube.com/watch?v=test123"},
        )
        job_id = create_resp.json()["job_id"]

        # Manually set job status to download_complete
        job = app.state.job_manager.get_job(job_id)
        job.status = JobStatus.DOWNLOAD_COMPLETE

        response = await client.post(f"/api/jobs/{job_id}/subtitle")
        assert response.status_code == 200
        assert response.json()["status"] == "subtitle_started"
        assert job.glossary_text == ""  # empty glossary yields empty string

    async def test_start_subtitle_with_language_override(
        self, client: AsyncClient, app
    ) -> None:
        """Should update source/target language when triggering subtitle."""
        create_resp = await client.post(
            "/api/jobs",
            json={"source_url": "https://www.youtube.com/watch?v=test123"},
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
        assert job.glossary_text == ""


@pytest.mark.unit
@pytest.mark.asyncio
class TestPartialRetranslate:
    async def test_partial_retranslate_success(self, client: AsyncClient, app) -> None:
        create_resp = await client.post(
            "/api/jobs",
            json={"source_url": "https://www.youtube.com/watch?v=test123"},
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
        call_kwargs = mock_retranslate.call_args.kwargs
        assert call_kwargs["glossary_text"] == ""  # empty glossary

    async def test_partial_retranslate_requires_pipeline_complete(
        self, client: AsyncClient
    ) -> None:
        create_resp = await client.post(
            "/api/jobs",
            json={"source_url": "https://www.youtube.com/watch?v=test123"},
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


def _make_job(
    *,
    title: str = "",
    source_lang: str = "en",
    target_lang: str = "zh-TW",
) -> Job:
    job = Job(id="testjob")
    job.video_title = title
    job.source_lang = source_lang
    job.target_lang = target_lang
    return job


@pytest.mark.unit
class TestSanitizeFilename:
    def test_empty_string_returns_video(self) -> None:
        assert _sanitize_filename("") == "video"

    def test_whitespace_only_returns_video(self) -> None:
        assert _sanitize_filename("   ") == "video"

    def test_strips_illegal_chars(self) -> None:
        assert _sanitize_filename('My: <video> / test"') == "My video  test"

    def test_truncates_to_120_chars(self) -> None:
        long_name = "a" * 200
        assert len(_sanitize_filename(long_name)) == 120

    def test_strips_leading_trailing_dots_and_spaces(self) -> None:
        assert _sanitize_filename("  .hello.  ") == "hello"

    def test_sanitize_all_bad_chars_returns_default(self) -> None:
        result = _sanitize_filename(":::")
        assert result == "video"

    def test_sanitize_dots_only_returns_default(self) -> None:
        result = _sanitize_filename("...")
        assert result == "video"


@pytest.mark.unit
class TestBuildDownloadFilename:
    def test_empty_title_falls_back_to_video(self) -> None:
        job = _make_job(title="", source_lang="en", target_lang="en")
        result = _build_download_filename(job, FileType.SRT)
        assert result == "video (original).srt"

    def test_same_lang_produces_original_suffix(self) -> None:
        job = _make_job(title="My Video", source_lang="en", target_lang="en")
        result = _build_download_filename(job, FileType.SRT)
        assert result == "My Video (original).srt"

    def test_translation_produces_lang_suffix(self) -> None:
        job = _make_job(title="My Video", source_lang="en", target_lang="zh-TW")
        result = _build_download_filename(job, FileType.SRT)
        assert result == "My Video (en_to_zh-TW).srt"

    def test_title_with_illegal_chars_stripped(self) -> None:
        job = _make_job(
            title='My: <video> / test"', source_lang="en", target_lang="zh-TW"
        )
        result = _build_download_filename(job, FileType.SRT)
        assert result == "My video  test (en_to_zh-TW).srt"

    def test_source_video_always_original(self) -> None:
        job = _make_job(title="My Video", source_lang="en", target_lang="zh-TW")
        result = _build_download_filename(job, FileType.SOURCE_VIDEO)
        assert result == "My Video (original).mp4"

    def test_audio_always_original(self) -> None:
        job = _make_job(title="My Video", source_lang="en", target_lang="zh-TW")
        result = _build_download_filename(job, FileType.AUDIO)
        assert result == "My Video (original).mp3"

    def test_ass_with_translation(self) -> None:
        job = _make_job(title="My Video", source_lang="en", target_lang="zh-TW")
        result = _build_download_filename(job, FileType.ASS)
        assert result == "My Video (en_to_zh-TW).ass"

    def test_burned_video_with_translation(self) -> None:
        job = _make_job(title="My Video", source_lang="en", target_lang="zh-TW")
        result = _build_download_filename(job, FileType.VIDEO)
        assert result == "My Video (en_to_zh-TW).mp4"

    def test_empty_source_lang_produces_original(self) -> None:
        job = _make_job(title="My Video", source_lang="", target_lang="zh-TW")
        result = _build_download_filename(job, FileType.SRT)
        assert result == "My Video (original).srt"


@pytest.mark.unit
@pytest.mark.asyncio
class TestGlossaryRoutes:
    async def test_list_empty_glossary(self, client: AsyncClient) -> None:
        response = await client.get("/api/glossary")
        assert response.status_code == 200
        assert response.json() == {"entries": []}

    async def test_add_glossary_entry(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/glossary",
            json={"source": "Agent", "target": "Agent"},
        )
        assert response.status_code == 201
        assert response.json() == {"source": "Agent", "target": "Agent"}

    async def test_add_then_list(self, client: AsyncClient) -> None:
        await client.post("/api/glossary", json={"source": "Agent", "target": "Agent"})
        response = await client.get("/api/glossary")
        entries = response.json()["entries"]
        assert len(entries) == 1
        assert entries[0]["source"] == "Agent"
        assert entries[0]["target"] == "Agent"

    async def test_update_glossary_entry(self, client: AsyncClient) -> None:
        await client.post("/api/glossary", json={"source": "Agent", "target": "Agent"})
        response = await client.put(
            "/api/glossary/Agent",
            json={"source": "Agent", "target": "代理"},
        )
        assert response.status_code == 200
        assert response.json()["target"] == "代理"

    async def test_update_nonexistent_returns_404(self, client: AsyncClient) -> None:
        response = await client.put(
            "/api/glossary/nope",
            json={"source": "nope", "target": "value"},
        )
        assert response.status_code == 404

    async def test_delete_glossary_entry(self, client: AsyncClient) -> None:
        await client.post("/api/glossary", json={"source": "Agent", "target": "Agent"})
        response = await client.delete("/api/glossary/Agent")
        assert response.status_code == 204
        list_response = await client.get("/api/glossary")
        assert list_response.json()["entries"] == []

    async def test_delete_nonexistent_returns_404(self, client: AsyncClient) -> None:
        response = await client.delete("/api/glossary/nope")
        assert response.status_code == 404

    async def test_add_empty_source_returns_400(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/glossary",
            json={"source": "", "target": "value"},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "GLOSSARY_ERROR"
