"""Video visual description using Gemini."""

from __future__ import annotations

import re
import time
from datetime import timedelta
from typing import TYPE_CHECKING

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.utils.config import get_gemini_api_key, get_settings

if TYPE_CHECKING:
    from pathlib import Path

try:
    from google import genai as _genai
except ImportError:
    _genai = None

DESCRIBE_PROMPT = (
    "Analyze this video and provide a timestamped visual description. "
    "Format each segment as: MM:SS - MM:SS | Description\n"
    "Focus on: on-screen text, titles, product names, UI elements, "
    "and key visual scenes.\n"
    "Provide descriptions in the video's original language. "
    "Be concise (one sentence per segment)."
)

_TIMESTAMP_PATTERN = re.compile(
    r"(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–]\s*"  # noqa: RUF001
    r"(\d{1,2}:\d{2}(?::\d{2})?)\s*[|｜:：]\s*(.+)"  # noqa: RUF001
)


class VisualDescriptionError(Exception):
    """Raised when Gemini visual description fails."""


def _parse_timestamp(timestamp: str) -> timedelta:
    parts = timestamp.strip().split(":")
    if len(parts) == 2:
        minutes, seconds = int(parts[0]), int(parts[1])
        return timedelta(minutes=minutes, seconds=seconds)
    hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def describe_video(
    video_path: Path,
    *,
    source_lang: str = "en",  # noqa: ARG001
) -> Subtitle:
    """Analyze video frames with Gemini and return timestamped descriptions."""
    if not video_path.exists():
        raise ValueError(f"Video file not found: {video_path}")

    api_key = get_gemini_api_key()

    if _genai is None:
        raise VisualDescriptionError(
            "google-genai package is not installed. Run: uv add google-genai"
        )

    settings = get_settings()

    try:
        client = _genai.Client(api_key=api_key)
        uploaded_file = client.files.upload(file=video_path)

        # Wait for file processing to complete
        while uploaded_file.state == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)
        if uploaded_file.state != "ACTIVE":
            raise VisualDescriptionError(
                f"File processing failed with state: {uploaded_file.state}"
            )

        response = client.models.generate_content(
            model=settings.visual_description_model,
            contents=[uploaded_file, DESCRIBE_PROMPT],
        )
    except VisualDescriptionError:
        raise
    except Exception as exc:
        raise VisualDescriptionError(f"Gemini API call failed: {exc}") from exc

    response_text = response.text or ""
    entries: list[SubtitleEntry] = []

    for line in response_text.splitlines():
        match = _TIMESTAMP_PATTERN.search(line)
        if not match:
            continue
        start_str, end_str, description = (
            match.group(1),
            match.group(2),
            match.group(3).strip(),
        )
        try:
            start = _parse_timestamp(start_str)
            end = _parse_timestamp(end_str)
            if start >= end or not description:
                continue
            entries.append(
                SubtitleEntry(
                    index=len(entries) + 1,
                    start=start,
                    end=end,
                    text=description,
                )
            )
        except (ValueError, IndexError):
            continue

    if not entries:
        raise VisualDescriptionError("No visual description segments returned")

    return Subtitle(entries=entries)
