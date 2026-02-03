"""Unit tests for audio transcription."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from bilingualsub.core.transcriber import TranscriptionError, transcribe_audio


class TestTranscribeAudio:
    """Test cases for transcribe_audio function."""

    @pytest.fixture
    def mock_groq(self):
        """Mock Groq client."""
        with patch("bilingualsub.core.transcriber.Groq") as mock:
            yield mock

    @pytest.fixture
    def mock_parse_srt(self):
        """Mock parse_srt function."""
        with patch("bilingualsub.core.transcriber.parse_srt") as mock:
            yield mock

    @pytest.fixture
    def valid_srt_content(self) -> str:
        """Return valid SRT content."""
        return """1
00:00:00,000 --> 00:00:02,000
Hello world

2
00:00:02,000 --> 00:00:04,000
This is a test
"""

    def test_transcribe_valid_audio_file(
        self, tmp_path, mock_groq, mock_parse_srt, valid_srt_content, monkeypatch
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
        mock_client.audio.transcriptions.create.return_value = valid_srt_content

        # Mock parse_srt
        mock_subtitle = Mock()
        mock_parse_srt.return_value = mock_subtitle

        # Transcribe audio
        result = transcribe_audio(audio_path)

        # Verify Groq client was initialized
        mock_groq.assert_called_once_with(api_key="test-api-key")

        # Verify transcription API was called
        mock_client.audio.transcriptions.create.assert_called_once()
        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["model"] == "whisper-large-v3-turbo"
        assert call_kwargs["response_format"] == "srt"
        assert call_kwargs["language"] == "en"
        assert call_kwargs["file"][0] == "audio.mp3"
        # File handle is passed directly (not bytes) for memory efficiency
        assert hasattr(call_kwargs["file"][1], "read")

        # Verify parse_srt was called
        mock_parse_srt.assert_called_once_with(valid_srt_content)

        # Verify result
        assert result == mock_subtitle

    def test_transcribe_with_chinese_language(
        self, tmp_path, mock_groq, mock_parse_srt, monkeypatch
    ):
        """Test transcribing with Chinese language parameter."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        mock_client = MagicMock()
        mock_groq.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = (
            "1\n00:00:00,000 --> 00:00:01,000\n你好"
        )

        mock_subtitle = Mock()
        mock_parse_srt.return_value = mock_subtitle

        result = transcribe_audio(audio_path, language="zh")

        # Verify language parameter was passed
        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["language"] == "zh"
        assert result == mock_subtitle

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

    def test_file_too_large_raises_error(self, tmp_path, monkeypatch):
        """Test that file larger than 25MB raises error."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_path = tmp_path / "large_audio.mp3"
        # Create a file larger than 25MB
        large_content = b"x" * (26 * 1024 * 1024)
        audio_path.write_bytes(large_content)

        with pytest.raises(ValueError, match=r"File size .* exceeds Groq's 25MB limit"):
            transcribe_audio(audio_path)

    def test_missing_api_key_raises_error(self, tmp_path, monkeypatch):
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

    def test_parse_srt_error_raises_transcription_error(
        self, tmp_path, mock_groq, mock_parse_srt, monkeypatch
    ):
        """Test that parse_srt error raises TranscriptionError."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        mock_client = MagicMock()
        mock_groq.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = "invalid srt"

        mock_parse_srt.side_effect = Exception("Invalid SRT format")

        with pytest.raises(
            TranscriptionError, match="Failed to parse transcription result"
        ):
            transcribe_audio(audio_path)

    def test_file_exactly_25mb_is_accepted(
        self, tmp_path, mock_groq, mock_parse_srt, monkeypatch
    ):
        """Test that file exactly 25MB is accepted."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_path = tmp_path / "audio.mp3"
        # Create exactly 25MB file
        content = b"x" * (25 * 1024 * 1024)
        audio_path.write_bytes(content)

        mock_client = MagicMock()
        mock_groq.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = (
            "1\n00:00:00,000 --> 00:00:01,000\nTest"
        )

        mock_subtitle = Mock()
        mock_parse_srt.return_value = mock_subtitle

        # Should not raise
        result = transcribe_audio(audio_path)
        assert result == mock_subtitle

    def test_various_audio_formats(
        self, tmp_path, mock_groq, mock_parse_srt, monkeypatch
    ):
        """Test transcription with various audio file formats."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        formats = [".mp3", ".wav", ".m4a", ".flac", ".ogg"]

        mock_client = MagicMock()
        mock_groq.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = (
            "1\n00:00:00,000 --> 00:00:01,000\nTest"
        )

        mock_subtitle = Mock()
        mock_parse_srt.return_value = mock_subtitle

        for fmt in formats:
            audio_path = tmp_path / f"audio{fmt}"
            audio_path.write_bytes(b"fake audio")

            result = transcribe_audio(audio_path)
            assert result == mock_subtitle

            # Verify correct filename was sent
            call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
            assert call_kwargs["file"][0] == f"audio{fmt}"

    def test_empty_api_key_raises_error(self, tmp_path, monkeypatch):
        """Test that empty GROQ_API_KEY raises error."""
        monkeypatch.setenv("GROQ_API_KEY", "")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        with pytest.raises(
            ValueError, match="GROQ_API_KEY environment variable is not set"
        ):
            transcribe_audio(audio_path)

    @pytest.mark.unit
    def test_default_language_is_english(
        self, tmp_path, mock_groq, mock_parse_srt, monkeypatch
    ):
        """Test that default language is English."""
        monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        mock_client = MagicMock()
        mock_groq.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = (
            "1\n00:00:00,000 --> 00:00:01,000\nTest"
        )

        mock_subtitle = Mock()
        mock_parse_srt.return_value = mock_subtitle

        transcribe_audio(audio_path)

        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["language"] == "en"
