"""ASS (Advanced SubStation Alpha) format serializer for bilingual subtitles."""

from datetime import timedelta

from bilingualsub.core.subtitle import Subtitle


def serialize_bilingual_ass(
    original: Subtitle, translated: Subtitle, *, video_width: int, video_height: int
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
    """
    if len(original.entries) != len(translated.entries):
        raise ValueError(
            f"Original and translated subtitles must have same number of entries: "
            f"got {len(original.entries)} vs {len(translated.entries)}"
        )

    # ASS header with fixed styling
    header = f"""[Script Info]
Title: Bilingual Subtitle
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Translated,Arial,20,&H0000FFFF,&H0000FFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,40,1
Style: Original,Arial,20,&H0000FFFF,&H0000FFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Build dialogue lines
    dialogue_lines = []
    for orig_entry, trans_entry in zip(original.entries, translated.entries):
        # Format time as H:MM:SS.cc (centiseconds)
        start_time = _format_ass_time(orig_entry.start)
        end_time = _format_ass_time(orig_entry.end)

        # Add translated line (appears higher with MarginV=40)
        trans_text = _escape_ass_text(trans_entry.text)
        dialogue_lines.append(
            f"Dialogue: 0,{start_time},{end_time},Translated,,0,0,0,,{trans_text}"
        )

        # Add original line (appears lower with MarginV=10, closer to bottom edge)
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
