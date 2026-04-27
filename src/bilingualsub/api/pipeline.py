"""Async pipeline runner that orchestrates core modules."""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from bilingualsub.api.constants import (
    FileType,
    JobStatus,
    ProcessingMode,
    SSEEvent,
    SubtitleSource,
)
from bilingualsub.api.errors import PipelineError

if TYPE_CHECKING:
    from collections.abc import Callable

    from bilingualsub.api.jobs import Job
from bilingualsub.core import (
    DownloadError,
    Subtitle,
    TranscriptionError,
    TranslationError,
    VideoMetadata,
    VisualDescriptionError,
    describe_video,
    download_video,
    merge_subtitles,
    transcribe_audio,
    translate_subtitle,
)
from bilingualsub.core.subtitle_fetcher import fetch_manual_subtitle
from bilingualsub.formats import serialize_bilingual_ass, serialize_srt
from bilingualsub.utils import (
    FFmpegError,
    burn_subtitles,
    extract_audio,
    extract_video_metadata,
    trim_video,
)

logger = structlog.get_logger()

# Maps core errors to (error_code, user_message) for PipelineError
_ERROR_MAP: dict[type, tuple[str, str]] = {
    DownloadError: ("download_failed", "Failed to download video"),
    TranscriptionError: ("transcription_failed", "Failed to transcribe audio"),
    TranslationError: ("translation_failed", "Failed to translate subtitles"),
    FFmpegError: ("burn_failed", "Failed to burn subtitles into video"),
    VisualDescriptionError: (
        "visual_description_failed",
        "Failed to analyze video content",
    ),
    ValueError: ("invalid_input", "Invalid input"),
}


def _send_progress(
    job: Job,
    status: JobStatus,
    progress: float,
    current_step: str,
    message: str,
    extra: dict[str, object] | None = None,
) -> None:
    """Update job state and enqueue an SSE progress event."""
    job.status = status
    job.progress = progress
    job.current_step = current_step
    data: dict[str, object] = {
        "status": str(status),
        "progress": progress,
        "current_step": current_step,
        "message": message,
    }
    if extra:
        data.update(extra)
    job.event_queue.put_nowait(
        {
            "event": SSEEvent.PROGRESS,
            "data": data,
        }
    )


def _send_error(job: Job, code: str, message: str, detail: str) -> None:
    """Update job state and enqueue an SSE error event."""
    job.status = JobStatus.FAILED
    job.error_code = code
    job.error_message = message
    job.error_detail = detail
    job.event_queue.put_nowait(
        {
            "event": SSEEvent.ERROR,
            "data": {"code": code, "message": message, "detail": detail},
        }
    )


def _send_complete(job: Job) -> None:
    """Update job state and enqueue an SSE complete event."""
    job.status = JobStatus.COMPLETED
    job.progress = 100.0
    job.event_queue.put_nowait(
        {
            "event": SSEEvent.COMPLETE,
            "data": {"status": "completed", "progress": 100},
        }
    )


def _to_pipeline_error(exc: Exception) -> PipelineError:
    """Convert a core module exception to PipelineError."""
    for exc_type, (code, message) in _ERROR_MAP.items():
        if isinstance(exc, exc_type):
            return PipelineError(code, message, detail=str(exc))
    return PipelineError(
        "pipeline_failed", "Unexpected pipeline error", detail=str(exc)
    )


def _make_translate_progress_cb(job: Job) -> Callable[[int, int], None]:
    """Create a progress callback for the translation step."""

    def _on_progress(completed: int, total: int) -> None:
        pct = 50.0 + (completed / total) * 20.0 if total > 0 else 50.0
        _send_progress(
            job,
            JobStatus.TRANSLATING,
            pct,
            "translate",
            f"Translating subtitles ({completed}/{total})",
        )

    return _on_progress


def _make_rate_limit_cb(job: Job) -> Callable[[float, int, int], None]:
    """Create a callback for rate limit notifications."""

    def _on_rate_limit(retry_after: float, attempt: int, max_retries: int) -> None:
        _send_progress(
            job,
            JobStatus.TRANSLATING,
            job.progress,
            "translate",
            f"API rate limited, retrying in {retry_after:.0f}s "
            f"(attempt {attempt}/{max_retries})",
        )

    return _on_rate_limit


