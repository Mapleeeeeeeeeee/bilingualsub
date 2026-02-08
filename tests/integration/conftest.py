"""Pytest configuration and shared fixtures for integration tests."""

from collections.abc import Generator
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from bilingualsub.core.downloader import VideoMetadata
from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.utils.config import get_settings

# ---------------------------------------------------------------------------
# Module-level helpers & markers
# ---------------------------------------------------------------------------


def has_groq_api_key() -> bool:
    """Check if GROQ_API_KEY is available."""
    get_settings.cache_clear()
    settings = get_settings()
    return bool(settings.groq_api_key)


requires_groq_api = pytest.mark.skipif(
    not has_groq_api_key(),
    reason="GROQ_API_KEY environment variable not set",
)


# ---------------------------------------------------------------------------
# Autouse fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Generator[None, None, None]:
    """Clear the get_settings LRU cache before and after each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Environment fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def set_fake_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set a fake GROQ_API_KEY environment variable."""
    monkeypatch.setenv("GROQ_API_KEY", "test-fake-key")
    get_settings.cache_clear()


@pytest.fixture
def no_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Switch to a temporary directory with no .env file."""
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Subtitle fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_subtitle_3_entries() -> Subtitle:
    """Return a Subtitle with 3 English entries matching sample_srt_content."""
    return Subtitle(
        entries=[
            SubtitleEntry(
                index=1,
                start=timedelta(seconds=1),
                end=timedelta(seconds=4),
                text="Hello, this is a test.",
            ),
            SubtitleEntry(
                index=2,
                start=timedelta(seconds=5),
                end=timedelta(seconds=8),
                text="This is the second subtitle.",
            ),
            SubtitleEntry(
                index=3,
                start=timedelta(seconds=9),
                end=timedelta(seconds=12),
                text="And this is the third one.",
            ),
        ]
    )


@pytest.fixture
def sample_translated_3_entries() -> Subtitle:
    """Return a Subtitle with 3 Traditional Chinese entries."""
    return Subtitle(
        entries=[
            SubtitleEntry(
                index=1,
                start=timedelta(seconds=1),
                end=timedelta(seconds=4),
                text="你好，這是一個測試。",
            ),
            SubtitleEntry(
                index=2,
                start=timedelta(seconds=5),
                end=timedelta(seconds=8),
                text="這是第二個字幕。",
            ),
            SubtitleEntry(
                index=3,
                start=timedelta(seconds=9),
                end=timedelta(seconds=12),
                text="這是第三個。",
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Video metadata fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_video_metadata() -> VideoMetadata:
    """Return sample VideoMetadata for testing."""
    return VideoMetadata(
        title="Test Video",
        duration=60.0,
        width=1920,
        height=1080,
        fps=30.0,
    )


# ---------------------------------------------------------------------------
# API response fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_whisper_api_response() -> Mock:
    """Return a mock Groq Whisper verbose_json response matching sample_subtitle_3_entries."""
    response = Mock()
    response.segments = [
        {"id": 0, "start": 1.0, "end": 4.0, "text": " Hello, this is a test."},
        {"id": 1, "start": 5.0, "end": 8.0, "text": " This is the second subtitle."},
        {"id": 2, "start": 9.0, "end": 12.0, "text": " And this is the third one."},
    ]
    response.text = (
        "Hello, this is a test. This is the second subtitle. And this is the third one."
    )
    return response
