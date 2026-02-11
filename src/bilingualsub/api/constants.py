"""Constants and enums for the API layer."""

from enum import StrEnum


class JobStatus(StrEnum):
    """Status of a subtitle generation job."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOAD_COMPLETE = "download_complete"
    TRANSCRIBING = "transcribing"
    TRANSLATING = "translating"
    MERGING = "merging"
    BURNING = "burning"
    COMPLETED = "completed"
    FAILED = "failed"


class FileType(StrEnum):
    """Output file types produced by the pipeline."""

    SRT = "srt"
    ASS = "ass"
    VIDEO = "video"
    AUDIO = "audio"
    SOURCE_VIDEO = "source_video"


class SSEEvent(StrEnum):
    """Server-Sent Events event types."""

    PROGRESS = "progress"
    COMPLETE = "complete"
    DOWNLOAD_COMPLETE = "download_complete"
    ERROR = "error"
    PING = "ping"


JOB_TTL_SECONDS = 1800
CLEANUP_INTERVAL_SECONDS = 300
SSE_KEEPALIVE_SECONDS = 30
