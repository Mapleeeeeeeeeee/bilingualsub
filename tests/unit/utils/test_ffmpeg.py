"""Unit tests for FFmpeg utilities."""

import json
from unittest.mock import MagicMock, patch

import pytest

from bilingualsub.utils.ffmpeg import (
    FFmpegError,
    burn_subtitles,
    extract_audio,
    get_audio_duration,
    split_audio,
    trim_video,
)


class TestBurnSubtitles:
    """Test cases for burn_subtitles function."""

    @pytest.fixture
    def mock_ffmpeg(self):
        """Mock subprocess.Popen and extract_video_metadata for burn_subtitles."""
        with (
            patch("bilingualsub.utils.ffmpeg.subprocess.Popen") as mock_popen,
            patch(
                "bilingualsub.utils.ffmpeg.extract_video_metadata"
            ) as mock_extract_metadata,
            patch(
                "bilingualsub.utils.ffmpeg.tempfile.SpooledTemporaryFile"
            ) as mock_stderr_file,
        ):
            # Mock process object
            mock_process = MagicMock()
            mock_process.stdout = []  # Empty stdout by default (no progress lines)
            mock_process.wait.return_value = 0  # Success
            mock_popen.return_value = mock_process

            # Mock stderr file
            mock_file = MagicMock()
            mock_file.read.return_value = b""
            mock_stderr_file.return_value.__enter__.return_value = mock_file

            # Mock metadata with duration
            mock_extract_metadata.return_value = {
                "duration": 10.0,
                "width": 1920,
                "height": 1080,
                "fps": 30.0,
                "title": "test video",
            }

            yield {
                "popen": mock_popen,
                "extract_metadata": mock_extract_metadata,
                "stderr_file": mock_stderr_file,
            }

    @pytest.mark.parametrize(
        ("subtitle_format", "expected_filter"),
        [
            (".srt", "subtitles="),
            (".ass", "ass="),
        ],
    )
    @pytest.mark.unit
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

        # Verify subprocess.Popen was called
        mock_popen = mock_ffmpeg["popen"]
        mock_popen.assert_called_once()

        # Get the command passed to Popen
        cmd = mock_popen.call_args[0][0]

        # Verify command structure
        assert cmd[0] == "ffmpeg"
        assert "-i" in cmd
        assert str(video_path) in cmd
        assert "-vf" in cmd

        # Find the filter value
        vf_idx = cmd.index("-vf")
        vf_filter = cmd[vf_idx + 1]
        assert expected_filter in vf_filter
        assert str(subtitle_path) in vf_filter

        # Verify VideoToolbox encoding
        assert "-c:v" in cmd
        c_v_idx = cmd.index("-c:v")
        assert cmd[c_v_idx + 1] == "h264_videotoolbox"

        # Verify audio copy
        assert "-c:a" in cmd
        c_a_idx = cmd.index("-c:a")
        assert cmd[c_a_idx + 1] == "copy"

        # Verify progress output
        assert "-progress" in cmd

        # Verify result
        assert result == output_path

    @pytest.mark.unit
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
        mock_popen = mock_ffmpeg["popen"]
        cmd = mock_popen.call_args[0][0]
        vf_idx = cmd.index("-vf")
        vf_filter = cmd[vf_idx + 1]
        assert "subtitles=" in vf_filter
        assert result == output_path

    @pytest.mark.unit
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
        mock_popen = mock_ffmpeg["popen"]
        cmd = mock_popen.call_args[0][0]
        vf_idx = cmd.index("-vf")
        vf_filter = cmd[vf_idx + 1]
        assert "ass=" in vf_filter
        assert result == output_path

    @pytest.mark.unit
    def test_when_video_does_not_exist_then_raises_value_error(self, tmp_path):
        """Given non-existent video, when burning, then raises error."""
        video_path = tmp_path / "nonexistent.mp4"
        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")
        output_path = tmp_path / "output.mp4"

        with pytest.raises(ValueError, match="Video file does not exist"):
            burn_subtitles(video_path, subtitle_path, output_path)

    @pytest.mark.unit
    def test_when_video_path_is_directory_then_raises_value_error(self, tmp_path):
        """Given video is a directory, when burning, then raises error."""
        video_dir = tmp_path / "video_dir"
        video_dir.mkdir()

        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "output.mp4"

        with pytest.raises(ValueError, match="Video path is not a file"):
            burn_subtitles(video_dir, subtitle_path, output_path)

    @pytest.mark.unit
    def test_when_subtitle_does_not_exist_then_raises_value_error(self, tmp_path):
        """Given non-existent subtitle, when burning, then raises error."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "nonexistent.srt"
        output_path = tmp_path / "output.mp4"

        with pytest.raises(ValueError, match="Subtitle file does not exist"):
            burn_subtitles(video_path, subtitle_path, output_path)

    @pytest.mark.unit
    def test_when_subtitle_path_is_directory_then_raises_value_error(self, tmp_path):
        """Given subtitle is a directory, when burning, then raises error."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_dir = tmp_path / "subtitle_dir"
        subtitle_dir.mkdir()

        output_path = tmp_path / "output.mp4"

        with pytest.raises(ValueError, match="Subtitle path is not a file"):
            burn_subtitles(video_path, subtitle_dir, output_path)

    @pytest.mark.unit
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

    @pytest.mark.unit
    def test_when_ffmpeg_fails_then_raises_ffmpeg_error(self, tmp_path, mock_ffmpeg):
        """Given ffmpeg fails, when burning, then raises FFmpegError."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "output.mp4"

        # Mock ffmpeg error with stderr
        mock_popen = mock_ffmpeg["popen"]
        mock_process = mock_popen.return_value
        mock_process.wait.return_value = 1  # Non-zero exit code

        # Mock stderr file to return error message
        mock_stderr_file = mock_ffmpeg["stderr_file"]
        mock_file = mock_stderr_file.return_value.__enter__.return_value
        mock_file.read.return_value = b"Codec not found"

        with pytest.raises(
            FFmpegError, match=r"Failed to burn subtitles.*Codec not found"
        ):
            burn_subtitles(video_path, subtitle_path, output_path)

    @pytest.mark.unit
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
        mock_popen = mock_ffmpeg["popen"]
        mock_process = mock_popen.return_value
        mock_process.wait.return_value = 1  # Non-zero exit code

        # Mock stderr file to return empty message
        mock_stderr_file = mock_ffmpeg["stderr_file"]
        mock_file = mock_stderr_file.return_value.__enter__.return_value
        mock_file.read.return_value = b""

        with pytest.raises(FFmpegError, match=r"Failed to burn subtitles"):
            burn_subtitles(video_path, subtitle_path, output_path)

    @pytest.mark.parametrize(
        "subtitle_format",
        [".vtt", ".sub", ".sbv", ".json"],
    )
    @pytest.mark.unit
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
        mock_popen = mock_ffmpeg["popen"]
        cmd = mock_popen.call_args[0][0]
        vf_idx = cmd.index("-vf")
        vf_filter = cmd[vf_idx + 1]
        assert "ass=" in vf_filter
        # Verify subtitles filter was NOT used
        assert vf_filter.startswith("ass=")

    @pytest.mark.unit
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
        mock_popen = mock_ffmpeg["popen"]
        cmd = mock_popen.call_args[0][0]
        assert str(video_path) in cmd
        vf_idx = cmd.index("-vf")
        vf_filter = cmd[vf_idx + 1]
        assert str(subtitle_path) in vf_filter
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
        mock_popen = mock_ffmpeg["popen"]
        cmd = mock_popen.call_args[0][0]
        assert str(video_path) in cmd
        vf_idx = cmd.index("-vf")
        vf_filter = cmd[vf_idx + 1]
        assert str(subtitle_path) in vf_filter
        assert result == output_path

    @pytest.mark.unit
    def test_on_progress_called_during_burn(self, tmp_path, mock_ffmpeg):
        """on_progress should be called with percentage during burn."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "output.mp4"

        # Mock metadata with 10 second duration
        mock_ffmpeg["extract_metadata"].return_value = {
            "duration": 10.0,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "title": "test",
        }

        # Mock stdout with progress lines (5 seconds processed out of 10)
        mock_popen = mock_ffmpeg["popen"]
        mock_process = mock_popen.return_value
        mock_process.stdout = [
            b"frame=150\n",
            b"out_time_us=5000000\n",  # 5 seconds in microseconds
            b"progress=continue\n",
        ]

        # Track progress callback calls
        progress_calls = []

        def on_progress(percentage: float) -> None:
            progress_calls.append(percentage)

        result = burn_subtitles(
            video_path, subtitle_path, output_path, on_progress=on_progress
        )

        # Verify on_progress was called
        assert len(progress_calls) > 0
        # Progress should be ~50% (5 seconds out of 10)
        assert 49.0 <= progress_calls[0] <= 51.0
        assert result == output_path

    @pytest.mark.unit
    def test_when_on_darwin_then_uses_videotoolbox_encoder(self, tmp_path, mock_ffmpeg):
        """Given macOS platform, when burning, then uses h264_videotoolbox encoder."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "output.mp4"

        with patch("bilingualsub.utils.ffmpeg.sys.platform", "darwin"):
            burn_subtitles(video_path, subtitle_path, output_path)

        # Verify command uses VideoToolbox encoder
        mock_popen = mock_ffmpeg["popen"]
        cmd = mock_popen.call_args[0][0]

        assert "-c:v" in cmd
        c_v_idx = cmd.index("-c:v")
        assert cmd[c_v_idx + 1] == "h264_videotoolbox"
        assert "-b:v" in cmd
        b_v_idx = cmd.index("-b:v")
        assert cmd[b_v_idx + 1] == "8M"

    @pytest.mark.unit
    def test_when_on_linux_then_uses_libx264_encoder(self, tmp_path, mock_ffmpeg):
        """Given Linux platform, when burning, then uses libx264 encoder."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "output.mp4"

        with patch("bilingualsub.utils.ffmpeg.sys.platform", "linux"):
            burn_subtitles(video_path, subtitle_path, output_path)

        # Verify command uses libx264 encoder
        mock_popen = mock_ffmpeg["popen"]
        cmd = mock_popen.call_args[0][0]

        assert "-c:v" in cmd
        c_v_idx = cmd.index("-c:v")
        assert cmd[c_v_idx + 1] == "libx264"
        assert "-crf" in cmd
        crf_idx = cmd.index("-crf")
        assert cmd[crf_idx + 1] == "23"
        assert "-preset" in cmd
        preset_idx = cmd.index("-preset")
        assert cmd[preset_idx + 1] == "medium"

    @pytest.mark.unit
    def test_when_on_windows_then_uses_libx264_encoder(self, tmp_path, mock_ffmpeg):
        """Given Windows platform, when burning, then uses libx264 encoder."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")

        output_path = tmp_path / "output.mp4"

        with patch("bilingualsub.utils.ffmpeg.sys.platform", "win32"):
            burn_subtitles(video_path, subtitle_path, output_path)

        # Verify command uses libx264 encoder (fallback)
        mock_popen = mock_ffmpeg["popen"]
        cmd = mock_popen.call_args[0][0]

        assert "-c:v" in cmd
        c_v_idx = cmd.index("-c:v")
        assert cmd[c_v_idx + 1] == "libx264"


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


class TestTrimVideo:
    """Test cases for trim_video function."""

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
    def test_trim_video_success(self, tmp_path, mock_ffmpeg):
        """Given valid video, when trimming, then calls ffmpeg correctly."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video content")
        output_path = tmp_path / "trimmed.mp4"

        result = trim_video(video_path, output_path, 10.0, 30.0)

        mock_ffmpeg.input.assert_called_once_with(str(video_path), ss=10.0, to=30.0)
        call_args = mock_ffmpeg.input.return_value.output.call_args
        assert call_args[0] == (str(output_path),)
        assert call_args[1]["c"] == "copy"
        assert result == output_path

    @pytest.mark.unit
    def test_trim_video_not_found(self, tmp_path):
        """Given non-existent video, when trimming, then raises FFmpegError."""
        video_path = tmp_path / "nonexistent.mp4"
        output_path = tmp_path / "trimmed.mp4"

        with pytest.raises(FFmpegError, match="Video file does not exist"):
            trim_video(video_path, output_path, 0.0, 10.0)

    @pytest.mark.unit
    def test_trim_video_is_directory(self, tmp_path):
        """Given directory as video, when trimming, then raises FFmpegError."""
        video_dir = tmp_path / "video_dir"
        video_dir.mkdir()
        output_path = tmp_path / "trimmed.mp4"

        with pytest.raises(FFmpegError, match="Video path is not a file"):
            trim_video(video_dir, output_path, 0.0, 10.0)

    @pytest.mark.unit
    def test_trim_video_ffmpeg_error_with_stderr(self, tmp_path, mock_ffmpeg):
        """Given ffmpeg fails with stderr, when trimming, then raises FFmpegError."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video content")
        output_path = tmp_path / "trimmed.mp4"

        error = Exception("ffmpeg error")
        error.stderr = b"Invalid time range"
        mock_output = mock_ffmpeg.input.return_value.output.return_value
        mock_chain = mock_output.overwrite_output.return_value
        mock_chain.run.side_effect = error

        with pytest.raises(
            FFmpegError, match=r"Failed to trim video.*Invalid time range"
        ):
            trim_video(video_path, output_path, 0.0, 10.0)

    @pytest.mark.unit
    def test_trim_video_ffmpeg_error_without_stderr(self, tmp_path, mock_ffmpeg):
        """Given ffmpeg fails without stderr, when trimming, then raises FFmpegError."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video content")
        output_path = tmp_path / "trimmed.mp4"

        error = Exception("Generic error")
        mock_output = mock_ffmpeg.input.return_value.output.return_value
        mock_chain = mock_output.overwrite_output.return_value
        mock_chain.run.side_effect = error

        with pytest.raises(FFmpegError, match=r"Failed to trim video.*Generic error"):
            trim_video(video_path, output_path, 0.0, 10.0)


