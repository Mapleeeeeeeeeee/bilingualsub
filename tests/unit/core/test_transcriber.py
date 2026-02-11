"""Unit tests for audio transcription."""

from datetime import timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from bilingualsub.core.subtitle import Subtitle
from bilingualsub.core.transcriber import TranscriptionError, transcribe_audio
from bilingualsub.utils.config import get_settings


class TestTranscribeAudio:
    """Test cases for transcribe_audio function."""

    @pytest.fixture(autouse=True)
    def clear_settings_cache(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    @pytest.fixture
    def no_env_file(self, tmp_path, monkeypatch):
        """Run test in a directory without .env file."""
        monkeypatch.chdir(tmp_path)
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    @pytest.fixture
    def mock_groq(self):
        """Mock Groq client."""
        with patch("bilingualsub.core.transcriber.Groq") as mock:
            yield mock

    @pytest.fixture
    def mock_openai(self):
        """Mock OpenAI client."""
        with patch("bilingualsub.core.transcriber.OpenAI") as mock:
            yield mock

    @pytest.fixture
    def valid_verbose_json_response(self):
        """Return a mock verbose_json transcription response."""
        response = Mock()
        response.segments = [
            {"id": 0, "start": 0.0, "end": 2.0, "text": " Hello world"},
            {"id": 1, "start": 2.0, "end": 4.0, "text": " This is a test"},
        ]
        response.text = "Hello world This is a test"
        return response

    def test_transcribe_valid_audio_file(
        self, tmp_path, mock_groq, valid_verbose_json_response, monkeypatch
    ):
        """Test transcribing a valid audio file."""
        # Set API key
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        # Create test audio file (small enough)
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio content")

        # Mock Groq client
        mock_client = MagicMock()
        mock_groq.return_value = mock_client

        # Mock transcription response
        mock_client.audio.transcriptions.create.return_value = (
            valid_verbose_json_response
        )

        # Transcribe audio
        result = transcribe_audio(audio_path)

        # Verify Groq client was initialized
        mock_groq.assert_called_once_with(api_key="test-api-key")

        # Verify transcription API was called
        mock_client.audio.transcriptions.create.assert_called_once()
        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["model"] == "whisper-large-v3-turbo"
        assert call_kwargs["response_format"] == "verbose_json"
        assert call_kwargs["language"] == "en"
        assert call_kwargs["file"][0] == "audio.mp3"
        # File handle is passed directly (not bytes) for memory efficiency
        assert hasattr(call_kwargs["file"][1], "read")

        # Verify result is a real Subtitle object
        assert isinstance(result, Subtitle)
        assert len(result.entries) == 2
        assert result.entries[0].text == "Hello world"
        assert result.entries[0].start == timedelta(0)
        assert result.entries[0].end == timedelta(seconds=2)
        assert result.entries[1].text == "This is a test"
        assert result.entries[1].start == timedelta(seconds=2)
        assert result.entries[1].end == timedelta(seconds=4)

    def test_transcribe_with_chinese_language(self, tmp_path, mock_groq, monkeypatch):
        """Test transcribing with Chinese language parameter."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        mock_client = MagicMock()
        mock_groq.return_value = mock_client

        # Mock verbose_json response with Chinese text
        response = Mock()
        response.segments = [{"id": 0, "start": 0.0, "end": 1.0, "text": " 你好"}]
        mock_client.audio.transcriptions.create.return_value = response

        result = transcribe_audio(audio_path, language="zh")

        # Verify language parameter was passed
        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["language"] == "zh"

        # Verify result
        assert isinstance(result, Subtitle)
        assert len(result.entries) == 1
        assert result.entries[0].text == "你好"

    def test_audio_file_not_exists_raises_error(self, tmp_path, monkeypatch):
        """Test that non-existent audio file raises error."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_path = tmp_path / "nonexistent.mp3"

        with pytest.raises(ValueError, match="Audio file does not exist"):
            transcribe_audio(audio_path)

    def test_audio_path_is_directory_raises_error(self, tmp_path, monkeypatch):
        """Test that directory path raises error."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_dir = tmp_path / "audio_dir"
        audio_dir.mkdir()

        with pytest.raises(ValueError, match="Audio path is not a file"):
            transcribe_audio(audio_dir)

    def test_large_file_triggers_chunking(self, tmp_path, mock_groq, monkeypatch):
        """Test that file larger than 25MB triggers chunking instead of error."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_path = tmp_path / "large_audio.mp3"
        large_content = b"x" * (26 * 1024 * 1024)
        audio_path.write_bytes(large_content)

        mock_client = MagicMock()
        mock_groq.return_value = mock_client

        # Create two mock responses for two chunks
        response1 = Mock()
        response1.segments = [
            {"id": 0, "start": 0.0, "end": 2.0, "text": " Hello"},
        ]
        response2 = Mock()
        response2.segments = [
            {"id": 0, "start": 0.0, "end": 3.0, "text": " World"},
        ]
        mock_client.audio.transcriptions.create.side_effect = [response1, response2]

        chunk0 = tmp_path / "large_audio_chunk0.mp3"
        chunk0.write_bytes(b"chunk0")
        chunk1 = tmp_path / "large_audio_chunk1.mp3"
        chunk1.write_bytes(b"chunk1")

        with patch(
            "bilingualsub.core.transcriber.split_audio",
            return_value=[(chunk0, 0.0), (chunk1, 1500.0)],
        ):
            result = transcribe_audio(audio_path)

        assert isinstance(result, Subtitle)
        assert len(result.entries) == 2
        assert result.entries[0].text == "Hello"
        assert result.entries[0].start == timedelta(seconds=0.0)
        assert result.entries[1].text == "World"
        assert result.entries[1].start == timedelta(seconds=1500.0)
        assert result.entries[1].end == timedelta(seconds=1503.0)

    def test_missing_api_key_raises_error(self, tmp_path, monkeypatch, no_env_file):
        """Test that missing GROQ_API_KEY raises error."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        with pytest.raises(
            ValueError, match="GROQ_API_KEY environment variable is not set"
        ):
            transcribe_audio(audio_path)

    def test_groq_api_error_raises_transcription_error(
        self, tmp_path, mock_groq, monkeypatch
    ):
        """Test that Groq API error raises TranscriptionError."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        mock_client = MagicMock()
        mock_groq.return_value = mock_client
        mock_client.audio.transcriptions.create.side_effect = Exception(
            "API rate limit exceeded"
        )

        with pytest.raises(TranscriptionError, match="Failed to transcribe audio"):
            transcribe_audio(audio_path)

    def test_malformed_segments_raises_transcription_error(
        self, tmp_path, mock_groq, monkeypatch
    ):
        """Test that malformed segments data raises TranscriptionError."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        mock_client = MagicMock()
        mock_groq.return_value = mock_client

        # Mock response with malformed segments (missing "text" key)
        response = Mock()
        response.segments = [{"id": 0, "start": 0.0, "end": 1.0}]  # missing "text"
        mock_client.audio.transcriptions.create.return_value = response

        with pytest.raises(
            TranscriptionError, match="Failed to parse transcription result"
        ):
            transcribe_audio(audio_path)

    def test_empty_segments_raises_transcription_error(
        self, tmp_path, mock_groq, monkeypatch
    ):
        """Test that empty segments list raises TranscriptionError."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        mock_client = MagicMock()
        mock_groq.return_value = mock_client

        # Mock response with empty segments
        response = Mock()
        response.segments = []
        mock_client.audio.transcriptions.create.return_value = response

        with pytest.raises(
            TranscriptionError, match="Transcription returned no segments"
        ):
            transcribe_audio(audio_path)

    def test_file_exactly_25mb_is_accepted(self, tmp_path, mock_groq, monkeypatch):
        """Test that file exactly 25MB is accepted."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_path = tmp_path / "audio.mp3"
        # Create exactly 25MB file
        content = b"x" * (25 * 1024 * 1024)
        audio_path.write_bytes(content)

        mock_client = MagicMock()
        mock_groq.return_value = mock_client

        # Mock verbose_json response
        response = Mock()
        response.segments = [{"id": 0, "start": 0.0, "end": 1.0, "text": " Test"}]
        mock_client.audio.transcriptions.create.return_value = response

        # Should not raise
        result = transcribe_audio(audio_path)
        assert isinstance(result, Subtitle)
        assert len(result.entries) == 1
        assert result.entries[0].text == "Test"

    def test_various_audio_formats(self, tmp_path, mock_groq, monkeypatch):
        """Test transcription with various audio file formats."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        formats = [".mp3", ".wav", ".m4a", ".flac", ".ogg"]

        mock_client = MagicMock()
        mock_groq.return_value = mock_client

        # Mock verbose_json response
        response = Mock()
        response.segments = [{"id": 0, "start": 0.0, "end": 1.0, "text": " Test"}]
        mock_client.audio.transcriptions.create.return_value = response

        for fmt in formats:
            audio_path = tmp_path / f"audio{fmt}"
            audio_path.write_bytes(b"fake audio")

            result = transcribe_audio(audio_path)
            assert isinstance(result, Subtitle)
            assert len(result.entries) == 1
            assert result.entries[0].text == "Test"

            # Verify correct filename was sent
            call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
            assert call_kwargs["file"][0] == f"audio{fmt}"

    def test_empty_api_key_raises_error(self, tmp_path, monkeypatch, no_env_file):
        """Test that empty GROQ_API_KEY raises error."""
        monkeypatch.setenv("GROQ_API_KEY", "")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        with pytest.raises(
            ValueError, match="GROQ_API_KEY environment variable is not set"
        ):
            transcribe_audio(audio_path)

    @pytest.mark.unit
    def test_default_language_is_english(self, tmp_path, mock_groq, monkeypatch):
        """Test that default language is English."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        mock_client = MagicMock()
        mock_groq.return_value = mock_client

        # Mock verbose_json response
        response = Mock()
        response.segments = [{"id": 0, "start": 0.0, "end": 1.0, "text": " Test"}]
        mock_client.audio.transcriptions.create.return_value = response

        transcribe_audio(audio_path)

        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["language"] == "en"

    def test_transcribe_with_openai_provider(
        self, tmp_path, mock_openai, valid_verbose_json_response, monkeypatch
    ):
        """Test transcribing with OpenAI provider."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
        monkeypatch.setenv("TRANSCRIBER_PROVIDER", "openai")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio content")

        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = (
            valid_verbose_json_response
        )

        result = transcribe_audio(audio_path)

        mock_openai.assert_called_once_with(
            api_key="test-openai-key"  # pragma: allowlist secret
        )
        assert isinstance(result, Subtitle)
        assert len(result.entries) == 2

    def test_transcribe_with_custom_model(
        self, tmp_path, mock_groq, valid_verbose_json_response, monkeypatch
    ):
        """Test transcribing with custom model name."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
        monkeypatch.setenv("TRANSCRIBER_MODEL", "whisper-large-v3")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio content")

        mock_client = MagicMock()
        mock_groq.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = (
            valid_verbose_json_response
        )

        transcribe_audio(audio_path)

        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["model"] == "whisper-large-v3"

    def test_unknown_provider_raises_error(self, tmp_path, monkeypatch):
        """Test that unknown provider raises ValueError."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
        monkeypatch.setenv("TRANSCRIBER_PROVIDER", "unsupported")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio content")

        with pytest.raises(ValueError, match="Unknown transcriber provider"):
            transcribe_audio(audio_path)

    def test_small_file_does_not_trigger_chunking(
        self, tmp_path, mock_groq, valid_verbose_json_response, monkeypatch
    ):
        """Test that small file uses direct transcription without chunking."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio content")

        mock_client = MagicMock()
        mock_groq.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = (
            valid_verbose_json_response
        )

        with patch("bilingualsub.core.transcriber.split_audio") as mock_split:
            result = transcribe_audio(audio_path)

        mock_split.assert_not_called()
        assert isinstance(result, Subtitle)
        assert len(result.entries) == 2
