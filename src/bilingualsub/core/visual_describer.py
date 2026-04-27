"""Video visual description using Gemini."""

from __future__ import annotations

import contextlib
import re
import time
from datetime import timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.utils.config import get_gemini_api_key, get_settings

try:
    from google import genai as _genai
except ImportError:
    _genai = None  # type: ignore[assignment]

_FILE_PROCESSING_TIMEOUT = 600

DESCRIBE_PROMPT = (
    "You are a narrator producing subtitles for a silent video.\n\n"
    "Format each subtitle as: MM:SS - MM:SS | Text\n\n"
    "<pacing>\n"
    "Viewers need time to read each subtitle while watching the video.\n"
    "Keep each segment 3-8 seconds. Combine related actions into one line "
    "(e.g. a user typing a prompt and pressing Send is one segment, "
    "not three separate ones).\n"
    "</pacing>\n\n"
    "<on_screen_text>\n"
    "When someone types or a message appears on screen, quote the actual "
    "text so it can be translated later. A viewer watching a foreign-language "
    "product demo needs to read what was typed, not be told 'the user typed "
    "a prompt about a globe.'\n"
    "</on_screen_text>\n\n"
    "<ui_actions>\n"
    "For sequences of clicks, menus, and transitions, summarize the goal "
    "of the sequence in one line (e.g. 'The user customizes the globe's "
    "appearance using a settings panel'). Individual button labels like "
    "'Send' or 'Edit' are not useful as standalone subtitles.\n"
    "</ui_actions>\n\n"
    "<skip>\n"
    "Omit static logo cards and branding screens — they carry no information "
    "a subtitle can add.\n"
    "</skip>"
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


def _wait_for_active(client: Any, uploaded_file: Any) -> Any:
    """Poll until the uploaded file reaches ACTIVE state or raise on failure."""
    deadline = time.monotonic() + _FILE_PROCESSING_TIMEOUT
    while uploaded_file.state == "PROCESSING":
        if time.monotonic() >= deadline:
            raise VisualDescriptionError("File processing timed out after 600 seconds")
        time.sleep(2)
        file_name = uploaded_file.name or ""
        uploaded_file = client.files.get(name=file_name)

    if uploaded_file.state == "FAILED":
        raise VisualDescriptionError("File processing failed on Gemini servers")
    if uploaded_file.state != "ACTIVE":
        raise VisualDescriptionError(f"Unexpected file state: {uploaded_file.state}")
    return uploaded_file


def _parse_response(response_text: str) -> list[SubtitleEntry]:
    """Parse Gemini response text into subtitle entries."""
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
    return entries


def describe_video(
    video_path: Path,
    *,
    source_lang: str = "en",
) -> Subtitle:
    """Analyze video frames with Gemini and return timestamped descriptions."""
    if not video_path.exists():
        raise ValueError(f"Video file not found: {video_path}")

    if _genai is None:
        raise ValueError(
            "google-genai package is not installed. Run: uv add google-genai"
        )

    api_key = get_gemini_api_key()
    settings = get_settings()

    prompt = DESCRIBE_PROMPT
    if source_lang and source_lang != "auto":
        prompt += f"\n\nOutput in {source_lang}."
    else:
        prompt += "\n\nOutput in the video's original language."

    client = None
    uploaded_file = None
    try:
        client = _genai.Client(api_key=api_key)
        uploaded_file = client.files.upload(file=video_path)
        uploaded_file = _wait_for_active(client, uploaded_file)

        response = client.models.generate_content(
            model=settings.visual_description_model,
            contents=[uploaded_file, prompt],
        )
    except VisualDescriptionError:
        raise
    except Exception as exc:
        raise VisualDescriptionError(f"Gemini API call failed: {exc}") from exc
    finally:
        if client and uploaded_file and uploaded_file.name:
            with contextlib.suppress(Exception):
                client.files.delete(name=uploaded_file.name)

    entries = _parse_response(response.text or "")
    if not entries:
        raise VisualDescriptionError("No visual description segments returned")

    return Subtitle(entries=entries)
