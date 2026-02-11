"""ASS (Advanced SubStation Alpha) format serializer for bilingual subtitles."""

from datetime import timedelta

from bilingualsub.core.subtitle import Subtitle


def serialize_bilingual_ass(
    original: Subtitle,
    translated: Subtitle,
    *,
    video_width: int,
    video_height: int,
) -> str:
    """Serialize two Subtitle objects to ASS format for bilingual display.

    Args:
        original: Original language subtitle
        translated: Translated language subtitle
        video_width: Video width in pixels for proper positioning
        video_height: Video height in pixels for proper positioning

    Returns:
        ASS format string with bilingual subtitles

    Raises:
        ValueError: If subtitles have mismatched number of entries

    Note:
        video_width and video_height parameters are accepted for API compatibility
        but no longer used internally. PlayRes is fixed at 1920x1080 for consistent
        rendering across all video resolutions.
    """
    # Kept for API compatibility - suppress vulture warnings
    _ = (video_width, video_height)

    if len(original.entries) != len(translated.entries):
        raise ValueError(
            f"Original and translated subtitles must have same number of entries: "
            f"got {len(original.entries)} vs {len(translated.entries)}"
        )

    # ASS header with fixed styling
    # Note: ASS format requires specific long format strings - these are spec-compliant
    style_format = (
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding"
    )
    # Yellow text (&H0000FFFF) with black outline (&H00000000)
    style_params = "&H0000FFFF,&H0000FFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0"
    trans_style = f"Style: Translated,Arial,20,{style_params},1,2,0,2,30,30,60,1"
    orig_style = f"Style: Original,Arial,14,{style_params},1,2,0,2,30,30,20,1"
    event_format = (
        "Format: Layer, Start, End, Style, Name, "
        "MarginL, MarginR, MarginV, Effect, Text"
    )

    header = f"""[Script Info]
Title: Bilingual Subtitle
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
{style_format}
{trans_style}
{orig_style}

[Events]
{event_format}
"""

    # Build dialogue lines
    dialogue_lines = []
    for orig_entry, trans_entry in zip(
        original.entries, translated.entries, strict=True
    ):
        # Format time as H:MM:SS.cc (centiseconds)
        start_time = _format_ass_time(orig_entry.start)
        end_time = _format_ass_time(orig_entry.end)

        # Add translated line (appears higher with MarginV=140)
        trans_text = _escape_ass_text(trans_entry.text)
        dialogue_lines.append(
            f"Dialogue: 0,{start_time},{end_time},Translated,,0,0,0,,{trans_text}"
        )

        # Add original line (appears lower with MarginV=60, closer to bottom edge)
        orig_text = _escape_ass_text(orig_entry.text)
        dialogue_lines.append(
            f"Dialogue: 0,{start_time},{end_time},Original,,0,0,0,,{orig_text}"
        )

    return header + "\n".join(dialogue_lines) + "\n"


def _escape_ass_text(text: str) -> str:
    """Escape special characters for ASS format.

    Args:
        text: Raw text string

    Returns:
        Escaped text safe for ASS format
    """
    # Escape backslash first to avoid double-escaping
    text = text.replace("\\", "\\\\")
    # Escape curly braces to prevent override code injection
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    # Convert newlines to ASS format
    text = text.replace("\n", "\\N")
    return text


def _format_ass_time(td: timedelta) -> str:
    """Format timedelta to ASS time format H:MM:SS.cc (centiseconds).

    Args:
        td: timedelta object

    Returns:
        Time string in H:MM:SS.cc format
    """
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    centiseconds = td.microseconds // 10000

    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"
