"""Unit tests for subtitle translation."""

from datetime import timedelta
from unittest.mock import Mock, patch

import pytest

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.core.translator import (
    TranslationError,
    _parse_batch_response,
    translate_subtitle,
)
from bilingualsub.utils.config import get_settings


class TestTranslateSubtitle:
    """Test cases for translate_subtitle function."""

    @pytest.fixture(autouse=True)
    def clear_settings_cache(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    @pytest.fixture(autouse=True)
    def set_api_key(self, monkeypatch):
        """Set GROQ_API_KEY for all tests by default."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

    @pytest.fixture
    def no_env_file(self, tmp_path, monkeypatch):
        """Run test in a directory without .env file."""
        monkeypatch.chdir(tmp_path)
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

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
        """Should translate all entries in subtitle successfully via batch."""
        mock_translator = Mock()
        mock_agent.return_value = mock_translator

        # Batch response for 2 entries
        mock_response = Mock()
        mock_response.content = "1. 你好，世界！\n2. 你好嗎？"
        mock_translator.run.return_value = mock_response

        result = translate_subtitle(sample_subtitle)

        assert len(result.entries) == 2
        assert result.entries[0].text == "你好，世界！"
        assert result.entries[1].text == "你好嗎？"

        # Verify timing is preserved
        assert result.entries[0].start == timedelta(seconds=0)
        assert result.entries[0].end == timedelta(seconds=2)
        assert result.entries[1].start == timedelta(seconds=2)
        assert result.entries[1].end == timedelta(seconds=4)

        # Verify indices are preserved
        assert result.entries[0].index == 1
        assert result.entries[1].index == 2

        # Should be called once for the batch (not once per entry)
        assert mock_translator.run.call_count == 1

    def test_translate_subtitle_with_custom_languages(
        self, mock_agent, sample_subtitle
    ):
        """Should use custom source and target languages."""
        mock_translator = Mock()
        mock_agent.return_value = mock_translator

        mock_response = Mock()
        mock_response.content = "1. Bonjour, monde!\n2. Comment allez-vous?"
        mock_translator.run.return_value = mock_response

        translate_subtitle(sample_subtitle, source_lang="en", target_lang="fr")

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
        mock_translator = Mock()
        mock_agent.return_value = mock_translator

        mock_response = Mock()
        mock_response.content = "1.   你好，世界！  \n2.   你好，世界！  "
        mock_translator.run.return_value = mock_response

        result = translate_subtitle(sample_subtitle)

        assert result.entries[0].text == "你好，世界！"
        assert result.entries[1].text == "你好，世界！"

    def test_translate_subtitle_raises_error_on_empty_translation(
        self, mock_agent, sample_subtitle
    ):
        """Should raise TranslationError when translation is empty."""
        mock_translator = Mock()
        mock_agent.return_value = mock_translator

        # Batch returns empty → triggers fallback → fallback also empty
        mock_response_empty = Mock()
        mock_response_empty.content = "   "
        mock_translator.run.return_value = mock_response_empty

        with pytest.raises(TranslationError):
            translate_subtitle(sample_subtitle)

    def test_translate_subtitle_raises_error_on_api_failure(
        self, mock_agent, sample_subtitle
    ):
        """Should raise TranslationError when API call fails."""
        mock_translator = Mock()
        mock_agent.return_value = mock_translator
        mock_translator.run.side_effect = Exception("API connection failed")

        with pytest.raises(TranslationError):
            translate_subtitle(sample_subtitle)

    def test_translate_subtitle_uses_qwen_model(self, sample_subtitle):
        """Should use qwen/qwen3-32b model for translation."""
        with (
            patch("bilingualsub.core.translator.Agent") as mock_agent,
            patch("bilingualsub.core.translator.Groq") as mock_groq,
        ):
            mock_translator = Mock()
            mock_agent.return_value = mock_translator

            mock_response = Mock()
            mock_response.content = "1. 你好\n2. 你好嗎"
            mock_translator.run.return_value = mock_response

            translate_subtitle(sample_subtitle)

            mock_groq.assert_called_once_with(
                id="qwen/qwen3-32b",
                api_key="test-api-key",
                request_params={"reasoning_format": "hidden"},
            )

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
        mock_translator = Mock()
        mock_agent.return_value = mock_translator

        mock_response = Mock()
        mock_response.content = "1. Translated text\n2. Translated text"
        mock_translator.run.return_value = mock_response

        translate_subtitle(
            sample_subtitle, source_lang=source_lang, target_lang=target_lang
        )

        agent_call = mock_agent.call_args
        description = agent_call.kwargs["description"]
        for part in expected_desc_parts:
            assert part in description

    def test_translate_subtitle_returns_new_subtitle_object(
        self, mock_agent, sample_subtitle
    ):
        """Should return a new Subtitle object, not modify original."""
        mock_translator = Mock()
        mock_agent.return_value = mock_translator

        mock_response = Mock()
        mock_response.content = "1. 你好\n2. 你好嗎"
        mock_translator.run.return_value = mock_response

        original_text = sample_subtitle.entries[0].text

        result = translate_subtitle(sample_subtitle)

        assert result is not sample_subtitle
        assert sample_subtitle.entries[0].text == original_text
        assert result.entries[0].text == "你好"

    def test_missing_api_key_raises_error(
        self, sample_subtitle, monkeypatch, no_env_file
    ):
        """Should raise ValueError when GROQ_API_KEY is not set."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        with pytest.raises(
            ValueError, match="GROQ_API_KEY environment variable is not set"
        ):
            translate_subtitle(sample_subtitle)

    def test_empty_api_key_raises_error(
        self, sample_subtitle, monkeypatch, no_env_file
    ):
        """Should raise ValueError when GROQ_API_KEY is empty."""
        monkeypatch.setenv("GROQ_API_KEY", "")

        with pytest.raises(
            ValueError, match="GROQ_API_KEY environment variable is not set"
        ):
            translate_subtitle(sample_subtitle)


