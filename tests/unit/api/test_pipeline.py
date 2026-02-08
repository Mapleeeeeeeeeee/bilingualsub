"""Tests for the async pipeline runner."""

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from bilingualsub.api.constants import JobStatus, SSEEvent
from bilingualsub.api.jobs import Job
from bilingualsub.api.pipeline import run_pipeline
from bilingualsub.core.downloader import DownloadError, VideoMetadata
from bilingualsub.core.subtitle import Subtitle, SubtitleEntry


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
