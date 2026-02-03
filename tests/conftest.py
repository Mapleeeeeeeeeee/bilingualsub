"""Pytest configuration and shared fixtures."""

from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def temp_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide a temporary directory for tests."""
    yield tmp_path


@pytest.fixture
def sample_srt_content() -> str:
    """Return sample SRT content for testing."""
    return """1
00:00:01,000 --> 00:00:04,000
Hello, this is a test.

2
00:00:05,000 --> 00:00:08,000
This is the second subtitle.

3
00:00:09,000 --> 00:00:12,000
And this is the third one.
"""


@pytest.fixture
def sample_youtube_url() -> str:
    """Return a sample YouTube URL for testing."""
    return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
