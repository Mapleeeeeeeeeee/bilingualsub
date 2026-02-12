"""SRT format parser and serializer."""

import re
from datetime import timedelta

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry


class SRTParseError(Exception):
    """Exception raised when SRT parsing fails."""


def parse_srt(content: str) -> Subtitle:
    """Parse SRT format string into Subtitle object.

    Args:
        content: SRT format string content

    Returns:
        Subtitle object containing parsed entries

    Raises:
        SRTParseError: If content is invalid or malformed
    """
    if not content.strip():
        raise SRTParseError("Content cannot be empty")

    # Split into blocks by double newlines
    blocks = re.split(r"\n\n+", content.strip())

    entries = []
    for block_num, block in enumerate(blocks, start=1):
        lines = block.strip().split("\n")

        if len(lines) < 3:
            raise SRTParseError(
                f"Block {block_num}: Invalid format, expected at least 3 lines "
                f"(index, timing, text), got {len(lines)}"
            )

        # Parse index
        try:
            index = int(lines[0].strip())
        except ValueError as e:
            raise SRTParseError(
                f"Block {block_num}: Invalid index '{lines[0].strip()}', "
                "must be integer"
            ) from e

        # Parse timing line
        timing_line = lines[1].strip()
        timing_match = re.match(
            r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})",
            timing_line,
        )

        if not timing_match:
            raise SRTParseError(
                f"Block {block_num}: Invalid timing format '{timing_line}', "
                f"expected 'HH:MM:SS,mmm --> HH:MM:SS,mmm'"
            )

        groups = timing_match.groups()
        start = timedelta(
            hours=int(groups[0]),
            minutes=int(groups[1]),
            seconds=int(groups[2]),
            milliseconds=int(groups[3]),
        )
        end = timedelta(
            hours=int(groups[4]),
            minutes=int(groups[5]),
            seconds=int(groups[6]),
            milliseconds=int(groups[7]),
        )

        # Parse text (remaining lines)
        text = "\n".join(lines[2:]).strip()

        try:
            entry = SubtitleEntry(index=index, start=start, end=end, text=text)
            entries.append(entry)
        except ValueError as e:
            raise SRTParseError(f"Block {block_num}: {e}") from e

    if not entries:
        raise SRTParseError("No valid subtitle entries found")

    try:
        return Subtitle(entries=entries)
    except ValueError as e:
        raise SRTParseError(f"Invalid subtitle structure: {e}") from e


def serialize_srt(subtitle: Subtitle) -> str:
    """Serialize Subtitle object to SRT format string.

    Args:
        subtitle: Subtitle object to serialize

    Returns:
        SRT format string
    """
    blocks = []

    for entry in subtitle.entries:
        # Format timing - use total_seconds() to handle durations > 24 hours
        total_start_seconds = int(entry.start.total_seconds())
        start_hours = total_start_seconds // 3600
        start_minutes = (total_start_seconds % 3600) // 60
        start_seconds = total_start_seconds % 60
        start_millis = entry.start.microseconds // 1000

        total_end_seconds = int(entry.end.total_seconds())
        end_hours = total_end_seconds // 3600
        end_minutes = (total_end_seconds % 3600) // 60
        end_seconds = total_end_seconds % 60
        end_millis = entry.end.microseconds // 1000

        start_str = f"{start_hours:02d}:{start_minutes:02d}:{start_seconds:02d}"
        end_str = f"{end_hours:02d}:{end_minutes:02d}:{end_seconds:02d}"
        timing = f"{start_str},{start_millis:03d} --> {end_str},{end_millis:03d}"

        # Build block
        block = f"{entry.index}\n{timing}\n{entry.text}"
        blocks.append(block)

    return "\n\n".join(blocks) + "\n"