async def _trim_if_needed(
    job: Job,
    video_path: Path,
    work_dir: Path,
    metadata_duration: float,
    log: structlog.stdlib.BoundLogger,
) -> Path:
    """Trim video if time range is specified, returning the (possibly new) path."""
    if job.start_time is None and job.end_time is None:
        return video_path

    _send_progress(job, JobStatus.DOWNLOADING, 12.0, "trim", "Trimming video")
    t0 = time.monotonic()
    trimmed_path = work_dir / "video_trimmed.mp4"
    start = job.start_time if job.start_time is not None else 0.0
    end = job.end_time if job.end_time is not None else metadata_duration
    await asyncio.to_thread(trim_video, video_path, trimmed_path, start, end)
    log.info(
        "step_done",
        step="trim",
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
    return trimmed_path


async def _extract_audio_step(
    job: Job,
    video_path: Path,
    work_dir: Path,
    log: structlog.stdlib.BoundLogger,
) -> Path:
    """Extract audio from video, returning the audio file path."""
    _send_progress(
        job, JobStatus.DOWNLOADING, 15.0, "extract_audio", "Extracting audio"
    )
    t0 = time.monotonic()
    audio_path = work_dir / "audio.mp3"
    await asyncio.to_thread(extract_audio, video_path, audio_path)
    job.output_files[FileType.AUDIO] = audio_path
    log.info(
        "step_done",
        step="extract_audio",
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
    return audio_path


async def _acquire_video(
    job: Job,
    work_dir: Path,
    log: structlog.stdlib.BoundLogger,
) -> tuple[Path, VideoMetadata]:
    """Download or use local upload, returning video path and metadata."""
    if job.local_video_path is not None:
        _send_progress(
            job, JobStatus.DOWNLOADING, 5.0, "upload", "Processing uploaded file"
        )
        video_path = job.local_video_path
        meta_dict = await asyncio.to_thread(extract_video_metadata, video_path)
        metadata = VideoMetadata(
            title=str(meta_dict["title"]),
            duration=float(meta_dict["duration"]),
            width=int(meta_dict["width"]),
            height=int(meta_dict["height"]),
            fps=float(meta_dict["fps"]),
        )
        log.info("step_done", step="upload", source=str(video_path))
        return video_path, metadata

    _send_progress(job, JobStatus.DOWNLOADING, 0.0, "download", "Downloading video")
    t0 = time.monotonic()
    video_path = work_dir / "video.mp4"

    loop = asyncio.get_running_loop()

    def _on_download_progress(downloaded: float, total: float) -> None:
        if total > 0:
            pct = (downloaded / total) * 10.0  # Map to 0-10% range

            def _put_event() -> None:
                job.event_queue.put_nowait(
                    {
                        "event": SSEEvent.PROGRESS,
                        "data": {
                            "status": str(JobStatus.DOWNLOADING),
                            "progress": pct,
                            "current_step": "download",
                            "message": f"Downloading ({downloaded / total * 100:.0f}%)",
                        },
                    }
                )

            loop.call_soon_threadsafe(_put_event)

    metadata = await asyncio.to_thread(
        download_video,
        job.source_url,
        video_path,
        on_progress=_on_download_progress,
        start_time=job.start_time,
        end_time=job.end_time,
    )
    log.info(
        "step_done",
        step="download",
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
    return video_path, metadata


def _send_download_complete(job: Job) -> None:
    """Update job state and enqueue an SSE download_complete event."""
    job.status = JobStatus.DOWNLOAD_COMPLETE
    job.progress = 100.0
    job.event_queue.put_nowait(
        {
            "event": SSEEvent.DOWNLOAD_COMPLETE,
            "data": {"status": "download_complete", "progress": 100},
        }
    )


async def run_download(job: Job) -> None:
    """Phase 1: Download -> Extract Audio."""
    log = logger.bind(job_id=job.id)
    work_dir = Path(tempfile.mkdtemp(prefix=f"bilingualsub_{job.id}_"))

    try:
        video_path, metadata = await _acquire_video(job, work_dir, log)
        await _extract_audio_step(job, video_path, work_dir, log)

        # Save metadata for subtitle phase
        job.video_width = metadata.width
        job.video_height = metadata.height
        job.video_title = metadata.title
        job.video_description = metadata.description
        job.video_duration = metadata.duration
        job.output_files[FileType.SOURCE_VIDEO] = video_path

        _send_download_complete(job)
        log.info("download_complete", job_id=job.id)
    except Exception as exc:
        pipeline_err = _to_pipeline_error(exc)
        _send_error(
            job, pipeline_err.code, pipeline_err.message, pipeline_err.detail or ""
        )
        log.error(
            "download_failed",
            error_code=pipeline_err.code,
            error=str(exc),
        )


async def _merge_and_serialize(
    job: Job,
    original_sub: Subtitle,
    translated_sub: Subtitle,
    work_dir: Path,
    log: structlog.stdlib.BoundLogger,
) -> None:
    """Merge original + translated subtitles and serialize to SRT/ASS."""
    _send_progress(job, JobStatus.MERGING, 70.0, "merge", "Merging bilingual subtitles")
    t0 = time.monotonic()

    merged_entries = await asyncio.to_thread(
        merge_subtitles, original_sub.entries, translated_sub.entries
    )
    merged_sub = Subtitle(entries=merged_entries)

    srt_content = serialize_srt(merged_sub)
    srt_path = work_dir / "subtitle.srt"
    srt_path.write_text(srt_content, encoding="utf-8")
    job.output_files[FileType.SRT] = srt_path

    ass_content = serialize_bilingual_ass(
        original_sub,
        translated_sub,
        video_width=job.video_width,
        video_height=job.video_height,
    )
    ass_path = work_dir / "subtitle.ass"
    ass_path.write_text(ass_content, encoding="utf-8")
    job.output_files[FileType.ASS] = ass_path

    log.info("step_done", step="merge", duration_ms=int((time.monotonic() - t0) * 1000))


def _serialize_translated_only(
    job: Job, translated_sub: Subtitle, work_dir: Path
) -> None:
    """Serialize only the translated subtitle to SRT (no bilingual merge)."""
    _send_progress(
        job, JobStatus.MERGING, 70.0, "serialize", "Generating subtitle file..."
    )

    srt_content = serialize_srt(translated_sub)
    srt_path = work_dir / "subtitle.srt"
    srt_path.write_text(srt_content, encoding="utf-8")
    job.output_files[FileType.SRT] = srt_path


async def _run_visual_description_subtitle(job: Job) -> None:
    """Run visual description subtitle pipeline."""
    log = logger.bind(job_id=job.id)
    try:
        video_path = job.output_files.get(FileType.SOURCE_VIDEO)
        if not video_path:
            raise PipelineError("visual_description_failed", "Source video not found")

        if job.video_duration > 5400.0:
            raise PipelineError(
                "video_too_long",
                "Video exceeds 90-minute limit for visual description mode",
            )

        # Describe video (20-50%)
        _send_progress(
            job,
            JobStatus.TRANSCRIBING,
            20.0,
            "describe",
            "Analyzing video content...",
        )
        described_sub = await asyncio.to_thread(
            describe_video, video_path, source_lang=job.source_lang
        )
        job.subtitle_source = SubtitleSource.VISUAL_DESCRIPTION

        # Translate (50-70%)
        _send_progress(
            job,
            JobStatus.TRANSLATING,
            50.0,
            "translate",
            "Translating descriptions...",
        )
        translated_sub = await asyncio.to_thread(
            translate_subtitle,
            described_sub,
            source_lang=job.source_lang,
            target_lang=job.target_lang,
            video_title=job.video_title,
            video_description=job.video_description,
            glossary_text=job.glossary_text,
            on_progress=_make_translate_progress_cb(job),
            on_rate_limit=_make_rate_limit_cb(job),
        )

        # Serialize translated-only SRT (70-80%)
        _serialize_translated_only(job, translated_sub, work_dir=video_path.parent)

        _send_complete(job)

    except PipelineError as exc:
        _send_error(job, exc.code, exc.message, exc.detail or "")
        log.error("visual_description_failed", error_code=exc.code, error=str(exc))
    except Exception as exc:
        pipeline_err = _to_pipeline_error(exc)
        log.error(
            "visual_description_failed",
            error_code=pipeline_err.code,
            error=str(exc),
        )
        _send_error(
            job,
            pipeline_err.code,
            pipeline_err.message,
            detail=str(exc),
        )


async def run_subtitle(job: Job) -> None:
    """Phase 2: Transcribe -> Translate -> Merge -> Serialize."""
    log = logger.bind(job_id=job.id)

    if job.processing_mode == ProcessingMode.VISUAL_DESCRIPTION:
        await _run_visual_description_subtitle(job)
        return

    try:
        audio_path = job.output_files[FileType.AUDIO]
        work_dir = audio_path.parent

        original_sub = None
        subtitle_source = SubtitleSource.WHISPER

        if job.source_url:
            _send_progress(
                job,
                JobStatus.TRANSCRIBING,
                20.0,
                "transcribe",
                "Checking for manual subtitles",
            )
            t0 = time.monotonic()
            original_sub = await asyncio.to_thread(
                fetch_manual_subtitle, job.source_url, job.source_lang, work_dir
            )
            if original_sub is not None:
                subtitle_source = SubtitleSource.YOUTUBE_MANUAL
                log.info(
                    "step_done",
                    step="subtitle_fetch",
                    source="youtube_manual",
                    entries=len(original_sub.entries),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

        if original_sub is None:
            _send_progress(
                job, JobStatus.TRANSCRIBING, 20.0, "transcribe", "Transcribing audio"
            )
            t0 = time.monotonic()
            original_sub = await asyncio.to_thread(
                transcribe_audio, audio_path, language=job.source_lang
            )
            log.info(
                "step_done",
                step="transcribe",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        job.subtitle_source = subtitle_source
        if not isinstance(original_sub, Subtitle):
            raise PipelineError("transcription_failed", "Failed to obtain subtitles")

        _send_progress(
            job,
            JobStatus.TRANSLATING,
            50.0,
            "translate",
            "Translating subtitles",
            extra={"subtitle_source": str(subtitle_source)},
        )
        t0 = time.monotonic()
        _on_translate_progress = _make_translate_progress_cb(job)
        _on_rate_limit = _make_rate_limit_cb(job)
        translated_sub = await asyncio.to_thread(
            translate_subtitle,
            original_sub,
            source_lang=job.source_lang,
            target_lang=job.target_lang,
            video_title=job.video_title,
            video_description=job.video_description,
            glossary_text=job.glossary_text,
            on_progress=_on_translate_progress,
            on_rate_limit=_on_rate_limit,
        )
        log.info(
            "step_done",
            step="translate",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

        await _merge_and_serialize(job, original_sub, translated_sub, work_dir, log)

        _send_complete(job)
        log.info("subtitle_complete", job_id=job.id)
    except PipelineError as exc:
        _send_error(job, exc.code, exc.message, exc.detail or "")
        log.error("subtitle_failed", error_code=exc.code, error=str(exc))
    except Exception as exc:
        pipeline_err = _to_pipeline_error(exc)
        _send_error(
            job, pipeline_err.code, pipeline_err.message, pipeline_err.detail or ""
        )
        log.error(
            "subtitle_failed",
            error_code=pipeline_err.code,
            error=str(exc),
        )


async def run_burn(job: Job, srt_content: str) -> None:
    """Burn user-edited SRT into the source video."""
    log = logger.bind(job_id=job.id)
    try:
        source_video = job.output_files[FileType.SOURCE_VIDEO]
        work_dir = source_video.parent
        srt_path = work_dir / "subtitle_edited.srt"
        srt_path.write_text(srt_content, encoding="utf-8")

        _send_progress(job, JobStatus.BURNING, 0.0, "burn", "Burning subtitles")
        output_video = work_dir / "output.mp4"

        def on_burn_progress(percent: float) -> None:
            _send_progress(
                job,
                JobStatus.BURNING,
                percent,
                "burn",
                f"Burning subtitles ({percent:.0f}%)",
            )

        await asyncio.to_thread(
            burn_subtitles,
            source_video,
            srt_path,
            output_video,
            on_progress=on_burn_progress,
        )
        job.output_files[FileType.VIDEO] = output_video
        _send_complete(job)
        log.info("burn_complete", job_id=job.id)
    except Exception as exc:
        pipeline_err = _to_pipeline_error(exc)
        _send_error(
            job, pipeline_err.code, pipeline_err.message, pipeline_err.detail or ""
        )
        log.error("burn_failed", error_code=pipeline_err.code, error=str(exc))
