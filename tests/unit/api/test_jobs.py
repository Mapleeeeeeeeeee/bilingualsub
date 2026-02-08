"""Tests for job manager."""

import time

import pytest

from bilingualsub.api.constants import JOB_TTL_SECONDS, JobStatus
from bilingualsub.api.jobs import Job, JobManager


@pytest.mark.unit
class TestJob:
    def test_default_values(self) -> None:
        job = Job(
            id="test1",
            youtube_url="https://youtube.com/watch?v=test",
            source_lang="en",
            target_lang="zh-TW",
        )
        assert job.status == JobStatus.PENDING
        assert job.progress == 0.0
        assert job.current_step is None
        assert job.error_code is None
        assert job.output_files == {}


@pytest.mark.unit
class TestJobManager:
    def test_create_job(self) -> None:
        manager = JobManager()
        job = manager.create_job(
            youtube_url="https://youtube.com/watch?v=test",
            source_lang="en",
            target_lang="zh-TW",
        )
        assert job.id is not None
        assert len(job.id) == 12
        assert job.youtube_url == "https://youtube.com/watch?v=test"
        assert job.source_lang == "en"
        assert job.target_lang == "zh-TW"

    def test_get_existing_job(self) -> None:
        manager = JobManager()
        job = manager.create_job("https://youtube.com/watch?v=test", "en", "zh-TW")
        retrieved = manager.get_job(job.id)
        assert retrieved is job

    def test_get_nonexistent_job(self) -> None:
        manager = JobManager()
        assert manager.get_job("nonexistent") is None

    def test_cleanup_removes_expired(self) -> None:
        manager = JobManager()
        job = manager.create_job("https://youtube.com/watch?v=test", "en", "zh-TW")

        # Make the job appear expired by shifting its created_at back
        job.created_at = time.monotonic() - JOB_TTL_SECONDS - 1

        removed = manager.cleanup_expired()
        assert removed == 1
        assert manager.get_job(job.id) is None

    def test_cleanup_keeps_fresh_jobs(self) -> None:
        manager = JobManager()
        job = manager.create_job("https://youtube.com/watch?v=test", "en", "zh-TW")
        removed = manager.cleanup_expired()
        assert removed == 0
        assert manager.get_job(job.id) is not None
