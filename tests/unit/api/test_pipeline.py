"""Tests for the async pipeline runner."""

from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bilingualsub.api.constants import FileType, JobStatus, SSEEvent
from bilingualsub.api.jobs import Job
from bilingualsub.api.pipeline import run_burn, run_download, run_subtitle
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


# ---------------------------------------------------------------------------
# run_burn — watermark + intro + concat + degradation
# ---------------------------------------------------------------------------


def _make_burn_job(tmp_path: Path, *, channel: str = "TestChannel") -> Job:
    """Return a job pre-populated with the output files run_burn expects."""
    job = Job(
        id="burn001",
        source_url="https://youtube.com/watch?v=abc",
        source_lang="en",
        target_lang="zh-TW",
        video_width=1920,
        video_height=1080,
        video_fps=30.0,
        video_title="Test Video",
        video_channel=channel,
        video_channel_url="https://youtube.com/@TestChannel" if channel else "",
    )
    # run_burn reads SOURCE_VIDEO to determine work_dir
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")
    job.output_files[FileType.SOURCE_VIDEO] = video_path
    return job


@pytest.mark.unit
@pytest.mark.asyncio
class TestRunBurn:
    """Tests for run_burn watermark, intro, concat, and degradation logic."""

    @patch("bilingualsub.api.pipeline.concat_videos")
    @patch("bilingualsub.api.pipeline.generate_intro")
    @patch("bilingualsub.api.pipeline.burn_subtitles")
    async def test_when_channel_set_then_burn_called_with_watermark_and_intro_called(
        self,
        mock_burn: object,
        mock_intro: object,
        mock_concat: object,
        tmp_path: Path,
    ) -> None:
        """When video_channel is set, burn_subtitles receives watermark_text and generate_intro is called."""
        mock_burn.return_value = tmp_path / "output.mp4"
        mock_intro.return_value = tmp_path / "intro.mp4"
        mock_concat.return_value = tmp_path / "final.mp4"

        job = _make_burn_job(tmp_path, channel="3Blue1Brown")
        srt = "1\n00:00:00,000 --> 00:00:04,000\nHello\n"

        await run_burn(job, srt)

        # burn_subtitles must have received watermark_text with the channel name
        mock_burn.assert_called_once()
        call_kwargs = mock_burn.call_args.kwargs
        assert call_kwargs["watermark_text"] == "Source: 3Blue1Brown"

        # generate_intro must have been called with expected channel args
        mock_intro.assert_called_once()
        intro_kwargs = mock_intro.call_args.kwargs
        assert intro_kwargs["channel"] == "3Blue1Brown"
        assert intro_kwargs["channel_url"] == "https://youtube.com/@TestChannel"

        # concat_videos must have been called to combine intro + main
        mock_concat.assert_called_once()

        # Final VIDEO output should be the concatenated file
        assert job.output_files[FileType.VIDEO] == tmp_path / "final.mp4"
        assert job.status == JobStatus.COMPLETED

    @patch("bilingualsub.api.pipeline.concat_videos")
    @patch("bilingualsub.api.pipeline.generate_intro")
    @patch("bilingualsub.api.pipeline.burn_subtitles")
    async def test_when_channel_empty_then_burn_called_without_watermark_and_intro_skipped(
        self,
        mock_burn: object,
        mock_intro: object,
        mock_concat: object,
        tmp_path: Path,
    ) -> None:
        """When video_channel is empty, watermark_text=None and generate_intro is never called."""
        mock_burn.return_value = tmp_path / "output.mp4"

        job = _make_burn_job(tmp_path, channel="")
        srt = "1\n00:00:00,000 --> 00:00:04,000\nHello\n"

        await run_burn(job, srt)

        mock_burn.assert_called_once()
        call_kwargs = mock_burn.call_args.kwargs
        assert call_kwargs["watermark_text"] is None

        mock_intro.assert_not_called()
        mock_concat.assert_not_called()

        assert job.output_files[FileType.VIDEO] == tmp_path / "output.mp4"
        assert job.status == JobStatus.COMPLETED

    @patch("bilingualsub.api.pipeline.logger")
    @patch("bilingualsub.api.pipeline.concat_videos")
    @patch("bilingualsub.api.pipeline.generate_intro")
    @patch("bilingualsub.api.pipeline.burn_subtitles")
    async def test_when_generate_intro_fails_then_concat_skipped_and_job_completes(
        self,
        mock_burn: object,
        mock_intro: object,
        mock_concat: object,
        mock_logger: object,
        tmp_path: Path,
    ) -> None:
        """When generate_intro raises FFmpegError, concat is skipped but job still COMPLETED."""
        mock_log = MagicMock()
        mock_logger.bind.return_value = mock_log  # type: ignore[union-attr]

        mock_burn.return_value = tmp_path / "output.mp4"
        mock_intro.side_effect = FFmpegError("lavfi failed")

        job = _make_burn_job(tmp_path, channel="BadChannel")
        srt = "1\n00:00:00,000 --> 00:00:04,000\nHello\n"

        await run_burn(job, srt)

        mock_concat.assert_not_called()
        # Job still completes - no error event
        assert job.status == JobStatus.COMPLETED
        # VIDEO should fall back to output.mp4, not final.mp4
        assert job.output_files[FileType.VIDEO] == tmp_path / "output.mp4"
        # Degradation must be logged as a warning
        mock_log.warning.assert_called_once_with(
            "intro_generation_failed", error="lavfi failed"
        )

    @patch("bilingualsub.api.pipeline.logger")
    @patch("bilingualsub.api.pipeline.concat_videos")
    @patch("bilingualsub.api.pipeline.generate_intro")
    @patch("bilingualsub.api.pipeline.burn_subtitles")
    async def test_when_concat_fails_then_job_completes_with_output_video(
        self,
        mock_burn: object,
        mock_intro: object,
        mock_concat: object,
        mock_logger: object,
        tmp_path: Path,
    ) -> None:
        """When concat_videos raises FFmpegError, job still COMPLETED and VIDEO = output.mp4."""
        mock_log = MagicMock()
        mock_logger.bind.return_value = mock_log  # type: ignore[union-attr]

        mock_burn.return_value = tmp_path / "output.mp4"
        mock_intro.return_value = tmp_path / "intro.mp4"
        mock_concat.side_effect = FFmpegError("concat failed")

        job = _make_burn_job(tmp_path, channel="SomeChannel")
        srt = "1\n00:00:00,000 --> 00:00:04,000\nHello\n"

        await run_burn(job, srt)

        assert job.status == JobStatus.COMPLETED
        assert job.output_files[FileType.VIDEO] == tmp_path / "output.mp4"
        # Degradation must be logged as a warning
        mock_log.warning.assert_called_once_with("concat_failed", error="concat failed")


