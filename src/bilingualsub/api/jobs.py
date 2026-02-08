"""In-memory job store with TTL-based cleanup."""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

from bilingualsub.api.constants import (
    CLEANUP_INTERVAL_SECONDS,
    JOB_TTL_SECONDS,
    FileType,
    JobStatus,
)

logger = structlog.get_logger()


@dataclass
class Job:
    """Represents a subtitle generation job."""

    id: str
    youtube_url: str
    source_lang: str
    target_lang: str
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    current_step: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    error_detail: str | None = None
    output_files: dict[FileType, Path] = field(default_factory=dict)
    event_queue: asyncio.Queue[dict[str, object]] = field(default_factory=asyncio.Queue)
    created_at: float = field(default_factory=time.monotonic)


class JobManager:
    """Manages in-memory job lifecycle with automatic cleanup."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._cleanup_task: asyncio.Task[None] | None = None

    def create_job(self, youtube_url: str, source_lang: str, target_lang: str) -> Job:
        """Create a new job and store it."""
        job_id = uuid.uuid4().hex[:12]
        job = Job(
            id=job_id,
            youtube_url=youtube_url,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        self._jobs[job_id] = job
        logger.info("job_created", job_id=job_id, youtube_url=youtube_url)
        return job

    def get_job(self, job_id: str) -> Job | None:
        """Get a job by ID, returns None if not found."""
        return self._jobs.get(job_id)

    def cleanup_expired(self) -> int:
        """Remove jobs older than JOB_TTL_SECONDS. Returns count of removed jobs."""
        now = time.monotonic()
        expired = [
            jid
            for jid, job in self._jobs.items()
            if now - job.created_at > JOB_TTL_SECONDS
        ]
        for jid in expired:
            del self._jobs[jid]
        if expired:
            logger.info("jobs_cleaned_up", count=len(expired))
        return len(expired)

    async def start_cleanup_loop(self) -> None:
        """Start periodic cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_loop(self) -> None:
        """Stop the periodic cleanup task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None

    async def _cleanup_loop(self) -> None:
        """Periodically clean up expired jobs."""
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            self.cleanup_expired()
