"""Tests for the async pipeline runner."""

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from bilingualsub.api.constants import FileType, JobStatus, SSEEvent
from bilingualsub.api.jobs import Job
from bilingualsub.api.pipeline import run_download, run_pipeline, run_subtitle
from bilingualsub.core.downloader import DownloadError, VideoMetadata
from bilingualsub.core.subtitle import Subtitle, SubtitleEntry


def _make_job_with_time_range() -> Job:
    return Job(
        id="test456",
        youtube_url="https://youtube.com/watch?v=test",
        source_lang="en",
        target_lang="zh-TW",
        start_time=10.0,
        end_time=30.0,
    )


def _make_job() -> Job:
    return Job(
        id="test123",
        youtube_url="https://youtube.com/watch?v=test",
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
    @patch("bilingualsub.api.pipeline.burn_subtitles")
    @patch("bilingualsub.api.pipeline.serialize_bilingual_ass")
    @patch("bilingualsub.api.pipeline.serialize_srt")
    @patch("bilingualsub.api.pipeline.merge_subtitles")
    @patch("bilingualsub.api.pipeline.translate_subtitle")
    @patch("bilingualsub.api.pipeline.transcribe_audio")
    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.download_youtube_video")
    async def test_successful_pipeline(
        self,
        mock_download,
        mock_extract_audio,
        mock_transcribe,
        mock_translate,
        mock_merge,
        mock_serialize_srt,
        mock_serialize_ass,
        mock_burn,
        tmp_path: Path,
    ) -> None:
        sub = _make_subtitle()
        mock_download.return_value = _make_metadata()
        mock_transcribe.return_value = sub
        mock_translate.return_value = sub
        mock_merge.return_value = sub.entries
        mock_serialize_srt.return_value = "1\n00:00:00,000 --> 00:00:04,000\nLine 1"
        mock_serialize_ass.return_value = "[Script Info]\n..."
        mock_burn.return_value = tmp_path / "output.mp4"

        job = _make_job()
        await run_pipeline(job)

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

    @patch("bilingualsub.api.pipeline.download_youtube_video")
    async def test_download_error(self, mock_download) -> None:
        mock_download.side_effect = DownloadError("Network error")

        job = _make_job()
        await run_pipeline(job)

        events = []
        while not job.event_queue.empty():
            events.append(job.event_queue.get_nowait())

        error_events = [e for e in events if e["event"] == SSEEvent.ERROR]
        assert len(error_events) == 1
        assert error_events[0]["data"]["code"] == "download_failed"
        assert job.status == JobStatus.FAILED

    @patch("bilingualsub.api.pipeline.burn_subtitles")
    @patch("bilingualsub.api.pipeline.serialize_bilingual_ass")
    @patch("bilingualsub.api.pipeline.serialize_srt")
    @patch("bilingualsub.api.pipeline.merge_subtitles")
    @patch("bilingualsub.api.pipeline.translate_subtitle")
    @patch("bilingualsub.api.pipeline.transcribe_audio")
    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.download_youtube_video")
    async def test_transcribe_receives_audio_path(
        self,
        mock_download,
        mock_extract_audio,
        mock_transcribe,
        mock_translate,
        mock_merge,
        mock_serialize_srt,
        mock_serialize_ass,
        mock_burn,
    ) -> None:
        """Transcribe should receive extracted audio path, not video path."""
        sub = _make_subtitle()
        mock_download.return_value = _make_metadata()
        mock_transcribe.return_value = sub
        mock_translate.return_value = sub
        mock_merge.return_value = sub.entries
        mock_serialize_srt.return_value = "1\n00:00:00,000 --> 00:00:04,000\nLine 1"
        mock_serialize_ass.return_value = "[Script Info]\n..."

        job = _make_job()
        await run_pipeline(job)

        # Verify extract_audio was called with video path
        extract_call_args = mock_extract_audio.call_args[0]
        assert extract_call_args[0].name == "video.mp4"
        assert extract_call_args[1].name == "audio.mp3"

        # Verify transcribe_audio received audio path, NOT video path
        transcribe_call_args = mock_transcribe.call_args
        audio_arg = transcribe_call_args[0][0]
        assert audio_arg.name == "audio.mp3"

    @patch("bilingualsub.api.pipeline.burn_subtitles")
    @patch("bilingualsub.api.pipeline.serialize_bilingual_ass")
    @patch("bilingualsub.api.pipeline.serialize_srt")
    @patch("bilingualsub.api.pipeline.merge_subtitles")
    @patch("bilingualsub.api.pipeline.translate_subtitle")
    @patch("bilingualsub.api.pipeline.transcribe_audio")
    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.trim_video")
    @patch("bilingualsub.api.pipeline.download_youtube_video")
    async def test_pipeline_with_time_range_calls_trim(
        self,
        mock_download,
        mock_trim,
        mock_extract_audio,
        mock_transcribe,
        mock_translate,
        mock_merge,
        mock_serialize_srt,
        mock_serialize_ass,
        mock_burn,
    ) -> None:
        """Given job with time range, download_youtube_video should receive time parameters."""
        sub = _make_subtitle()
        mock_download.return_value = _make_metadata()
        mock_transcribe.return_value = sub
        mock_translate.return_value = sub
        mock_merge.return_value = sub.entries
        mock_serialize_srt.return_value = "1\n00:00:00,000 --> 00:00:04,000\nLine 1"
        mock_serialize_ass.return_value = "[Script Info]\n..."

        job = _make_job_with_time_range()
        await run_pipeline(job)

        # Verify download was called with time parameters
        mock_download.assert_called_once()
        call_kwargs = mock_download.call_args[1]
        assert call_kwargs["start_time"] == 10.0
        assert call_kwargs["end_time"] == 30.0

        # Verify trim_video was NOT called (trimming happens during download now)
        mock_trim.assert_not_called()

        assert job.status == JobStatus.COMPLETED

    @patch("bilingualsub.api.pipeline.burn_subtitles")
    @patch("bilingualsub.api.pipeline.serialize_bilingual_ass")
    @patch("bilingualsub.api.pipeline.serialize_srt")
    @patch("bilingualsub.api.pipeline.merge_subtitles")
    @patch("bilingualsub.api.pipeline.translate_subtitle")
    @patch("bilingualsub.api.pipeline.transcribe_audio")
    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.trim_video")
    @patch("bilingualsub.api.pipeline.download_youtube_video")
    async def test_pipeline_without_time_range_skips_trim(
        self,
        mock_download,
        mock_trim,
        mock_extract_audio,
        mock_transcribe,
        mock_translate,
        mock_merge,
        mock_serialize_srt,
        mock_serialize_ass,
        mock_burn,
    ) -> None:
        """Given job without time range, pipeline should NOT call trim_video."""
        sub = _make_subtitle()
        mock_download.return_value = _make_metadata()
        mock_transcribe.return_value = sub
        mock_translate.return_value = sub
        mock_merge.return_value = sub.entries
        mock_serialize_srt.return_value = "1\n00:00:00,000 --> 00:00:04,000\nLine 1"
        mock_serialize_ass.return_value = "[Script Info]\n..."

        job = _make_job()
        await run_pipeline(job)

        mock_trim.assert_not_called()
        assert job.status == JobStatus.COMPLETED


@pytest.mark.unit
@pytest.mark.asyncio
class TestRunDownload:
    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.download_youtube_video")
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
    @patch("bilingualsub.api.pipeline.download_youtube_video")
    async def test_run_download_saves_metadata(
        self, mock_download, mock_extract_audio
    ) -> None:
        """run_download should save video dimensions to job."""
        mock_download.return_value = _make_metadata()

        job = _make_job()
        await run_download(job)

        assert job.video_width == 1920
        assert job.video_height == 1080


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
