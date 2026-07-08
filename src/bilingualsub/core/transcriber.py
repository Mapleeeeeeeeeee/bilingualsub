"""Audio transcription using Whisper API (Groq or OpenAI)."""

import re
from datetime import timedelta
from pathlib import Path
from typing import Any

from groq import Groq
from openai import OpenAI

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.utils.config import get_groq_api_key, get_openai_api_key, get_settings
from bilingualsub.utils.ffmpeg import split_audio

_MAX_WHISPER_PROMPT_CHARS = 800


class TranscriptionError(Exception):
    """Raised when audio transcription fails."""


def build_whisper_prompt(
    video_title: str = "",
) -> str | None:
    """Build a concise Whisper hint from the video title.

    Args:
        video_title: Raw video title string.

    Returns:
        Cleaned title string, or None if the title is blank.
    """
    title = video_title.strip()
    if not title:
        return None
    if len(title) > _MAX_WHISPER_PROMPT_CHARS:
        return title[:_MAX_WHISPER_PROMPT_CHARS]
    return title


def _transcribe_single(
    audio_path: Path, *, language: str, settings: Any, prompt: str | None = None
) -> Subtitle:
    """Transcribe a single audio file (must be <= 25MB).

    Args:
        audio_path: Path to audio file
        language: ISO 639-1 language code
        settings: Application settings
        prompt: Optional hint text to guide transcription accuracy

    Returns:
        Subtitle object with transcribed entries

    Raises:
        TranscriptionError: If transcription fails
        ValueError: If API key is missing or provider is unknown
    """
    provider = settings.transcriber_provider

    client: Any
    if provider == "groq":
        client = Groq(api_key=get_groq_api_key())
    elif provider == "openai":
        client = OpenAI(api_key=get_openai_api_key())
    else:
        raise ValueError(
            f"Unknown transcriber provider: {provider}. Use 'groq' or 'openai'."
        )

    try:
        with audio_path.open("rb") as audio_file:
            create_kwargs: dict[str, Any] = {
                "file": (audio_path.name, audio_file),
                "model": settings.transcriber_model,
                "response_format": "verbose_json",
                "language": language,
            }
            if prompt:
                create_kwargs["prompt"] = prompt
            transcription = client.audio.transcriptions.create(**create_kwargs)
    except Exception as e:
        raise TranscriptionError(f"Failed to transcribe audio: {e}") from e

    try:
        segments: list[dict[str, Any]] = transcription.segments
        if not segments:
            raise TranscriptionError("Transcription returned no segments")

        entries = [
            SubtitleEntry(
                index=i,
                start=timedelta(seconds=seg["start"]),
                end=timedelta(seconds=seg["end"]),
                text=seg["text"].strip(),
            )
            for i, seg in enumerate(
                (s for s in segments if s["start"] < s["end"] and s["text"].strip()),
                start=1,
            )
        ]

        if not entries:
            raise TranscriptionError("No valid segments after filtering")

        return Subtitle(entries=entries)
    except TranscriptionError:
        raise
    except Exception as e:
        raise TranscriptionError(f"Failed to parse transcription result: {e}") from e


def _split_long_entries(
    entries: list[SubtitleEntry],
    max_duration_sec: float = 6.0,
    max_chars: int = 80,
) -> list[SubtitleEntry]:
    """Split long subtitle entries.

    Splits based on duration, character count, and CJK boundaries.
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

        # Split by sentence endings first
        raw_parts = re.split(r"(?<=[.?!])\s+", entry.text)
        parts = [p.strip() for p in raw_parts if p.strip()]

        refined_parts = []
        for part in parts:
            part_duration = duration * (len(part) / len(entry.text))
            if part_duration > max_duration_sec or len(part) > max_chars:
                # Split by clause boundaries (commas and semicolons)
                # \uff0c is fullwidth comma, \uff1b is fullwidth semicolon
                comma_parts = re.split(r"(?<=[,;\uff0c\uff1b])\s*", part)
                comma_parts = [cp.strip() for cp in comma_parts if cp.strip()]

                for cp in comma_parts:
                    cp_duration = duration * (len(cp) / len(entry.text))
                    if cp_duration > max_duration_sec or len(cp) > max_chars:
                        # Split by space (words) for non-CJK,
                        # or by character count for CJK
                        has_cjk = any(
                            "\u3400" <= c <= "\u4dbf"
                            or "\u4e00" <= c <= "\u9fff"
                            or "\uf900" <= c <= "\ufaff"
                            for c in cp
                        )
                        if has_cjk:
                            chunk_size = 15
                            chunks = [
                                cp[i : i + chunk_size]
                                for i in range(0, len(cp), chunk_size)
                            ]
                            refined_parts.extend(chunks)
                        else:
                            words = cp.split()
                            chunk_size = 10
                            word_chunks = []
                            for i in range(0, len(words), chunk_size):
                                chunk = " ".join(words[i : i + chunk_size])
                                if chunk:
                                    word_chunks.append(chunk)
                            refined_parts.extend(word_chunks)
                    else:
                        refined_parts.append(cp)
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
        for part in refined_parts:
            part_ratio = len(part) / total_len
            part_dur = timedelta(seconds=duration * part_ratio)
            part_end = current_time + part_dur

            if part == refined_parts[-1]:
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


def transcribe_audio(
    audio_path: Path, *, language: str = "en", prompt: str | None = None
) -> Subtitle:
    """
    Transcribe audio file to subtitle using Whisper API.

    For files > 25MB, automatically splits into chunks and merges results.

    Args:
        audio_path: Path to audio/video file
        language: ISO 639-1 language code (e.g., "en", "zh", "ja")
        prompt: Optional hint text (e.g., from build_whisper_prompt) to improve
                proper noun recognition

    Returns:
        Subtitle object with transcribed entries

    Raises:
        TranscriptionError: If transcription fails
        ValueError: If audio_path is invalid or API key is missing
    """
    if not audio_path.exists():
        raise ValueError(f"Audio file does not exist: {audio_path}")

    if not audio_path.is_file():
        raise ValueError(f"Audio path is not a file: {audio_path}")

    language = language.split("-", maxsplit=1)[0]
    settings = get_settings()

    file_size_mb = audio_path.stat().st_size / (1024 * 1024)
    if file_size_mb <= 25:
        subtitle = _transcribe_single(
            audio_path, language=language, settings=settings, prompt=prompt
        )
        all_entries = subtitle.entries
    else:
        # Large file: split into chunks and transcribe each
        chunks = split_audio(audio_path, output_dir=audio_path.parent)
        all_entries = []
        idx = 1
        for chunk_path, time_offset in chunks:
            subtitle = _transcribe_single(
                chunk_path, language=language, settings=settings, prompt=prompt
            )
            offset_td = timedelta(seconds=time_offset)
            for entry in subtitle.entries:
                all_entries.append(
                    SubtitleEntry(
                        index=idx,
                        start=entry.start + offset_td,
                        end=entry.end + offset_td,
                        text=entry.text,
                    )
                )
                idx += 1

    # Split long entries before returning
    split_entries = _split_long_entries(all_entries)
    return Subtitle(entries=split_entries)