class TestGetAudioDuration:
    """Test cases for get_audio_duration function."""

    @pytest.mark.unit
    def test_successful_duration_extraction(self, tmp_path):
        """Given valid audio, when getting duration, then returns seconds."""
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        ffprobe_output = json.dumps({"format": {"duration": "123.456"}})
        with patch("bilingualsub.utils.ffmpeg.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=ffprobe_output)
            result = get_audio_duration(audio_path)

        assert result == 123.456
        mock_run.assert_called_once()

    @pytest.mark.unit
    def test_ffprobe_failure_raises_ffmpeg_error(self, tmp_path):
        """Given ffprobe fails, when getting duration, then raises FFmpegError."""
        audio_path = tmp_path / "audio.mp3"

        with (
            patch(
                "bilingualsub.utils.ffmpeg.subprocess.run",
                side_effect=FileNotFoundError("ffprobe not found"),
            ),
            pytest.raises(FFmpegError, match="ffprobe failed"),
        ):
            get_audio_duration(audio_path)

    @pytest.mark.unit
    def test_missing_duration_field_raises_ffmpeg_error(self, tmp_path):
        """Given no duration in output, when getting duration, then raises FFmpegError."""
        audio_path = tmp_path / "audio.mp3"

        ffprobe_output = json.dumps({"format": {}})
        with patch("bilingualsub.utils.ffmpeg.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=ffprobe_output)
            with pytest.raises(FFmpegError, match="Failed to get duration"):
                get_audio_duration(audio_path)


class TestSplitAudio:
    """Test cases for split_audio function."""

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
    def test_short_audio_returns_single_chunk(self, tmp_path, mock_ffmpeg):
        """Given audio shorter than chunk_duration, when splitting, then returns one chunk."""
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        with patch("bilingualsub.utils.ffmpeg.get_audio_duration", return_value=600.0):
            result = split_audio(audio_path, output_dir=tmp_path)

        assert len(result) == 1
        assert result[0][1] == 0.0
        assert "chunk0" in result[0][0].name

    @pytest.mark.unit
    def test_long_audio_splits_into_correct_number_of_chunks(
        self, tmp_path, mock_ffmpeg
    ):
        """Given long audio, when splitting, then creates correct chunk count."""
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        # 3600 seconds / 1500 default chunk = 3 chunks (0, 1500, 3000)
        with patch("bilingualsub.utils.ffmpeg.get_audio_duration", return_value=3600.0):
            result = split_audio(audio_path, output_dir=tmp_path)

        assert len(result) == 3
        assert result[0][1] == 0.0
        assert result[1][1] == 1500.0
        assert result[2][1] == 3000.0

    @pytest.mark.unit
    def test_custom_chunk_duration(self, tmp_path, mock_ffmpeg):
        """Given custom chunk_duration, when splitting, then uses it."""
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        with patch("bilingualsub.utils.ffmpeg.get_audio_duration", return_value=1000.0):
            result = split_audio(audio_path, output_dir=tmp_path, chunk_duration=400.0)

        assert len(result) == 3
        assert result[0][1] == 0.0
        assert result[1][1] == 400.0
        assert result[2][1] == 800.0

    @pytest.mark.unit
    def test_ffmpeg_failure_raises_ffmpeg_error(self, tmp_path):
        """Given ffmpeg fails, when splitting, then raises FFmpegError."""
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")

        with (
            patch("bilingualsub.utils.ffmpeg.get_audio_duration", return_value=3600.0),
            patch("bilingualsub.utils.ffmpeg.ffmpeg") as mock_ff,
        ):
            mock_stream = MagicMock()
            mock_ff.input.return_value = mock_stream
            mock_stream.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream
            error = Exception("split failed")
            mock_stream.run.side_effect = error

            with pytest.raises(FFmpegError, match="Failed to split audio"):
                split_audio(audio_path, output_dir=tmp_path)

    @pytest.mark.unit
    def test_non_existent_file_raises_error(self, tmp_path):
        """Given non-existent file, when splitting, then raises ValueError."""
        audio_path = tmp_path / "nonexistent.mp3"

        with pytest.raises(ValueError, match="Audio file does not exist"):
            split_audio(audio_path, output_dir=tmp_path)
