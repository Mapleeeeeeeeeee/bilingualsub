"""API route definitions."""

from __future__ import annotations

import asyncio
import json
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import structlog
from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from bilingualsub.api.constants import (
    SSE_KEEPALIVE_SECONDS,
    FileType,
    JobStatus,
    ProcessingMode,
    SSEEvent,
)
from bilingualsub.api.errors import (
    ApiError,
    InvalidRequestError,
    JobNotFoundError,
    PipelineError,
)
from bilingualsub.api.pipeline import run_burn, run_download, run_subtitle
from bilingualsub.api.schemas import (
    BurnRequest,
    ErrorDetail,
    GlossaryAddRequest,
    GlossaryEntrySchema,
    GlossaryListResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
    PartialRetranslateItem,
    PartialRetranslateRequest,
    PartialRetranslateResponse,
    StartSubtitleRequest,
)
from bilingualsub.core import RetranslateEntry, TranslationError, retranslate_entries
from bilingualsub.core.glossary import GlossaryError, GlossaryManager

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

_DEFAULT_FILENAME = "video"
_SUFFIX_ORIGINAL = "(original)"
_LANG_SEPARATOR = "_to_"


class _FileMeta(NamedTuple):
    ext: str
    media_type: str


_FILE_META: dict[FileType, _FileMeta] = {
    FileType.SRT: _FileMeta("srt", "text/plain"),
    FileType.ASS: _FileMeta("ass", "text/plain"),
    FileType.VIDEO: _FileMeta("mp4", "video/mp4"),
    FileType.AUDIO: _FileMeta("mp3", "audio/mpeg"),
    FileType.SOURCE_VIDEO: _FileMeta("mp4", "video/mp4"),
}

# Windows-reserved + POSIX control characters (NTFS/FAT32/ext4 safe)
_FILENAME_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

_MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


def _sanitize_filename(name: str) -> str:
    """Remove filesystem-unsafe characters and truncate to 120 chars."""
    cleaned = _FILENAME_BAD_CHARS.sub("", name).strip(" .")
    truncated = (cleaned or _DEFAULT_FILENAME)[:120]
    return truncated.rstrip(" .") or _DEFAULT_FILENAME


def _build_download_filename(job: Job, file_type: FileType) -> str:
    """Build a human-readable download filename for the given job and file type."""
    base = _sanitize_filename(job.video_title or _DEFAULT_FILENAME)
    original_only = file_type in (FileType.SOURCE_VIDEO, FileType.AUDIO)
    same_lang = (
        not job.source_lang or not job.target_lang or job.source_lang == job.target_lang
    )
    suffix = (
        _SUFFIX_ORIGINAL
        if original_only or same_lang
        else f"({job.source_lang}{_LANG_SEPARATOR}{job.target_lang})"
    )
    ext = _FILE_META[file_type].ext
    return f"{base} {suffix}.{ext}"


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


def _get_glossary_manager(request: Request) -> GlossaryManager:
    """Get the GlossaryManager from app state."""
    manager: GlossaryManager = request.app.state.glossary_manager
    return manager


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
        source_url=str(body.source_url),
        source_lang=body.source_lang,
        target_lang=body.target_lang,
        start_time=body.start_time,
        end_time=body.end_time,
        processing_mode=ProcessingMode(body.processing_mode),
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
    processing_mode: str = Form(ProcessingMode.SUBTITLE),
    *,
    request: Request,
) -> JobCreateResponse:
    """Create a subtitle generation job from an uploaded file."""
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise InvalidRequestError(
            f"Unsupported file type: {suffix}",
            detail=f"Allowed: {', '.join(sorted(_ALLOWED_UPLOAD_EXTENSIONS))}",
        )

    safe_name = Path(filename).name or f"upload{suffix}"

    try:
        mode = ProcessingMode(processing_mode)
    except ValueError as err:
        raise InvalidRequestError(
            "Invalid processing_mode",
            detail=f"Must be one of: {', '.join(ProcessingMode)}",
        ) from err

    max_size = _MAX_UPLOAD_BYTES
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
        processing_mode=mode,
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

    return FileResponse(
        path=path,
        media_type=_FILE_META[ft].media_type,
        filename=_build_download_filename(job, ft),
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
        if body.processing_mode is not None:
            job.processing_mode = ProcessingMode(body.processing_mode)
    glossary_manager = _get_glossary_manager(request)
    job.glossary_text = glossary_manager.format_for_prompt()
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

    glossary_manager = _get_glossary_manager(request)
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
            glossary_text=glossary_manager.format_for_prompt(),
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


@router.get("/glossary", response_model=GlossaryListResponse)
async def list_glossary(request: Request) -> GlossaryListResponse:
    manager = _get_glossary_manager(request)
    entries = manager.get_all()
    return GlossaryListResponse(
        entries=[GlossaryEntrySchema(source=e.source, target=e.target) for e in entries]
    )


@router.post("/glossary", response_model=GlossaryEntrySchema, status_code=201)
async def add_glossary_entry(
    body: GlossaryAddRequest, request: Request
) -> GlossaryEntrySchema:
    manager = _get_glossary_manager(request)
    try:
        entry = manager.add(body.source, body.target)
    except GlossaryError as exc:
        raise ApiError(
            status_code=400, code="GLOSSARY_ERROR", message=str(exc)
        ) from exc
    return GlossaryEntrySchema(source=entry.source, target=entry.target)


@router.put("/glossary/{source}", response_model=GlossaryEntrySchema)
async def update_glossary_entry(
    source: str, body: GlossaryAddRequest, request: Request
) -> GlossaryEntrySchema:
    manager = _get_glossary_manager(request)
    try:
        entry = manager.update(source, body.target)
    except GlossaryError as exc:
        is_not_found = "not found" in str(exc).lower()
        raise ApiError(
            status_code=404 if is_not_found else 400,
            code="GLOSSARY_NOT_FOUND" if is_not_found else "GLOSSARY_ERROR",
            message=str(exc),
        ) from exc
    return GlossaryEntrySchema(source=entry.source, target=entry.target)


@router.delete("/glossary/{source}", status_code=204)
async def delete_glossary_entry(source: str, request: Request) -> None:
    manager = _get_glossary_manager(request)
    try:
        manager.delete(source)
    except GlossaryError as exc:
        raise ApiError(
            status_code=404, code="GLOSSARY_NOT_FOUND", message=str(exc)
        ) from exc


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
