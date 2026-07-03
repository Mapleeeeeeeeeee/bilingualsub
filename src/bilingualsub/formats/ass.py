"""ASS (Advanced SubStation Alpha) format serializer for bilingual subtitles."""

from dataclasses import dataclass
from datetime import timedelta
from math import ceil

from bilingualsub.core.subtitle import Subtitle

_PLAY_RES_X = 1920
_PLAY_RES_Y = 1080
_SUBTITLE_MAX_WIDTH = 1680
_SUBTITLE_BOTTOM_MARGIN = 82
_SUBTITLE_LINE_GAP = 14
_SUBTITLE_MAX_GROUP_HEIGHT = 220
_TRANSLATED_FONT_SIZES = (46, 44, 42)
_ORIGINAL_FONT_SIZES = (26, 24, 22)
_TRANSLATED_LINE_HEIGHT = 1.18
_ORIGINAL_LINE_HEIGHT = 1.18


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
    # ASS colors are BGR. Font sizes and positions are applied per dialogue so
    # each subtitle pair can stay grouped when the original wraps to multiple lines.
    trans_style = (
        "Style: Translated,Arial,46,"
        "&H0000FFFF,&H0000FFFF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,3,0,8,60,60,0,1"
    )
    orig_style = (
        "Style: Original,Arial,26,"
        "&H00909090,&H00909090,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,0,8,60,60,0,1"
    )
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

        layout = _layout_bilingual_pair(trans_entry.text, orig_entry.text)

        # Add translated line (top of the grouped subtitle block)
        trans_text = _escape_ass_text(layout.translated_text)
        trans_override = (
            f"{{\\an8\\pos({layout.x},{layout.translated_y})"
            f"\\fs{layout.translated_font_size}\\q2}}"
        )
        dialogue_lines.append(
            f"Dialogue: 0,{start_time},{end_time},Translated,,0,0,0,,"
            f"{trans_override}{trans_text}"
        )

        # Add original line (lower, secondary reference text)
        orig_text = _escape_ass_text(layout.original_text)
        orig_override = (
            f"{{\\an8\\pos({layout.x},{layout.original_y})"
            f"\\fs{layout.original_font_size}\\q2}}"
        )
        dialogue_lines.append(
            f"Dialogue: 0,{start_time},{end_time},Original,,0,0,0,,"
            f"{orig_override}{orig_text}"
        )

    return header + "\n".join(dialogue_lines) + "\n"


@dataclass(frozen=True)
class _SubtitleLayout:
    translated_text: str
    original_text: str
    translated_font_size: int
    original_font_size: int
    x: int
    translated_y: int
    original_y: int


def _layout_bilingual_pair(translated_text: str, original_text: str) -> _SubtitleLayout:
    """Return wrapped text and top-anchored positions for one bilingual pair."""
    best_layout: _SubtitleLayout | None = None
    for trans_size, orig_size in zip(
        _TRANSLATED_FONT_SIZES, _ORIGINAL_FONT_SIZES, strict=True
    ):
        trans_wrapped = _wrap_text(translated_text, trans_size)
        orig_wrapped = _wrap_text(original_text, orig_size)
        trans_lines = trans_wrapped.count("\n") + 1
        orig_lines = orig_wrapped.count("\n") + 1
        trans_height = ceil(trans_lines * trans_size * _TRANSLATED_LINE_HEIGHT)
        group_height = (
            trans_height
            + _SUBTITLE_LINE_GAP
            + ceil(orig_lines * orig_size * _ORIGINAL_LINE_HEIGHT)
        )
        trans_y = max(
            0,
            _PLAY_RES_Y - _SUBTITLE_BOTTOM_MARGIN - group_height,
        )
        layout = _SubtitleLayout(
            translated_text=trans_wrapped,
            original_text=orig_wrapped,
            translated_font_size=trans_size,
            original_font_size=orig_size,
            x=_PLAY_RES_X // 2,
            translated_y=trans_y,
            original_y=trans_y + trans_height + _SUBTITLE_LINE_GAP,
        )
        best_layout = layout
        if group_height <= _SUBTITLE_MAX_GROUP_HEIGHT:
            return layout

    if best_layout is None:
        raise ValueError("No subtitle layout candidates configured")
    return best_layout


def _wrap_text(text: str, font_size: int) -> str:
    """Wrap text to a rough ASS pixel width using language-aware units."""
    lines = []
    for raw_line in text.splitlines() or [""]:
        units = _split_wrap_units(raw_line)
        current = ""
        current_width = 0.0
        for unit in units:
            unit_width = _estimate_text_width(unit, font_size)
            if current and current_width + unit_width > _SUBTITLE_MAX_WIDTH:
                lines.append(current.rstrip())
                current = unit.lstrip()
                current_width = _estimate_text_width(current, font_size)
            else:
                current += unit
                current_width += unit_width
        lines.append(current.rstrip())
    return "\n".join(lines)


def _split_wrap_units(text: str) -> list[str]:
    """Split CJK per character and Latin text by whitespace-preserving words."""
    units: list[str] = []
    current = ""
    for char in text:
        if _is_cjk(char):
            if current:
                units.append(current)
                current = ""
            units.append(char)
        else:
            current += char
            if char.isspace():
                units.append(current)
                current = ""
    if current:
        units.append(current)
    return units


def _estimate_text_width(text: str, font_size: int) -> float:
    """Estimate rendered width enough to make wrapping deterministic."""
    width = 0.0
    for char in text:
        if _is_cjk(char):
            width += font_size
        elif char.isspace():
            width += font_size * 0.35
        elif char in ".,;:!|'`ijlI[](){}":
            width += font_size * 0.32
        elif char in "mwMW@#%&":
            width += font_size * 0.9
        else:
            width += font_size * 0.56
    return width


def _is_cjk(char: str) -> bool:
    return (
        "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
    )


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
