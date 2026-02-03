"""Unit tests for subtitle translation."""

import os
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.core.translator import TranslationError, translate_subtitle


class TestTranslateSubtitle:
    """Test cases for translate_subtitle function."""

    @pytest.fixture(autouse=True)
    def set_api_key(self, monkeypatch):
        """Set GROQ_API_KEY for all tests by default."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

    @pytest.fixture
    def mock_agent(self):
        """Mock Agno Agent."""
        with patch("bilingualsub.core.translator.Agent") as mock:
            yield mock

    @pytest.fixture
    def sample_subtitle(self) -> Subtitle:
        """Create a sample subtitle with two entries."""
        entries = [
            SubtitleEntry(
                index=1,
                start=timedelta(seconds=0),
                end=timedelta(seconds=2),
                text="Hello, world!",
            ),
            SubtitleEntry(
                index=2,
                start=timedelta(seconds=2),
                end=timedelta(seconds=4),
                text="How are you?",
            ),
        ]
        return Subtitle(entries=entries)

    def test_translate_subtitle_successfully(self, mock_agent, sample_subtitle):
        """Should translate all entries in subtitle successfully."""
        # Arrange
        mock_translator = Mock()
        mock_agent.return_value = mock_translator

        # Mock responses for each entry
        mock_response_1 = Mock()
        mock_response_1.content = "你好，世界！"  # noqa: RUF001
        mock_response_2 = Mock()
        mock_response_2.content = "你好嗎？"  # noqa: RUF001

        mock_translator.run.side_effect = [mock_response_1, mock_response_2]

        # Act
        result = translate_subtitle(sample_subtitle)

        # Assert
        assert len(result.entries) == 2
        assert result.entries[0].text == "你好，世界！"  # noqa: RUF001
        assert result.entries[1].text == "你好嗎？"  # noqa: RUF001

        # Verify timing is preserved
        assert result.entries[0].start == timedelta(seconds=0)
        assert result.entries[0].end == timedelta(seconds=2)
        assert result.entries[1].start == timedelta(seconds=2)
        assert result.entries[1].end == timedelta(seconds=4)

        # Verify indices are preserved
        assert result.entries[0].index == 1
        assert result.entries[1].index == 2

    def test_translate_subtitle_with_custom_languages(
        self, mock_agent, sample_subtitle
    ):
        """Should use custom source and target languages."""
        # Arrange
        mock_translator = Mock()
        mock_agent.return_value = mock_translator

        mock_response = Mock()
        mock_response.content = "Bonjour, monde!"
        mock_translator.run.return_value = mock_response

        # Act
        translate_subtitle(sample_subtitle, source_lang="en", target_lang="fr")

        # Assert
        # Verify Agent was created with correct description
        agent_call = mock_agent.call_args
        assert "en" in agent_call.kwargs["description"]
        assert "fr" in agent_call.kwargs["description"]

        # Verify translator.run was called with correct language params
        translator_calls = mock_translator.run.call_args_list
        assert "en" in translator_calls[0][0][0]
        assert "fr" in translator_calls[0][0][0]

    def test_translate_subtitle_preserves_whitespace(self, mock_agent, sample_subtitle):
        """Should strip whitespace from translated text."""
        # Arrange
        mock_translator = Mock()
        mock_agent.return_value = mock_translator

        # Mock response with extra whitespace
        mock_response = Mock()
        mock_response.content = "  你好，世界！  \n"  # noqa: RUF001
        mock_translator.run.return_value = mock_response

        # Act
        result = translate_subtitle(sample_subtitle)

        # Assert
        assert result.entries[0].text == "你好，世界！"  # noqa: RUF001
        assert result.entries[1].text == "你好，世界！"  # noqa: RUF001

    def test_translate_subtitle_raises_error_on_empty_translation(
        self, mock_agent, sample_subtitle
    ):
        """Should raise TranslationError when translation is empty."""
        # Arrange
        mock_translator = Mock()
        mock_agent.return_value = mock_translator

        # Mock empty response
        mock_response = Mock()
        mock_response.content = "   "  # Only whitespace
        mock_translator.run.return_value = mock_response

        # Act & Assert
        with pytest.raises(TranslationError) as exc_info:
            translate_subtitle(sample_subtitle)

        assert "Empty or whitespace-only translation" in str(exc_info.value)
        assert "entry 1" in str(exc_info.value)

    def test_translate_subtitle_raises_error_on_api_failure(
        self, mock_agent, sample_subtitle
    ):
        """Should raise TranslationError when API call fails."""
        # Arrange
        mock_translator = Mock()
        mock_agent.return_value = mock_translator
        mock_translator.run.side_effect = Exception("API connection failed")

        # Act & Assert
        with pytest.raises(TranslationError) as exc_info:
            translate_subtitle(sample_subtitle)

        assert "Failed to translate entry 1" in str(exc_info.value)
        assert "Hello, world!" in str(exc_info.value)

    def test_translate_subtitle_uses_qwen_model(self, sample_subtitle):
        """Should use qwen-qwq-32b model for translation."""
        # Arrange & Act
        with (
            patch("bilingualsub.core.translator.Agent") as mock_agent,
            patch("bilingualsub.core.translator.Groq") as mock_groq,
        ):
            mock_translator = Mock()
            mock_agent.return_value = mock_translator

            mock_response = Mock()
            mock_response.content = "你好"
            mock_translator.run.return_value = mock_response

            translate_subtitle(sample_subtitle)

            # Assert - Verify Groq model was used with correct ID
            mock_groq.assert_called_once_with(id="qwen-qwq-32b")

    @pytest.mark.parametrize(
        "source_lang,target_lang,expected_desc_parts",
        [
            ("en", "zh-TW", ["en", "zh-TW"]),
            ("ja", "en", ["ja", "en"]),
            ("ko", "zh-CN", ["ko", "zh-CN"]),
        ],
    )
    def test_translate_subtitle_with_different_language_pairs(
        self, mock_agent, sample_subtitle, source_lang, target_lang, expected_desc_parts
    ):
        """Should handle different language pairs correctly."""
        # Arrange
        mock_translator = Mock()
        mock_agent.return_value = mock_translator

        mock_response = Mock()
        mock_response.content = "Translated text"
        mock_translator.run.return_value = mock_response

        # Act
        translate_subtitle(
            sample_subtitle, source_lang=source_lang, target_lang=target_lang
        )

        # Assert
        agent_call = mock_agent.call_args
        description = agent_call.kwargs["description"]
        for part in expected_desc_parts:
            assert part in description

    def test_translate_subtitle_returns_new_subtitle_object(
        self, mock_agent, sample_subtitle
    ):
        """Should return a new Subtitle object, not modify original."""
        # Arrange
        mock_translator = Mock()
        mock_agent.return_value = mock_translator

        mock_response = Mock()
        mock_response.content = "你好"
        mock_translator.run.return_value = mock_response

        original_text = sample_subtitle.entries[0].text

        # Act
        result = translate_subtitle(sample_subtitle)

        # Assert
        assert result is not sample_subtitle
        assert sample_subtitle.entries[0].text == original_text  # Original unchanged
        assert result.entries[0].text == "你好"  # New subtitle has translation

    def test_missing_api_key_raises_error(self, sample_subtitle, monkeypatch):
        """Should raise ValueError when GROQ_API_KEY is not set."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        with pytest.raises(
            ValueError, match="GROQ_API_KEY environment variable is not set"
        ):
            translate_subtitle(sample_subtitle)

    def test_empty_api_key_raises_error(self, sample_subtitle, monkeypatch):
        """Should raise ValueError when GROQ_API_KEY is empty."""
        monkeypatch.setenv("GROQ_API_KEY", "")

        with pytest.raises(
            ValueError, match="GROQ_API_KEY environment variable is not set"
        ):
            translate_subtitle(sample_subtitle)
