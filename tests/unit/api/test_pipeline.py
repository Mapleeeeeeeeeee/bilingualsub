"""Tests for the async pipeline runner."""

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from bilingualsub.api.constants import FileType, JobStatus, ProcessingMode, SSEEvent
from bilingualsub.api.jobs import Job
from bilingualsub.api.pipeline import run_download, run_subtitle
from bilingualsub.core.downloader import DownloadError, VideoMetadata
from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.utils.ffmpeg import FFmpegError


def _make_job_with_time_range() -> Job:
    return Job(
        id="test456",
        source_url="https://youtube.com/watch?v=test",
        source_lang="en",
        target_lang="zh-TW",
        start_time=10.0,
        end_time=30.0,
    )


def _make_job() -> Job:
    return Job(
        id="test123",
        source_url="https://youtube.com/watch?v=test",
        source_lang="en",
        target_lang="zh-TW",
    )


def _make_subtitle(n: int = 2) -> Subtitle:
    entries = [
        SubtitleEntry(
            index=i + 1,
            start=timedelta(seconds=i * 5),
            end=timedelta(seconds=i * 5 + 4),
            text=f"Line {i + 1}",
        )
        for i in range(n)
    ]
    return Subtitle(entries=entries)


def _make_metadata() -> VideoMetadata:
    return VideoMetadata(
        title="Test Video",
        duration=60.0,
        width=1920,
        height=1080,
        fps=30.0,
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestRunPipeline:
    @patch("bilingualsub.api.pipeline.serialize_bilingual_ass")
    @patch("bilingualsub.api.pipeline.serialize_srt")
    @patch("bilingualsub.api.pipeline.merge_subtitles")
    @patch("bilingualsub.api.pipeline.translate_subtitle")
    @patch("bilingualsub.api.pipeline.transcribe_audio")
    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.download_video")
    async def test_successful_pipeline(
        self,
        mock_download,
        mock_extract_audio,
        mock_transcribe,
        mock_translate,
        mock_merge,
        mock_serialize_srt,
        mock_serialize_ass,
        tmp_path: Path,
    ) -> None:
        sub = _make_subtitle()
        mock_download.return_value = _make_metadata()
        mock_transcribe.return_value = sub
        mock_translate.return_value = sub
        mock_merge.return_value = sub.entries
        mock_serialize_srt.return_value = "1\n00:00:00,000 --> 00:00:04,000\nLine 1"
        mock_serialize_ass.return_value = "[Script Info]\n..."

        job = _make_job()
        await run_download(job)
        await run_subtitle(job)

        # Collect all events
        events = []
        while not job.event_queue.empty():
            events.append(job.event_queue.get_nowait())

        # Should have progress events + complete
        event_types = [e["event"] for e in events]
        assert SSEEvent.PROGRESS in event_types
        assert SSEEvent.COMPLETE in event_types
        assert SSEEvent.ERROR not in event_types
        assert job.status == JobStatus.COMPLETED

        # Verify translate_subtitle received on_progress callback
        translate_call_kwargs = mock_translate.call_args.kwargs
        assert "on_progress" in translate_call_kwargs
        assert callable(translate_call_kwargs["on_progress"])

    @patch("bilingualsub.api.pipeline.download_video")
    async def test_download_error(self, mock_download) -> None:
        mock_download.side_effect = DownloadError("Network error")

        job = _make_job()
        await run_download(job)

        events = []
        while not job.event_queue.empty():
            events.append(job.event_queue.get_nowait())

        error_events = [e for e in events if e["event"] == SSEEvent.ERROR]
        assert len(error_events) == 1
        assert error_events[0]["data"]["code"] == "download_failed"
        assert job.status == JobStatus.FAILED

    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.download_video")
    async def test_download_with_time_range_completes(
        self,
        mock_download,
        mock_extract_audio,
    ) -> None:
        """Given job with time range, run_download produces expected output files."""
        mock_download.return_value = _make_metadata()

        job = _make_job_with_time_range()
        await run_download(job)

        assert job.status == JobStatus.DOWNLOAD_COMPLETE
        assert FileType.SOURCE_VIDEO in job.output_files
        assert FileType.AUDIO in job.output_files

    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.download_video")
    async def test_download_without_time_range_completes(
        self,
        mock_download,
        mock_extract_audio,
    ) -> None:
        """Given job without time range, run_download produces expected output files."""
        mock_download.return_value = _make_metadata()

        job = _make_job()
        await run_download(job)

        assert job.status == JobStatus.DOWNLOAD_COMPLETE
        assert FileType.SOURCE_VIDEO in job.output_files


@pytest.mark.unit
@pytest.mark.asyncio
class TestRunDownload:
    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.download_video")
    async def test_run_download_sends_download_complete(
        self, mock_download, mock_extract_audio
    ) -> None:
        """run_download should send download_complete event."""
        mock_download.return_value = _make_metadata()

        job = _make_job()
        await run_download(job)

        events = []
        while not job.event_queue.empty():
            events.append(job.event_queue.get_nowait())

        event_types = [e["event"] for e in events]
        assert SSEEvent.DOWNLOAD_COMPLETE in event_types
        assert SSEEvent.COMPLETE not in event_types
        assert job.status == JobStatus.DOWNLOAD_COMPLETE

    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.download_video")
    async def test_run_download_saves_metadata(
        self, mock_download, mock_extract_audio
    ) -> None:
        """run_download should save video dimensions to job."""
        mock_download.return_value = _make_metadata()

        job = _make_job()
        await run_download(job)

        assert job.video_width == 1920
        assert job.video_height == 1080

    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.download_video")
    async def test_run_download_extract_audio_failure_sends_error(
        self, mock_download, mock_extract_audio
    ) -> None:
        """When extract_audio raises FFmpegError, job transitions to FAILED."""
        mock_download.return_value = _make_metadata()
        mock_extract_audio.side_effect = FFmpegError("ffmpeg segfault")

        job = _make_job()
        await run_download(job)

        events = []
        while not job.event_queue.empty():
            events.append(job.event_queue.get_nowait())

        error_events = [e for e in events if e["event"] == SSEEvent.ERROR]
        assert len(error_events) == 1
        assert error_events[0]["data"]["code"] == "burn_failed"
        assert "ffmpeg segfault" in error_events[0]["data"]["detail"]
        assert job.status == JobStatus.FAILED

    @patch("bilingualsub.api.pipeline.download_video")
    async def test_run_download_no_audio_switches_to_visual_description(
        self, mock_download
    ) -> None:
        """When video has no audio stream, auto-switch to visual description mode."""
        metadata = VideoMetadata(
            title="Silent Video",
            duration=60.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=False,
        )
        mock_download.return_value = metadata

        job = _make_job()
        assert job.processing_mode == ProcessingMode.SUBTITLE

        await run_download(job)

        assert job.processing_mode == ProcessingMode.VISUAL_DESCRIPTION
        assert job.status == JobStatus.DOWNLOAD_COMPLETE

    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.download_video")
    async def test_run_download_with_audio_keeps_subtitle_mode(
        self, mock_download, mock_extract_audio
    ) -> None:
        """When video has audio stream, processing mode stays as SUBTITLE."""
        metadata = VideoMetadata(
            title="Normal Video",
            duration=60.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        )
        mock_download.return_value = metadata

        job = _make_job()
        await run_download(job)

        assert job.processing_mode == ProcessingMode.SUBTITLE
        assert job.status == JobStatus.DOWNLOAD_COMPLETE
        mock_extract_audio.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
class TestRunSubtitle:
    @patch("bilingualsub.api.pipeline.serialize_bilingual_ass")
    @patch("bilingualsub.api.pipeline.serialize_srt")
    @patch("bilingualsub.api.pipeline.merge_subtitles")
    @patch("bilingualsub.api.pipeline.translate_subtitle")
    @patch("bilingualsub.api.pipeline.transcribe_audio")
    async def test_run_subtitle_sends_complete(
        self,
        mock_transcribe,
        mock_translate,
        mock_merge,
        mock_srt,
        mock_ass,
        tmp_path,
    ) -> None:
        """run_subtitle should send complete event."""
        sub = _make_subtitle()
        mock_transcribe.return_value = sub
        mock_translate.return_value = sub
        mock_merge.return_value = sub.entries
        mock_srt.return_value = "1\n00:00:00,000 --> 00:00:04,000\nLine 1"
        mock_ass.return_value = "[Script Info]\n..."

        job = _make_job()
        # Set up job as if download phase completed
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")
        job.output_files[FileType.AUDIO] = audio_path
        job.output_files[FileType.SOURCE_VIDEO] = video_path
        job.video_width = 1920
        job.video_height = 1080

        await run_subtitle(job)

        events = []
        while not job.event_queue.empty():
            events.append(job.event_queue.get_nowait())

        event_types = [e["event"] for e in events]
        assert SSEEvent.COMPLETE in event_types
        assert job.status == JobStatus.COMPLETED