# ---------------------------------------------------------------------------
# run_download - channel metadata propagation
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestRunDownloadChannel:
    """Tests for channel metadata saved by run_download."""

    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.download_video")
    async def test_when_youtube_url_with_channel_then_job_stores_channel(
        self,
        mock_download: object,
        mock_extract_audio: object,
    ) -> None:
        """run_download must save video_channel from metadata.channel."""
        metadata = VideoMetadata(
            title="Test",
            duration=60.0,
            width=1920,
            height=1080,
            fps=30.0,
            channel="3Blue1Brown",
            channel_url="https://www.youtube.com/channel/UCYO_jab_esuFRV4b17AJtAw",
        )
        mock_download.return_value = metadata

        job = _make_job()
        await run_download(job)

        assert job.video_channel == "3Blue1Brown"

    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.download_video")
    async def test_when_youtube_url_with_channel_then_channel_url_stored(
        self,
        mock_download: object,
        mock_extract_audio: object,
    ) -> None:
        """run_download must save video_channel_url when source is YouTube."""
        channel_url = "https://www.youtube.com/channel/UCYO_jab_esuFRV4b17AJtAw"
        metadata = VideoMetadata(
            title="Test",
            duration=60.0,
            width=1920,
            height=1080,
            fps=30.0,
            channel="3Blue1Brown",
            channel_url=channel_url,
        )
        mock_download.return_value = metadata

        job = _make_job()  # source_url contains youtube.com
        await run_download(job)

        assert job.video_channel_url == channel_url

    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.download_video")
    async def test_when_local_upload_then_video_channel_is_empty(
        self,
        mock_download: object,
        mock_extract_audio: object,
        tmp_path: Path,
    ) -> None:
        """Local upload jobs must have video_channel = '' after run_download."""
        local_video = tmp_path / "local.mp4"
        local_video.write_bytes(b"fake")

        job = Job(
            id="local01",
            source_url="",
            source_lang="en",
            target_lang="zh-TW",
            local_video_path=local_video,
        )

        with patch(
            "bilingualsub.api.pipeline.extract_video_metadata",
            return_value={
                "title": "Local",
                "duration": 30.0,
                "width": 1280,
                "height": 720,
                "fps": 24.0,
            },
        ):
            await run_download(job)

        assert job.video_channel == ""

    @patch("bilingualsub.api.pipeline.extract_audio")
    @patch("bilingualsub.api.pipeline.download_video")
    async def test_when_non_youtube_url_then_channel_url_cleared(
        self,
        mock_download: object,
        mock_extract_audio: object,
    ) -> None:
        """Non-YouTube source must clear video_channel_url even if metadata has channel_url."""
        metadata = VideoMetadata(
            title="Test",
            duration=60.0,
            width=1920,
            height=1080,
            fps=30.0,
            channel="BilibiliUser",
            channel_url="https://space.bilibili.com/12345",
        )
        mock_download.return_value = metadata

        job = Job(
            id="bilibili01",
            source_url="https://www.bilibili.com/video/BV1234",
            source_lang="zh",
            target_lang="en",
        )
        await run_download(job)

        assert job.video_channel == "BilibiliUser"
        assert job.video_channel_url == ""  # Non-YouTube → cleared
