"""Audio transcription using Groq Whisper API."""

import os
from pathlib import Path

from groq import Groq

from bilingualsub.core.subtitle import Subtitle
from bilingualsub.formats.srt import parse_srt


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

    # Check API key
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY environment variable is not set. "
            "Please set it with your Groq API key."
        )

    # Initialize Groq client
    client = Groq(api_key=api_key)

    # Transcribe audio
    try:
        with audio_path.open("rb") as audio_file:
            # Note: response_format="srt" returns a string, not a Transcription object
            # The SDK type hints may show this as incorrect, but it works at runtime
            # Pass file handle directly to avoid reading entire file into memory
            transcription = client.audio.transcriptions.create(
                file=(audio_path.name, audio_file),
                model="whisper-large-v3-turbo",
                response_format="srt",  # type: ignore[arg-type]
                language=language,
            )
    except Exception as e:
        raise TranscriptionError(f"Failed to transcribe audio: {e}") from e

    # Parse SRT response (transcription is a string when response_format="srt")
    try:
        return parse_srt(str(transcription))
    except Exception as e:
        raise TranscriptionError(f"Failed to parse transcription result: {e}") from e
