"""Shared subtitle segmentation preserving source cue boundaries."""

import re
from datetime import timedelta

from bilingualsub.core.subtitle import SubtitleEntry


def split_at_phrase_boundaries(
    entries: list[SubtitleEntry],
    *,
    max_duration_sec: float,
    max_chars: int,
) -> list[SubtitleEntry]:
    """Split long cues at conservative punctuation or English clause boundaries.

    Limits are targets: text with no eligible boundary remains intact. Clause
    detection is heuristic, not grammatical parsing. Inner times are estimated
    from text length; source cue boundaries and gaps remain unchanged.
    """
    result: list[SubtitleEntry] = []
    for entry in entries:
        pending = [entry]
        while pending:
            current = pending.pop()
            duration = (current.end - current.start).total_seconds()
            if duration <= max_duration_sec and len(current.text) <= max_chars:
                result.append(current)
                continue
            boundaries = [
                match.end()
                for match in re.finditer(
                    r"(?:[.!?,;](?:\s+|$)|[\u3002\uff01\uff1f\u3001\uff0c\uff1b]\s*)",
                    current.text,
                )
            ]
            boundaries.extend(
                match.start()
                for match in re.finditer(
                    r"\b(?:that|which|who|where|when|because|although|while|and|or|but)\b",
                    current.text,
                    flags=re.IGNORECASE,
                )
            )
            candidates = [
                boundary
                for boundary in boundaries
                if not _is_short_text(current.text[:boundary].strip(), 3, 6)
                and not _is_short_text(current.text[boundary:].strip(), 3, 6)
            ]
            if not candidates:
                result.append(current)
                continue
            target_length = min(
                max_chars, len(current.text) * max_duration_sec / duration
            )
            boundary = min(candidates, key=lambda value: abs(value - target_length))
            left = current.text[:boundary].strip()
            right = current.text[boundary:].strip()
            split_time = current.start + (current.end - current.start) * (
                len(left) / (len(left) + len(right))
            )
            pending.extend(
                [
                    SubtitleEntry(1, split_time, current.end, right),
                    SubtitleEntry(1, current.start, split_time, left),
                ]
            )
    return [
        SubtitleEntry(index, entry.start, entry.end, entry.text)
        for index, entry in enumerate(result, start=1)
    ]


def _has_cjk(text: str) -> bool:
    """Check if the text contains CJK characters (Chinese, Japanese, or Korean)."""
    return any(
        "\u4e00" <= c <= "\u9fff"  # CJK Unified Ideographs
        or "\u3400" <= c <= "\u4dbf"  # Extension A
        or "\uf900" <= c <= "\ufaff"  # Compatibility Ideographs
        or "\u3040" <= c <= "\u309f"  # Hiragana
        or "\u30a0" <= c <= "\u30ff"  # Katakana
        or "\uac00" <= c <= "\ud7af"  # Hangul Syllables
        or "\u1100" <= c <= "\u11ff"  # Hangul Jamo
        or "\u3000" <= c <= "\u303f"  # CJK Symbols and Punctuation (e.g. 。、)
        for c in text
    )


def _is_short_text(text: str, min_words: int, min_cjk_chars: int) -> bool:
    """Check if the text segment is too short."""
    if _has_cjk(text):
        return len(text) < min_cjk_chars
    return len(text.split()) < min_words


