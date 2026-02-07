"""Unit tests for FFmpeg utilities."""

from unittest.mock import MagicMock, patch

import pytest

from bilingualsub.utils.ffmpeg import FFmpegError, burn_subtitles, extract_audio


class TestBurnSubtitles:
    """Test cases for burn_subtitles function."""

    @pytest.fixture
    def mock_ffmpeg(self):
        """Mock ffmpeg module."""
        with patch("bilingualsub.utils.ffmpeg.ffmpeg") as mock:
            # Set up mock chain for ffmpeg.input().output().overwrite_output().run()
            mock_stream = MagicMock()
            mock.input.return_value = mock_stream
            mock_stream.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream
            mock_stream.run.return_value = None
            yield mock

    @pytest.mark.parametrize(
        ("subtitle_format", "expected_filter"),
        [
            (".srt", "subtitles="),
            (".ass", "ass="),
        ],
    )
    def test_when_given_valid_paths_then_burns_subtitles_with_correct_filter(
        self, tmp_path, mock_ffmpeg, subtitle_format, expected_filter
    ):
        """Given valid paths, when burning, then uses correct filter."""
        # Create test files
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video content")

        subtitle_path = tmp_path / f"subtitle{subtitle_format}"
        subtitle_path.write_bytes(b"fake subtitle content")

        output_path = tmp_path / "output.mp4"

        # Burn subtitles
        result = burn_subtitles(video_path, subtitle_path, output_path)

        # Verify ffmpeg was called correctly
        mock_ffmpeg.input.assert_called_once_with(str(video_path))

        # Verify output was called with correct filter
        call_kwargs = mock_ffmpeg.input.return_value.output.call_args[1]
        assert expected_filter in call_kwargs["vf"]
        assert str(subtitle_path) in call_kwargs["vf"]
        assert call_kwargs["acodec"] == "copy"

        # Verify overwrite_output was called
        overwrite_mock = (
            mock_ffmpeg.input.return_value.output.return_value.overwrite_output
        )
        overwrite_mock.assert_called_once()

        # Verify run was called with capture flags
        run_call_kwargs = overwrite_mock.return_value.run.call_args[1]
        assert run_call_kwargs["capture_stdout"] is True
        assert run_call_kwargs["capture_stderr"] is True

        # Verify result
        assert result == output_path

    def test_when_given_uppercase_srt_extension_then_burns_subtitles_successfully(
        self, tmp_path, mock_ffmpeg
    ):
        """Given uppercase .SRT extension, when burning, then works."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "subtitle.SRT"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "output.mp4"

        result = burn_subtitles(video_path, subtitle_path, output_path)

        # Verify subtitles filter was used (SRT format)
        call_kwargs = mock_ffmpeg.input.return_value.output.call_args[1]
        assert "subtitles=" in call_kwargs["vf"]
        assert result == output_path

    def test_when_given_uppercase_ass_extension_then_burns_subtitles_successfully(
        self, tmp_path, mock_ffmpeg
    ):
        """Given uppercase .ASS extension, when burning, then works."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "subtitle.ASS"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "output.mp4"

        result = burn_subtitles(video_path, subtitle_path, output_path)

        # Verify ass filter was used
        call_kwargs = mock_ffmpeg.input.return_value.output.call_args[1]
        assert "ass=" in call_kwargs["vf"]
        assert result == output_path

    def test_when_video_does_not_exist_then_raises_value_error(self, tmp_path):
        """Given non-existent video, when burning, then raises error."""
        video_path = tmp_path / "nonexistent.mp4"
        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")
        output_path = tmp_path / "output.mp4"

        with pytest.raises(ValueError, match="Video file does not exist"):
            burn_subtitles(video_path, subtitle_path, output_path)

    def test_when_video_path_is_directory_then_raises_value_error(
        self, tmp_path, mock_ffmpeg
    ):
        """Given video is a directory, when burning, then raises error."""
        video_dir = tmp_path / "video_dir"
        video_dir.mkdir()

        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "output.mp4"

        with pytest.raises(ValueError, match="Video path is not a file"):
            burn_subtitles(video_dir, subtitle_path, output_path)

    def test_when_subtitle_does_not_exist_then_raises_value_error(self, tmp_path):
        """Given non-existent subtitle, when burning, then raises error."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "nonexistent.srt"
        output_path = tmp_path / "output.mp4"

        with pytest.raises(ValueError, match="Subtitle file does not exist"):
            burn_subtitles(video_path, subtitle_path, output_path)

    def test_when_subtitle_path_is_directory_then_raises_value_error(self, tmp_path):
        """Given subtitle is a directory, when burning, then raises error."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_dir = tmp_path / "subtitle_dir"
        subtitle_dir.mkdir()

        output_path = tmp_path / "output.mp4"

        with pytest.raises(ValueError, match="Subtitle path is not a file"):
            burn_subtitles(video_path, subtitle_dir, output_path)

    def test_when_given_unsupported_subtitle_format_then_raises_value_error(
        self, tmp_path
    ):
        """Given unsupported format, when burning, then raises error."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "subtitle.txt"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "output.mp4"

        with pytest.raises(
            ValueError,
            match=r"Unsupported subtitle format.*Supported formats: \.srt, \.ass",
        ):
            burn_subtitles(video_path, subtitle_path, output_path)

    def test_when_ffmpeg_fails_then_raises_ffmpeg_error(self, tmp_path, mock_ffmpeg):
        """Given ffmpeg fails, when burning, then raises FFmpegError."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "output.mp4"

        # Mock ffmpeg error with stderr
        error = Exception("ffmpeg error")
        error.stderr = b"Codec not found"  # type: ignore[attr-defined]
        mock_output = mock_ffmpeg.input.return_value.output.return_value
        mock_chain = mock_output.overwrite_output.return_value
        mock_chain.run.side_effect = error

        with pytest.raises(
            FFmpegError, match=r"Failed to burn subtitles.*Codec not found"
        ):
            burn_subtitles(video_path, subtitle_path, output_path)

    def test_when_ffmpeg_fails_with_no_stderr_then_raises_ffmpeg_error(
        self, tmp_path, mock_ffmpeg
    ):
        """Given ffmpeg fails without stderr, when burning, then raises error."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "output.mp4"

        # Mock ffmpeg error without stderr
        error = Exception("Generic ffmpeg error")
        mock_output = mock_ffmpeg.input.return_value.output.return_value
        mock_chain = mock_output.overwrite_output.return_value
        mock_chain.run.side_effect = error

        with pytest.raises(
            FFmpegError, match=r"Failed to burn subtitles.*Generic ffmpeg error"
        ):
            burn_subtitles(video_path, subtitle_path, output_path)

    @pytest.mark.parametrize(
        "subtitle_format",
        [".vtt", ".sub", ".sbv", ".json"],
    )
    def test_when_given_other_unsupported_formats_then_raises_value_error(
        self, tmp_path, subtitle_format
    ):
        """Given unsupported formats, when burning, then raises error."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / f"subtitle{subtitle_format}"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "output.mp4"

        with pytest.raises(ValueError, match="Unsupported subtitle format"):
            burn_subtitles(video_path, subtitle_path, output_path)

    @pytest.mark.unit
    def test_when_given_valid_ass_file_then_preserves_ass_styling(
        self, tmp_path, mock_ffmpeg
    ):
        """Given ASS file, when burning, then preserves styling."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "subtitle.ass"
        subtitle_path.write_bytes(b"fake ass content with styling")

        output_path = tmp_path / "output.mp4"

        burn_subtitles(video_path, subtitle_path, output_path)

        # Verify ass filter was used (preserves styling)
        call_kwargs = mock_ffmpeg.input.return_value.output.call_args[1]
        assert "ass=" in call_kwargs["vf"]
        # Verify subtitles filter was NOT used
        assert call_kwargs["vf"].startswith("ass=")

    def test_when_given_paths_with_spaces_then_handles_correctly(
        self, tmp_path, mock_ffmpeg
    ):
        """Given paths with spaces, when burning, then works correctly."""
        video_path = tmp_path / "my video file.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "my subtitle file.srt"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "my output file.mp4"

        result = burn_subtitles(video_path, subtitle_path, output_path)

        # Verify paths were passed correctly
        mock_ffmpeg.input.assert_called_once_with(str(video_path))
        call_kwargs = mock_ffmpeg.input.return_value.output.call_args[1]
        assert str(subtitle_path) in call_kwargs["vf"]
        assert result == output_path

    @pytest.mark.unit
    def test_when_given_paths_with_special_chars_then_handles_correctly(
        self, tmp_path, mock_ffmpeg
    ):
        """Given paths with special characters, when burning, then works correctly."""
        # Note: Some characters like $ ; & | are handled by Path objects
        # These tests verify ffmpeg receives the correct path strings
        video_path = tmp_path / "video[2024]_test.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "sub(1)-日本語.srt"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "output_result.mp4"

        result = burn_subtitles(video_path, subtitle_path, output_path)

        # Verify paths were passed correctly
        mock_ffmpeg.input.assert_called_once_with(str(video_path))
        call_kwargs = mock_ffmpeg.input.return_value.output.call_args[1]
        assert str(subtitle_path) in call_kwargs["vf"]
        assert result == output_path


class TestExtractAudio:
    """Test cases for extract_audio function."""

    @pytest.fixture
    def mock_ffmpeg(self):
        """Mock ffmpeg module."""
        with patch("bilingualsub.utils.ffmpeg.ffmpeg") as mock:
            mock_stream = MagicMock()
            mock.input.return_value = mock_stream
            mock_stream.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream
            mock_stream.run.return_value = None
            yield mock

    @pytest.mark.unit
    def test_extract_audio_success(self, tmp_path, mock_ffmpeg):
        """Given valid video, when extracting audio, then calls ffmpeg correctly."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video content")
        output_path = tmp_path / "audio.mp3"

        result = extract_audio(video_path, output_path)

        mock_ffmpeg.input.assert_called_once_with(str(video_path))
        call_args = mock_ffmpeg.input.return_value.output.call_args
        assert call_args[0] == (str(output_path),)
        assert call_args[1]["acodec"] == "libmp3lame"
        assert call_args[1]["audio_bitrate"] == "64k"
        assert "vn" in call_args[1]
        assert result == output_path

    @pytest.mark.unit
    def test_extract_audio_custom_bitrate(self, tmp_path, mock_ffmpeg):
        """Given custom bitrate, when extracting audio, then uses it."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video content")
        output_path = tmp_path / "audio.mp3"

        extract_audio(video_path, output_path, bitrate="128k")

        call_args = mock_ffmpeg.input.return_value.output.call_args
        assert call_args[1]["audio_bitrate"] == "128k"

    @pytest.mark.unit
    def test_extract_audio_video_not_found(self, tmp_path):
        """Given non-existent video, when extracting audio, then raises FFmpegError."""
        video_path = tmp_path / "nonexistent.mp4"
        output_path = tmp_path / "audio.mp3"

        with pytest.raises(FFmpegError, match="Video file does not exist"):
            extract_audio(video_path, output_path)

    @pytest.mark.unit
    def test_extract_audio_video_is_directory(self, tmp_path):
        """Given directory as video, when extracting audio, then raises FFmpegError."""
        video_dir = tmp_path / "video_dir"
        video_dir.mkdir()
        output_path = tmp_path / "audio.mp3"

        with pytest.raises(FFmpegError, match="Video path is not a file"):
            extract_audio(video_dir, output_path)

    @pytest.mark.unit
    def test_extract_audio_ffmpeg_error_with_stderr(self, tmp_path, mock_ffmpeg):
        """Given ffmpeg fails with stderr, when extracting, then raises FFmpegError."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video content")
        output_path = tmp_path / "audio.mp3"

        error = Exception("ffmpeg error")
        error.stderr = b"Codec not found"
        mock_output = mock_ffmpeg.input.return_value.output.return_value
        mock_chain = mock_output.overwrite_output.return_value
        mock_chain.run.side_effect = error

        with pytest.raises(
            FFmpegError, match=r"Failed to extract audio.*Codec not found"
        ):
            extract_audio(video_path, output_path)

    @pytest.mark.unit
    def test_extract_audio_ffmpeg_error_without_stderr(self, tmp_path, mock_ffmpeg):
        """Given ffmpeg fails without stderr, when extracting, then raises FFmpegError."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video content")
        output_path = tmp_path / "audio.mp3"

        error = Exception("Generic error")
        mock_output = mock_ffmpeg.input.return_value.output.return_value
        mock_chain = mock_output.overwrite_output.return_value
        mock_chain.run.side_effect = error

        with pytest.raises(
            FFmpegError, match=r"Failed to extract audio.*Generic error"
        ):
            extract_audio(video_path, output_path)
