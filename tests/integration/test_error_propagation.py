"""Integration tests for cross-module error propagation."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from bilingualsub.core.merger import merge_subtitles
from bilingualsub.core.subtitle import Subtitle
from bilingualsub.core.transcriber import TranscriptionError, transcribe_audio
from bilingualsub.core.translator import TranslationError, translate_subtitle
from bilingualsub.formats.srt import parse_srt, serialize_srt


@pytest.mark.integration
class TestErrorPropagation:
    """Verify cross-module error propagation behavior."""

    def test_when_transcriber_returns_malformed_response_then_transcription_error_raised(
        self,
        tmp_path,
        set_fake_api_key,
    ):
        """Malformed verbose_json response from Groq API raises TranscriptionError."""
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio content")

        with patch("bilingualsub.core.transcriber.Groq") as mock_groq:
            mock_client = MagicMock()
            mock_groq.return_value = mock_client
            response = Mock()
            response.segments = [
                {"id": 0, "start": 0.0, "end": 1.0}  # missing "text" key
            ]
            mock_client.audio.transcriptions.create.return_value = response

            with pytest.raises(TranscriptionError, match="Failed to parse"):
                transcribe_audio(audio_path)

            # Verify exception chaining
            try:
                transcribe_audio(audio_path)
            except TranscriptionError as exc:
                assert exc.__cause__ is not None

    def test_when_translator_returns_empty_text_then_translation_error_raised(
        self,
        set_fake_api_key,
        sample_subtitle_3_entries,
    ):
        """Whitespace-only translation response raises TranslationError."""
        with patch("bilingualsub.core.translator.Agent") as mock_agent:
            mock_translator = Mock()
            mock_agent.return_value = mock_translator

            resp = Mock()
            resp.content = "   "
            mock_translator.run.return_value = resp

            with pytest.raises(
                TranslationError,
                match="Empty or whitespace-only translation",
            ):
                translate_subtitle(sample_subtitle_3_entries)

    def test_when_translator_returns_fewer_entries_then_merger_raises_error(
        self,
        sample_subtitle_3_entries,
        sample_translated_3_entries,
    ):
        """Mismatched entry counts between original and translated raise ValueError."""
        original = sample_subtitle_3_entries.entries  # 3 entries
        translated = sample_translated_3_entries.entries[:2]  # 2 entries

        with pytest.raises(ValueError, match="Entry count mismatch"):
            merge_subtitles(original, translated)

    def test_when_merged_bilingual_text_has_newlines_then_srt_round_trips_correctly(
        self,
        sample_subtitle_3_entries,
        sample_translated_3_entries,
    ):
        """Bilingual merged text with newlines survives SRT serialize/parse round-trip."""
        merged = merge_subtitles(
            sample_subtitle_3_entries.entries,
            sample_translated_3_entries.entries,
        )

        bilingual_subtitle = Subtitle(entries=merged)
        serialized = serialize_srt(bilingual_subtitle)
        round_tripped = parse_srt(serialized)

        assert len(round_tripped.entries) == len(merged)
        for original, restored in zip(merged, round_tripped.entries, strict=True):
            assert restored.text == original.text
            assert "\n" in restored.text

    def test_when_config_missing_api_key_then_transcriber_raises_value_error(
        self,
        tmp_path,
        no_env_file,
        monkeypatch,
    ):
        """Missing GROQ_API_KEY causes transcribe_audio to raise ValueError."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio content")

        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            transcribe_audio(audio_path)

    def test_when_config_missing_api_key_then_translator_raises_value_error(
        self,
        no_env_file,
        monkeypatch,
        sample_subtitle_3_entries,
    ):
        """Missing GROQ_API_KEY causes translate_subtitle to raise ValueError."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            translate_subtitle(sample_subtitle_3_entries)
