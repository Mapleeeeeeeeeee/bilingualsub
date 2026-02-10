"""Async pipeline runner that orchestrates core modules."""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from bilingualsub.api.constants import FileType, JobStatus, SSEEvent
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
    download_youtube_video,
    merge_subtitles,
    transcribe_audio,
    translate_subtitle,
)
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
    ValueError: ("invalid_input", "Invalid input"),
}


def _send_progress(
    job: Job,
    status: JobStatus,
    progress: float,
    current_step: str,
    message: str,
) -> None:
    """Update job state and enqueue an SSE progress event."""
    job.status = status
    job.progress = progress
    job.current_step = current_step
    job.event_queue.put_nowait(
        {
            "event": SSEEvent.PROGRESS,
            "data": {
                "status": str(status),
                "progress": progress,
                "current_step": current_step,
                "message": message,
            },
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
    metadata = await asyncio.to_thread(
        download_youtube_video, job.youtube_url, video_path
    )
    log.info(
        "step_done",
        step="download",
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
    return video_path, metadata


async def run_pipeline(job: Job) -> None:
    """Execute the full subtitle generation pipeline for a job.

    Steps: download -> transcribe -> translate -> merge/serialize -> burn.
    All blocking core calls are wrapped in asyncio.to_thread().
    Progress events are sent to job.event_queue at each step.
    """
    log = logger.bind(job_id=job.id)
    work_dir = Path(tempfile.mkdtemp(prefix=f"bilingualsub_{job.id}_"))

    try:
        # --- Step 1: Download or use local file ---
        video_path, metadata = await _acquire_video(job, work_dir, log)

        # --- Step 1.25: Trim video (if time range specified) ---
        video_path = await _trim_if_needed(
            job, video_path, work_dir, metadata.duration, log
        )

        # --- Step 1.5: Extract audio ---
        audio_path = await _extract_audio_step(job, video_path, work_dir, log)

        # --- Step 2: Transcribe ---
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

        # --- Step 3: Translate ---
        _send_progress(
            job, JobStatus.TRANSLATING, 50.0, "translate", "Translating subtitles"
        )
        t0 = time.monotonic()

        _on_translate_progress = _make_translate_progress_cb(job)

        translated_sub = await asyncio.to_thread(
            translate_subtitle,
            original_sub,
            source_lang=job.source_lang,
            target_lang=job.target_lang,
            on_progress=_on_translate_progress,
        )
        log.info(
            "step_done",
            step="translate",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

        # --- Step 4: Merge & Serialize ---
        _send_progress(
            job, JobStatus.MERGING, 70.0, "merge", "Merging bilingual subtitles"
        )
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
            video_width=metadata.width,
            video_height=metadata.height,
        )
        ass_path = work_dir / "subtitle.ass"
        ass_path.write_text(ass_content, encoding="utf-8")
        job.output_files[FileType.ASS] = ass_path

        log.info(
            "step_done", step="merge", duration_ms=int((time.monotonic() - t0) * 1000)
        )

        # --- Step 5: Save source video & complete ---
        job.output_files[FileType.SOURCE_VIDEO] = video_path
        _send_complete(job)
        log.info("pipeline_complete", job_id=job.id)

    except PipelineError:
        raise
    except Exception as exc:
        pipeline_err = _to_pipeline_error(exc)
        _send_error(
            job, pipeline_err.code, pipeline_err.message, pipeline_err.detail or ""
        )
        log.error(
            "pipeline_failed",
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

        _send_progress(job, JobStatus.BURNING, 50.0, "burn", "Burning subtitles")
        output_video = work_dir / "output.mp4"
        await asyncio.to_thread(burn_subtitles, source_video, srt_path, output_video)
        job.output_files[FileType.VIDEO] = output_video
        _send_complete(job)
        log.info("burn_complete", job_id=job.id)
    except Exception as exc:
        pipeline_err = _to_pipeline_error(exc)
        _send_error(
            job, pipeline_err.code, pipeline_err.message, pipeline_err.detail or ""
        )
        log.error("burn_failed", error_code=pipeline_err.code, error=str(exc))
