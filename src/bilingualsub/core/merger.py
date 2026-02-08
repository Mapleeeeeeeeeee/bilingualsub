"""Merge original and translated subtitle entries into bilingual format."""

from collections.abc import Sequence

from bilingualsub.core.subtitle import SubtitleEntry


def merge_subtitles(
    original: Sequence[SubtitleEntry],
    translated: Sequence[SubtitleEntry],
) -> list[SubtitleEntry]:
    """Merge original and translated subtitles into bilingual format.

    Args:
        original: Original subtitle entries (source of timing)
        translated: Translated subtitle entries

    Returns:
        List of bilingual subtitle entries with format:
        "{translated}\\n{original}"

    Raises:
        ValueError: If entry counts don't match

    Notes:
        - Matches entries by index (entry[0] with entry[0])
        - Uses original timing as it's most accurate from transcription
        - Uses fixed format: translated line, then original line
        - Preserves all timing information from original entries
    """
    if len(original) != len(translated):
        raise ValueError(
            f"Entry count mismatch: original has {len(original)} entries, "
            f"translated has {len(translated)} entries"
        )

    merged = []
    for orig, trans in zip(original, translated, strict=True):
        bilingual_text = f"{trans.text}\n{orig.text}"
        merged_entry = SubtitleEntry(
            index=orig.index,
            start=orig.start,
            end=orig.end,
            text=bilingual_text,
        )
        merged.append(merged_entry)

    return merged
