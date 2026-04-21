"""Fetch manually-uploaded subtitles from video platforms via yt-dlp."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog
import yt_dlp

from bilingualsub.formats.srt import parse_srt

if TYPE_CHECKING:
    from pathlib import Path

    from bilingualsub.core.subtitle import Subtitle

logger = structlog.get_logger()


class SubtitleFetchError(Exception):
    """Raised when subtitle fetching fails."""


def fetch_manual_subtitle(
    url: str,
    lang: str,
    work_dir: Path,
) -> Subtitle | None:
    """Download manual subtitle for a video if available.

    Returns Subtitle object if manual subs found, None otherwise.
    Never raises - logs warnings and returns None on any failure.
    """
    try:
        return _fetch_subtitle(url, lang, work_dir)
    except Exception:
        logger.warning("subtitle_fetch_failed", url=url, lang=lang, exc_info=True)
        return None


def _fetch_subtitle(url: str, lang: str, work_dir: Path) -> Subtitle | None:
    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "subtitleslangs": [lang],
        "subtitlesformat": "srt",
        "outtmpl": str(work_dir / "manual_sub"),
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    if not info:
        return None

    manual_subs = info.get("subtitles", {})
    if lang not in manual_subs:
        logger.info(
            "no_manual_subtitle",
            url=url,
            lang=lang,
            available=list(manual_subs.keys()),
        )
        return None

    # yt-dlp may use different naming patterns, find the file
    actual_path: Path | None = None
    for ext in (".srt", ".vtt", ".ass"):
        candidate = work_dir / f"manual_sub.{lang}{ext}"
        if candidate.exists():
            actual_path = candidate
            break

    if actual_path is None:
        for ext in (".srt", ".vtt", ".ass"):
            matches = list(work_dir.glob(f"manual_sub*.{lang}{ext}"))
            if matches:
                actual_path = matches[0]
                break

    if actual_path is None:
        logger.warning("subtitle_file_not_found", work_dir=str(work_dir))
        return None

    content = actual_path.read_text(encoding="utf-8")

    if actual_path.suffix == ".vtt":
        content = vtt_to_srt(content)

    subtitle = parse_srt(content)
    logger.info("manual_subtitle_fetched", lang=lang, entries=len(subtitle.entries))
    return subtitle


def vtt_to_srt(vtt_content: str) -> str:
    """Convert WebVTT content to SRT format."""
    lines = vtt_content.strip().split("\n")

    # Skip VTT header
    start_idx = 0
    for i, line in enumerate(lines):
        if "-->" in line:
            # Check if previous line is a cue number
            start_idx = i - 1 if i > 0 and lines[i - 1].strip().isdigit() else i
            break

    srt_lines = []
    # Re-number and fix timestamp format (VTT uses . for ms, SRT uses ,)
    block_num = 0
    i = start_idx
    while i < len(lines):
        line = lines[i].strip()
        if "-->" in line:
            block_num += 1
            # Ensure HH:MM:SS format (VTT sometimes omits hours)
            parts = line.split("-->")
            fixed_parts = []
            for raw_part in parts:
                stripped = raw_part.strip()
                if len(stripped.split(":")) == 2:
                    stripped = "00:" + stripped
                fixed_parts.append(stripped)
            timing = " --> ".join(fixed_parts)
            # Fix timestamp separators: . → , (after hour-padding so regex matches)
            timing = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", timing)

            srt_lines.append(str(block_num))
            srt_lines.append(timing)
            i += 1
            while i < len(lines) and lines[i].strip() and "-->" not in lines[i]:
                # Strip VTT positioning tags like <c> </c> and alignment tags
                text = re.sub(r"<[^>]+>", "", lines[i].strip())
                if text:
                    srt_lines.append(text)
                i += 1
            srt_lines.append("")  # blank line between blocks
        else:
            i += 1

    return "\n".join(srt_lines)
