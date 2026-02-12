"""Integration tests for transcriber → translator pipeline compatibility."""

from datetime import timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from bilingualsub.core.subtitle import Subtitle
from bilingualsub.core.transcriber import transcribe_audio
from bilingualsub.core.translator import translate_subtitle


@pytest.mark.integration
class TestTranscriberToTranslator:
    """Verify that transcriber output feeds directly into translator."""

    def test_transcriber_output_feeds_directly_to_translator(
        self,
        tmp_path,
        set_fake_api_key,
        sample_whisper_api_response,
        sample_subtitle_3_entries,
    ):
        """Transcribed Subtitle flows into translate_subtitle unchanged."""
        # Create a real audio file for transcriber validation
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio content")

        # Mock Groq client for transcriber
        with patch("bilingualsub.core.transcriber.Groq") as mock_groq:
            mock_client = MagicMock()
            mock_groq.return_value = mock_client
            mock_client.audio.transcriptions.create.return_value = (
                sample_whisper_api_response
            )

            transcribed = transcribe_audio(audio_path)

        # Verify transcriber produced valid Subtitle with correct structure
        assert isinstance(transcribed, Subtitle)
        assert len(transcribed.entries) == 3
        for orig, result in zip(
            sample_subtitle_3_entries.entries, transcribed.entries, strict=True
        ):
            assert result.index == orig.index
            assert result.start == orig.start
            assert result.end == orig.end
            assert result.text == orig.text

        # Feed transcribed output into translator
        chinese_translations = [
            "你好，這是一個測試。",
            "這是第二個字幕。",
            "這是第三個。",
        ]

        with patch("bilingualsub.core.translator.Agent") as mock_agent:
            mock_translator = Mock()
            mock_agent.return_value = mock_translator
            batch_resp = Mock()
            batch_resp.content = (
                "1. 你好，這是一個測試。\n2. 這是第二個字幕。\n3. 這是第三個。"
            )
            mock_translator.run.return_value = batch_resp

            translated = translate_subtitle(transcribed)

        # Verify translated subtitle preserves timing and index
        assert len(translated.entries) == 3
        for i, entry in enumerate(translated.entries):
            assert entry.index == transcribed.entries[i].index
            assert entry.start == transcribed.entries[i].start
            assert entry.end == transcribed.entries[i].end
            assert entry.text == chinese_translations[i]

    def test_transcriber_multiline_output_compatible_with_translator(
        self,
        tmp_path,
        set_fake_api_key,
    ):
        """Multi-line segment text entries are correctly parsed and translated."""
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio content")

        with patch("bilingualsub.core.transcriber.Groq") as mock_groq:
            mock_client = MagicMock()
            mock_groq.return_value = mock_client
            response = Mock()
            response.segments = [
                {"id": 0, "start": 1.0, "end": 4.0, "text": " Line one\nLine two"},
                {
                    "id": 1,
                    "start": 5.0,
                    "end": 8.0,
                    "text": " Another line one\nAnother line two",
                },
            ]
            mock_client.audio.transcriptions.create.return_value = response

            transcribed = transcribe_audio(audio_path)

        # Multiline text should be preserved with newlines
        assert transcribed.entries[0].text == "Line one\nLine two"
        assert transcribed.entries[1].text == "Another line one\nAnother line two"

        # Translator should handle multiline entries
        with patch("bilingualsub.core.translator.Agent") as mock_agent:
            mock_translator = Mock()
            mock_agent.return_value = mock_translator

            batch_resp = Mock()
            batch_resp.content = "1. 第一行第二行\n2. 另一行一另一行二"
            mock_translator.run.return_value = batch_resp

            translated = translate_subtitle(transcribed)

        assert len(translated.entries) == 2
        assert translated.entries[0].text == "第一行第二行"
        assert translated.entries[1].text == "另一行一另一行二"
        # Timing preserved
        assert translated.entries[0].start == timedelta(seconds=1)
        assert translated.entries[0].end == timedelta(seconds=4)

    def test_single_entry_transcription_translates_successfully(
        self,
        tmp_path,
        set_fake_api_key,
    ):
        """Minimal pipeline with a single segment entry works end-to-end."""
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio content")

        with patch("bilingualsub.core.transcriber.Groq") as mock_groq:
            mock_client = MagicMock()
            mock_groq.return_value = mock_client
            response = Mock()
            response.segments = [
                {"id": 0, "start": 0.5, "end": 3.2, "text": " Welcome to the show."},
            ]
            mock_client.audio.transcriptions.create.return_value = response

            transcribed = transcribe_audio(audio_path)

        assert len(transcribed.entries) == 1
        assert transcribed.entries[0].text == "Welcome to the show."

        with patch("bilingualsub.core.translator.Agent") as mock_agent:
            mock_translator = Mock()
            mock_agent.return_value = mock_translator

            batch_resp = Mock()
            batch_resp.content = "1. 歡迎收看本節目。"
            mock_translator.run.return_value = batch_resp

            translated = translate_subtitle(transcribed)

        assert len(translated.entries) == 1
        assert translated.entries[0].index == 1
        assert translated.entries[0].start == timedelta(milliseconds=500)
        assert translated.entries[0].end == timedelta(seconds=3, milliseconds=200)
        assert translated.entries[0].text == "歡迎收看本節目。"
