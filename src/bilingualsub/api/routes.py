"""API route definitions."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from bilingualsub.api.constants import SSE_KEEPALIVE_SECONDS, FileType, SSEEvent
from bilingualsub.api.errors import InvalidRequestError, JobNotFoundError
from bilingualsub.api.pipeline import run_pipeline
from bilingualsub.api.schemas import (
    ErrorDetail,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from bilingualsub.api.jobs import Job, JobManager

router = APIRouter(prefix="/api")
logger = structlog.get_logger()


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
    # Start pipeline in background; store ref to prevent GC
    request.app.state._background_tasks = getattr(
        request.app.state, "_background_tasks", set()
    )
    task = asyncio.create_task(run_pipeline(job))
    request.app.state._background_tasks.add(task)
    task.add_done_callback(request.app.state._background_tasks.discard)
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
    }
    extensions = {
        FileType.SRT: "srt",
        FileType.ASS: "ass",
        FileType.VIDEO: "mp4",
    }
    return FileResponse(
        path=path,
        media_type=media_types[ft],
        filename=f"bilingualsub.{extensions[ft]}",
    )


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
