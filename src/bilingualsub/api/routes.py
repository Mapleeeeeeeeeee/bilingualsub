"""API route definitions."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from bilingualsub.api.constants import (
    SSE_KEEPALIVE_SECONDS,
    FileType,
    JobStatus,
    SSEEvent,
)
from bilingualsub.api.errors import InvalidRequestError, JobNotFoundError, PipelineError
from bilingualsub.api.pipeline import run_burn, run_download, run_subtitle
from bilingualsub.api.schemas import (
    BurnRequest,
    ErrorDetail,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
    PartialRetranslateItem,
    PartialRetranslateRequest,
    PartialRetranslateResponse,
    StartSubtitleRequest,
)
from bilingualsub.core import RetranslateEntry, TranslationError, retranslate_entries

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from bilingualsub.api.jobs import Job, JobManager

router = APIRouter(prefix="/api")
logger = structlog.get_logger()

_ALLOWED_UPLOAD_EXTENSIONS = {
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".mp3",
    ".wav",
    ".m4a",
    ".webm",
}


def _get_job_manager(request: Request) -> JobManager:
    """Get the JobManager from app state."""
    manager: JobManager = request.app.state.job_manager
    return manager


def _get_job_or_404(request: Request, job_id: str) -> Job:
    """Get a job by ID or raise 404."""
    job = _get_job_manager(request).get_job(job_id)
    if job is None:
        raise JobNotFoundError(job_id)
    return job


def _start_background_task(request: Request, coro: Any) -> None:
    """Start a coroutine as a background task, preventing GC."""
    request.app.state._background_tasks = getattr(
        request.app.state, "_background_tasks", set()
    )
    task = asyncio.create_task(coro)
    request.app.state._background_tasks.add(task)
    task.add_done_callback(request.app.state._background_tasks.discard)


@router.post("/jobs", response_model=JobCreateResponse)
async def create_job(body: JobCreateRequest, request: Request) -> JobCreateResponse:
    """Create a new subtitle generation job."""
    manager = _get_job_manager(request)
    job = manager.create_job(
        youtube_url=str(body.youtube_url),
        source_lang=body.source_lang,
        target_lang=body.target_lang,
        start_time=body.start_time,
        end_time=body.end_time,
    )
    _start_background_task(request, run_download(job))
    return JobCreateResponse(job_id=job.id)


@router.post("/jobs/upload", response_model=JobCreateResponse)
async def create_job_from_upload(
    file: UploadFile,
    source_lang: str = Form("en"),
    target_lang: str = Form("zh-TW"),
    start_time: float | None = Form(None),
    end_time: float | None = Form(None),
    *,
    request: Request,
) -> JobCreateResponse:
    """Create a subtitle generation job from an uploaded file."""
    # Validate file extension
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise InvalidRequestError(
            f"Unsupported file type: {suffix}",
            detail=f"Allowed: {', '.join(sorted(_ALLOWED_UPLOAD_EXTENSIONS))}",
        )

    # Sanitize filename to prevent path traversal
    safe_name = Path(filename).name or f"upload{suffix}"

    # Save uploaded file to temp directory with size limit
    max_size = 500 * 1024 * 1024  # 500 MB
    tmp_dir = Path(tempfile.mkdtemp(prefix="bilingualsub_upload_"))
    saved_path = tmp_dir / safe_name
    bytes_written = 0
    with saved_path.open("wb") as buf:
        while chunk := await file.read(1024 * 1024):
            bytes_written += len(chunk)
            if bytes_written > max_size:
                saved_path.unlink(missing_ok=True)
                tmp_dir.rmdir()
                raise InvalidRequestError(
                    "File too large",
                    detail="Maximum file size is 500 MB",
                )
            buf.write(chunk)

    manager = _get_job_manager(request)
    job = manager.create_job(
        source_lang=source_lang,
        target_lang=target_lang,
        start_time=start_time,
        end_time=end_time,
        local_video_path=saved_path,
    )
    _start_background_task(request, run_download(job))
    return JobCreateResponse(job_id=job.id)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, request: Request) -> JobStatusResponse:
    """Get the current status of a job."""
    job = _get_job_or_404(request, job_id)
    error = None
    if job.error_code:
        error = ErrorDetail(
            code=job.error_code,
            message=job.error_message or "",
            detail=job.error_detail,
        )
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        current_step=job.current_step,
        error=error,
        output_files={ft: str(p) for ft, p in job.output_files.items()},
    )


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request) -> EventSourceResponse:
    """SSE stream of job progress events."""
    job = _get_job_or_404(request, job_id)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        while True:
            try:
                event = await asyncio.wait_for(
                    job.event_queue.get(), timeout=SSE_KEEPALIVE_SECONDS
                )
                yield {
                    "event": str(event["event"]),
                    "data": json.dumps(event["data"]),
                }
                # Stop streaming on terminal events
                if event["event"] in (SSEEvent.COMPLETE, SSEEvent.ERROR):
                    return
                # download_complete does NOT close the stream
            except TimeoutError:
                # Send keepalive ping
                yield {"event": SSEEvent.PING, "data": ""}

    return EventSourceResponse(event_generator())


@router.get("/jobs/{job_id}/download/{file_type}")
async def download_file(job_id: str, file_type: str, request: Request) -> FileResponse:
    """Download a generated file."""
    # Validate file type
    try:
        ft = FileType(file_type)
    except ValueError as err:
        raise InvalidRequestError(
            f"Invalid file type: {file_type}",
            detail=f"Must be one of: {', '.join(FileType)}",
        ) from err

    job = _get_job_or_404(request, job_id)
    path = job.output_files.get(ft)
    if path is None or not path.exists():
        raise InvalidRequestError(
            f"File not available: {file_type}",
            detail="Job may not have completed this step",
        )

    # Set appropriate media type and filename
    media_types = {
        FileType.SRT: "text/plain",
        FileType.ASS: "text/plain",
        FileType.VIDEO: "video/mp4",
        FileType.AUDIO: "audio/mpeg",
        FileType.SOURCE_VIDEO: "video/mp4",
    }
    extensions = {
        FileType.SRT: "srt",
        FileType.ASS: "ass",
        FileType.VIDEO: "mp4",
        FileType.AUDIO: "mp3",
        FileType.SOURCE_VIDEO: "mp4",
    }
    return FileResponse(
        path=path,
        media_type=media_types[ft],
        filename=f"bilingualsub.{extensions[ft]}",
    )


@router.post("/jobs/{job_id}/subtitle")
async def start_subtitle(
    job_id: str,
    request: Request,
    body: StartSubtitleRequest | None = None,
) -> dict[str, str]:
    """Trigger subtitle generation for a downloaded job."""
    job = _get_job_or_404(request, job_id)
    if job.status != JobStatus.DOWNLOAD_COMPLETE:
        raise InvalidRequestError(
            "Job is not in download_complete state",
            detail=f"Current status: {job.status}",
        )
    if body:
        if body.source_lang:
            job.source_lang = body.source_lang
        if body.target_lang:
            job.target_lang = body.target_lang
    _start_background_task(request, run_subtitle(job))
    return {"status": "subtitle_started"}


@router.post("/jobs/{job_id}/burn")
async def burn_job(job_id: str, body: BurnRequest, request: Request) -> dict[str, str]:
    """Burn user-edited subtitles into the source video."""
    job = _get_job_or_404(request, job_id)
    if FileType.SOURCE_VIDEO not in job.output_files:
        raise InvalidRequestError("Pipeline not complete")
    if job.status == JobStatus.BURNING:
        raise InvalidRequestError("Burn already in progress")

    job.status = JobStatus.BURNING
    job.progress = 0.0
    job.event_queue = asyncio.Queue()
    _start_background_task(request, run_burn(job, body.srt_content))
    return {"status": "burning"}


@router.post("/jobs/{job_id}/retranslate", response_model=PartialRetranslateResponse)
async def partial_retranslate(
    job_id: str,
    body: PartialRetranslateRequest,
    request: Request,
) -> PartialRetranslateResponse:
    """Re-translate selected subtitle entries with surrounding context."""
    job = _get_job_or_404(request, job_id)
    if FileType.SOURCE_VIDEO not in job.output_files:
        raise InvalidRequestError("Pipeline not complete")

    try:
        results = await asyncio.to_thread(
            retranslate_entries,
            entries=[
                RetranslateEntry(
                    index=entry.index,
                    original=entry.original,
                    translated=entry.translated,
                )
                for entry in body.entries
            ],
            selected_indices=body.selected_indices,
            source_lang=job.source_lang,
            target_lang=job.target_lang,
            video_title=job.video_title,
            video_description=job.video_description,
            user_context=body.user_context,
        )
    except ValueError as exc:
        raise InvalidRequestError(
            "Invalid re-translation request",
            detail=str(exc),
        ) from exc
    except TranslationError as exc:
        raise PipelineError(
            "translation_failed",
            "Failed to re-translate subtitles",
            detail=str(exc),
        ) from exc

    return PartialRetranslateResponse(
        results=[
            PartialRetranslateItem(index=index, translated=translated)
            for index, translated in sorted(results.items())
        ]
    )


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