class TestParseBatchResponse:
    """Test cases for _parse_batch_response function."""

    def test_parse_batch_response_valid(self):
        """Should parse valid numbered response."""
        response = "1. 你好，世界！\n2. 你好嗎？\n3. 再見"
        result = _parse_batch_response(response, 3)
        assert result == ["你好，世界！", "你好嗎？", "再見"]

    def test_parse_batch_response_extra_whitespace(self):
        """Should handle extra whitespace in response."""
        response = "  1.  你好，世界！  \n  2.  你好嗎？  "
        result = _parse_batch_response(response, 2)
        assert result == ["你好，世界！", "你好嗎？"]

    def test_parse_batch_response_various_separators(self):
        """Should handle different separators (dot, paren, colon)."""
        response = "1) 翻譯一\n2) 翻譯二"
        result = _parse_batch_response(response, 2)
        assert result == ["翻譯一", "翻譯二"]

    def test_parse_batch_response_count_mismatch(self):
        """Should raise TranslationError on count mismatch."""
        response = "1. 你好"
        with pytest.raises(TranslationError, match="Expected 2 translations"):
            _parse_batch_response(response, 2)

    def test_parse_batch_response_missing_number(self):
        """Should raise TranslationError when a number is missing."""
        response = "1. 你好\n3. 再見"
        with pytest.raises(TranslationError):
            _parse_batch_response(response, 3)


class TestBatchTranslation:
    """Test batch translation behavior."""

    @pytest.fixture(autouse=True)
    def clear_settings_cache(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    @pytest.fixture(autouse=True)
    def set_api_key(self, monkeypatch):
        """Set GROQ_API_KEY for all tests by default."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

    def test_translate_batch_fallback_on_parse_failure(self):
        """Should fallback to one-by-one when batch parsing fails."""
        entries = [
            SubtitleEntry(
                index=1,
                start=timedelta(seconds=0),
                end=timedelta(seconds=2),
                text="Hello",
            ),
            SubtitleEntry(
                index=2,
                start=timedelta(seconds=2),
                end=timedelta(seconds=4),
                text="World",
            ),
        ]
        subtitle = Subtitle(entries=entries)

        with patch("bilingualsub.core.translator.Agent") as mock_agent:
            mock_translator = Mock()
            mock_agent.return_value = mock_translator

            # First call (batch) returns unparseable response
            # Then fallback calls return individual translations
            bad_batch_resp = Mock()
            bad_batch_resp.content = "Here are the translations: hello world"

            good_resp_1 = Mock()
            good_resp_1.content = "你好"
            good_resp_2 = Mock()
            good_resp_2.content = "世界"

            mock_translator.run.side_effect = [bad_batch_resp, good_resp_1, good_resp_2]

            result = translate_subtitle(subtitle)

        assert len(result.entries) == 2
        assert result.entries[0].text == "你好"
        assert result.entries[1].text == "世界"

    def test_translate_respects_batch_size(self):
        """25 entries should result in 3 batch API calls (10+10+5)."""
        entries = [
            SubtitleEntry(
                index=i + 1,
                start=timedelta(seconds=i * 2),
                end=timedelta(seconds=i * 2 + 2),
                text=f"Line {i + 1}",
            )
            for i in range(25)
        ]
        subtitle = Subtitle(entries=entries)

        with patch("bilingualsub.core.translator.Agent") as mock_agent:
            mock_translator = Mock()
            mock_agent.return_value = mock_translator

            def make_batch_response(*args, **kwargs):
                prompt_text = args[0] if args else ""
                # Count how many numbered lines in the prompt
                lines = [
                    line
                    for line in prompt_text.strip().splitlines()
                    if line.strip() and line.strip()[0].isdigit()
                ]
                count = len(lines)
                resp = Mock()
                resp.content = "\n".join(f"{i}. 翻譯 {i}" for i in range(1, count + 1))
                return resp

            mock_translator.run.side_effect = make_batch_response

            result = translate_subtitle(subtitle)

        assert len(result.entries) == 25
        # 3 batch calls: 10 + 10 + 5
        assert mock_translator.run.call_count == 3

    def test_on_progress_called_per_batch(self):
        """on_progress should be called after each batch."""
        entries = [
            SubtitleEntry(
                index=i + 1,
                start=timedelta(seconds=i * 2),
                end=timedelta(seconds=i * 2 + 2),
                text=f"Line {i + 1}",
            )
            for i in range(25)
        ]
        subtitle = Subtitle(entries=entries)

        with patch("bilingualsub.core.translator.Agent") as mock_agent:
            mock_translator = Mock()
            mock_agent.return_value = mock_translator

            def make_batch_response(*args, **kwargs):
                prompt_text = args[0] if args else ""
                lines = [
                    line
                    for line in prompt_text.strip().splitlines()
                    if line.strip() and line.strip()[0].isdigit()
                ]
                count = len(lines)
                resp = Mock()
                resp.content = "\n".join(f"{i}. 翻譯 {i}" for i in range(1, count + 1))
                return resp

            mock_translator.run.side_effect = make_batch_response

            progress_calls = []

            def on_progress(completed, total):
                progress_calls.append((completed, total))

            translate_subtitle(subtitle, on_progress=on_progress)

        # 3 batches: 10 + 10 + 5
        assert len(progress_calls) == 3
        assert progress_calls[0] == (10, 25)
        assert progress_calls[1] == (20, 25)
        assert progress_calls[2] == (25, 25)