def _split_long_part_by_length(
    part: str,
    part_duration: float,
    max_duration_sec: float,
    max_chars: int,
    min_words: int,
    min_cjk_chars: int,
) -> list[str]:
    """Force-split a long text part into length/duration-restricted chunks."""
    has_cjk = _has_cjk(part)

    if has_cjk:
        if part_duration > 0:
            chars_per_sec = len(part) / part_duration
            max_len_by_dur = max(1, int(chars_per_sec * max_duration_sec))
            chunk_size = min(max_chars, max_len_by_dur)
        else:
            chunk_size = max_chars

        chunks = [part[i : i + chunk_size] for i in range(0, len(part), chunk_size)]
        if len(chunks) > 1 and _is_short_text(chunks[-1], min_words, min_cjk_chars):
            merged_len = len(chunks[-2]) + len(chunks[-1])
            merged_duration = part_duration * (merged_len / len(part))
            if merged_len <= max_chars and merged_duration <= max_duration_sec:
                chunks[-2] = chunks[-2] + chunks[-1]
                chunks.pop()
        return chunks

    words = part.split()
    if not words:
        return []

    if part_duration > 0:
        words_per_sec = len(words) / part_duration
        max_words_by_dur = max(1, int(words_per_sec * max_duration_sec))
    else:
        max_words_by_dur = len(words)

    word_chunks = []
    current_chunk: list[str] = []

    for word in words:
        prospective_len = len(" ".join([*current_chunk, word]))
        if current_chunk and (
            prospective_len > max_chars or len(current_chunk) >= max_words_by_dur
        ):
            word_chunks.append(" ".join(current_chunk))
            current_chunk = [word]
        else:
            current_chunk.append(word)

    if current_chunk:
        word_chunks.append(" ".join(current_chunk))

    if len(word_chunks) > 1 and _is_short_text(
        word_chunks[-1], min_words, min_cjk_chars
    ):
        merged_text = f"{word_chunks[-2]} {word_chunks[-1]}"
        merged_words = merged_text.split()
        merged_duration = part_duration * (len(merged_text) / len(part))
        if (
            len(merged_text) <= max_chars
            and len(merged_words) <= max_words_by_dur
            and merged_duration <= max_duration_sec
        ):
            word_chunks[-2] = merged_text
            word_chunks.pop()

    return word_chunks


def split_long_entries(
    entries: list[SubtitleEntry],
    max_duration_sec: float = 6.0,
    max_chars: int = 80,
    min_words: int = 4,
    min_cjk_chars: int = 6,
) -> list[SubtitleEntry]:
    """Split long subtitle entries.

    Splits based on duration, character count, and CJK boundaries,
    ensuring split parts are not too short.
    """
    new_entries = []
    current_index = 1

    for entry in entries:
        duration = (entry.end - entry.start).total_seconds()
        if duration <= max_duration_sec and len(entry.text) <= max_chars:
            new_entries.append(
                SubtitleEntry(
                    index=current_index,
                    start=entry.start,
                    end=entry.end,
                    text=entry.text,
                )
            )
            current_index += 1
            continue

        # Split by punctuation first (sentences and clauses)
        raw_parts = re.split(
            r"(?<=[.?!,;\uff0c\uff1b\u3002\uff01\uff1f\u3001])\s*", entry.text
        )
        parts = [p.strip() for p in raw_parts if p.strip()]

        # Merge adjacent parts that are too short,
        # but only if the merged part is <= max_duration_sec
        merged_parts: list[str] = []
        for part in parts:
            if not merged_parts:
                merged_parts.append(part)
                continue

            part_duration = duration * (len(part) / len(entry.text))
            last_duration = duration * (len(merged_parts[-1]) / len(entry.text))

            if (
                _is_short_text(part, min_words, min_cjk_chars)
                or _is_short_text(merged_parts[-1], min_words, min_cjk_chars)
            ) and (part_duration + last_duration <= max_duration_sec):
                last_part = merged_parts[-1]
                has_cjk = _has_cjk(last_part + part)
                if has_cjk:
                    merged_parts[-1] = f"{last_part}{part}"
                else:
                    merged_parts[-1] = f"{last_part} {part}"
            else:
                merged_parts.append(part)

        # Split remaining long parts by length chunks
        refined_parts = []
        for part in merged_parts:
            part_duration = duration * (len(part) / len(entry.text))
            if part_duration > max_duration_sec or len(part) > max_chars:
                chunks = _split_long_part_by_length(
                    part,
                    part_duration,
                    max_duration_sec,
                    max_chars,
                    min_words,
                    min_cjk_chars,
                )
                refined_parts.extend(chunks)
            else:
                refined_parts.append(part)

        total_len = sum(len(p) for p in refined_parts)
        if total_len == 0:
            new_entries.append(
                SubtitleEntry(
                    index=current_index,
                    start=entry.start,
                    end=entry.end,
                    text=entry.text,
                )
            )
            current_index += 1
            continue

        current_time = entry.start
        for idx, part in enumerate(refined_parts):
            part_ratio = len(part) / total_len
            part_dur = timedelta(seconds=duration * part_ratio)
            part_end = current_time + part_dur

            if idx == len(refined_parts) - 1:
                part_end = entry.end

            if part_end > current_time:
                new_entries.append(
                    SubtitleEntry(
                        index=current_index,
                        start=current_time,
                        end=part_end,
                        text=part,
                    )
                )
                current_index += 1
                current_time = part_end

    return new_entries
