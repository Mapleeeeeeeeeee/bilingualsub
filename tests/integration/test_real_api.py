"""Integration tests using real Groq API (no mocks).

These tests call the actual Groq Whisper and Groq LLM APIs.
They are automatically skipped when GROQ_API_KEY is not set.
"""

import struct
import wave
from datetime import timedelta
from pathlib import Path

import pytest

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.core.transcriber import TranscriptionError, transcribe_audio
from bilingualsub.core.translator import translate_subtitle
from tests.integration.conftest import requires_groq_api


def create_silent_wav(
    path: Path,
    duration_seconds: float = 1.0,
    sample_rate: int = 16000,
) -> Path:
    """Create a silent WAV file for testing."""
    num_frames = int(sample_rate * duration_seconds)
    with wave.open(str(path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        silence = struct.pack("<" + "h" * num_frames, *([0] * num_frames))
        wav_file.writeframes(silence)
    return path


@pytest.mark.integration
@requires_groq_api
class TestRealGroqTranscription:
    """Tests that call the real Groq Whisper API."""

    def test_transcribe_real_audio_returns_valid_subtitle(
        self,
        tmp_path: Path,
    ) -> None:
        """Transcribing a silent WAV returns Subtitle or raises TranscriptionError."""
        wav_path = create_silent_wav(tmp_path / "silence.wav")

        # A silent file may produce a valid Subtitle or raise
        # TranscriptionError if Whisper cannot parse it.
        try:
            result = transcribe_audio(wav_path)
            assert isinstance(result, Subtitle)
        except TranscriptionError:
            # Silence may cause a parse error; this is expected behaviour.
            pass


@pytest.mark.integration
@requires_groq_api
class TestRealGroqTranslation:
    """Tests that call the real Groq LLM translation API."""

    def test_translate_real_subtitle_returns_valid_result(self) -> None:
        """Single-entry translation returns correct structure."""
        subtitle = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(0),
                    end=timedelta(seconds=3),
                    text="Hello world",
                ),
            ]
        )

        result = translate_subtitle(subtitle, source_lang="en", target_lang="zh-TW")

        assert isinstance(result, Subtitle)
        assert len(result.entries) == 1
        assert result.entries[0].text.strip()
        assert result.entries[0].index == 1
        assert result.entries[0].start == timedelta(0)
        assert result.entries[0].end == timedelta(seconds=3)

    def test_translate_multiple_entries_preserves_count_and_timing(
        self,
    ) -> None:
        """Multi-entry translation preserves count, index, and timing."""
        subtitle = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=0),
                    end=timedelta(seconds=3),
                    text="Good morning",
                ),
                SubtitleEntry(
                    index=2,
                    start=timedelta(seconds=4),
                    end=timedelta(seconds=7),
                    text="How are you today",
                ),
            ]
        )

        result = translate_subtitle(subtitle, source_lang="en", target_lang="zh-TW")

        assert isinstance(result, Subtitle)
        assert len(result.entries) == 2

        for orig, translated in zip(subtitle.entries, result.entries, strict=True):
            assert translated.index == orig.index
            assert translated.start == orig.start
            assert translated.end == orig.end
            assert translated.text.strip()


@pytest.mark.integration
@requires_groq_api
class TestRealTranscribeThenTranslate:
    """End-to-end test: real transcription followed by real translation."""

    def test_real_transcription_feeds_into_real_translation(
        self,
        tmp_path: Path,
    ) -> None:
        """Transcribe a silent WAV then translate the result."""
        wav_path = create_silent_wav(tmp_path / "silence.wav")

        try:
            transcribed = transcribe_audio(wav_path)
        except TranscriptionError:
            pytest.skip("Silence transcription not supported by API")

        translated = translate_subtitle(
            transcribed, source_lang="en", target_lang="zh-TW"
        )

        assert isinstance(translated, Subtitle)
        assert len(translated.entries) == len(transcribed.entries)

        for orig, result in zip(transcribed.entries, translated.entries, strict=True):
            assert result.index == orig.index
            assert result.start == orig.start
            assert result.end == orig.end
            assert result.text.strip()
