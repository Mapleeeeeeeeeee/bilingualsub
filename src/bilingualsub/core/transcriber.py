"""Audio transcription using Groq Whisper API."""

from datetime import timedelta
from pathlib import Path
from typing import Any

from groq import Groq

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.utils.config import get_groq_api_key


class TranscriptionError(Exception):
    """Raised when audio transcription fails."""


def transcribe_audio(audio_path: Path, *, language: str = "en") -> Subtitle:
    """
    Transcribe audio file to subtitle using Groq Whisper API.

    Args:
        audio_path: Path to audio/video file
        language: ISO 639-1 language code (e.g., "en", "zh", "ja")

    Returns:
        Subtitle object with transcribed entries

    Raises:
        TranscriptionError: If transcription fails
        ValueError: If audio_path is invalid or API key is missing
    """
    # Validate inputs
    if not audio_path.exists():
        raise ValueError(f"Audio file does not exist: {audio_path}")

    if not audio_path.is_file():
        raise ValueError(f"Audio path is not a file: {audio_path}")

    # Check file size (Groq has 25MB limit)
    file_size_mb = audio_path.stat().st_size / (1024 * 1024)
    if file_size_mb > 25:
        raise ValueError(
            f"File size {file_size_mb:.1f}MB exceeds Groq's 25MB limit. "
            "Please compress the audio or split into smaller chunks."
        )

    # Get API key from config
    api_key = get_groq_api_key()

    # Normalize language code to ISO 639-1 (e.g., "zh-TW" -> "zh")
    language = language.split("-")[0]

    # Initialize Groq client
    client = Groq(api_key=api_key)

    # Transcribe audio
    try:
        with audio_path.open("rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=(audio_path.name, audio_file),
                model="whisper-large-v3-turbo",
                response_format="verbose_json",
                language=language,
            )
    except Exception as e:
        raise TranscriptionError(f"Failed to transcribe audio: {e}") from e

    # Parse verbose_json response into Subtitle
    try:
        segments: list[dict[str, Any]] = transcription.segments  # type: ignore[attr-defined]
        if not segments:
            raise TranscriptionError("Transcription returned no segments")

        entries = []
        for i, seg in enumerate(segments, start=1):
            entry = SubtitleEntry(
                index=i,
                start=timedelta(seconds=seg["start"]),
                end=timedelta(seconds=seg["end"]),
                text=seg["text"].strip(),
            )
            entries.append(entry)

        return Subtitle(entries=entries)
    except TranscriptionError:
        raise
    except Exception as e:
        raise TranscriptionError(f"Failed to parse transcription result: {e}") from e
