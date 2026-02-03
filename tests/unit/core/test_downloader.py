"""Unit tests for YouTube video downloader."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from bilingualsub.core.downloader import (
    DownloadError,
    VideoMetadata,
    download_youtube_video,
)


class TestVideoMetadata:
    """Test cases for VideoMetadata dataclass."""

    def test_valid_metadata(self):
        """Test creating valid metadata."""
        metadata = VideoMetadata(
            title="Test Video",
            duration=120.5,
            width=1920,
            height=1080,
            fps=30.0,
        )

        assert metadata.title == "Test Video"
        assert metadata.duration == 120.5
        assert metadata.width == 1920
        assert metadata.height == 1080
        assert metadata.fps == 30.0

    def test_negative_duration_raises_error(self):
        """Test that negative duration raises error."""
        with pytest.raises(ValueError, match="Duration must be positive"):
            VideoMetadata(
                title="Test",
                duration=-1.0,
                width=1920,
                height=1080,
                fps=30.0,
            )

    def test_zero_duration_raises_error(self):
        """Test that zero duration raises error."""
        with pytest.raises(ValueError, match="Duration must be positive"):
            VideoMetadata(
                title="Test",
                duration=0.0,
                width=1920,
                height=1080,
                fps=30.0,
            )

    def test_negative_width_raises_error(self):
        """Test that negative width raises error."""
        with pytest.raises(ValueError, match="Width must be positive"):
            VideoMetadata(
                title="Test",
                duration=120.0,
                width=-1,
                height=1080,
                fps=30.0,
            )

    def test_negative_height_raises_error(self):
        """Test that negative height raises error."""
        with pytest.raises(ValueError, match="Height must be positive"):
            VideoMetadata(
                title="Test",
                duration=120.0,
                width=1920,
                height=-1,
                fps=30.0,
            )

    def test_negative_fps_raises_error(self):
        """Test that negative fps raises error."""
        with pytest.raises(ValueError, match="FPS must be positive"):
            VideoMetadata(
                title="Test",
                duration=120.0,
                width=1920,
                height=1080,
                fps=-1.0,
            )

    def test_empty_title_raises_error(self):
        """Test that empty title raises error."""
        with pytest.raises(ValueError, match="Title cannot be empty"):
            VideoMetadata(
                title="",
                duration=120.0,
                width=1920,
                height=1080,
                fps=30.0,
            )

    def test_whitespace_title_raises_error(self):
        """Test that whitespace-only title raises error."""
        with pytest.raises(ValueError, match="Title cannot be empty"):
            VideoMetadata(
                title="   \n\t  ",
                duration=120.0,
                width=1920,
                height=1080,
                fps=30.0,
            )


class TestDownloadYoutubeVideo:
    """Test cases for download_youtube_video function."""

    @pytest.fixture
    def mock_yt_dlp(self):
        """Mock yt-dlp."""
        with patch("bilingualsub.core.downloader.yt_dlp") as mock:
            yield mock

    @pytest.fixture
    def mock_subprocess(self):
        """Mock subprocess for ffprobe."""
        with patch("bilingualsub.core.downloader.subprocess") as mock:
            yield mock

    @pytest.fixture
    def valid_ffprobe_output(self) -> str:
        """Return valid ffprobe JSON output."""
        return json.dumps(
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "width": 1920,
                        "height": 1080,
                        "r_frame_rate": "30/1",
                    }
                ],
                "format": {
                    "duration": "120.5",
                    "tags": {"title": "Test Video"},
                },
            }
        )

    def test_download_valid_youtube_url(
        self, tmp_path, mock_yt_dlp, mock_subprocess, valid_ffprobe_output
    ):
        """Test downloading a valid YouTube video."""
        output_path = tmp_path / "video.mp4"

        # Mock yt-dlp download
        mock_ydl_instance = MagicMock()
        mock_yt_dlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl_instance

        # Simulate file creation
        def create_video_file(*args, **kwargs):
            output_path.touch()

        mock_ydl_instance.download.side_effect = create_video_file

        # Mock ffprobe
        mock_result = Mock()
        mock_result.stdout = valid_ffprobe_output
        mock_subprocess.run.return_value = mock_result

        # Download video
        metadata = download_youtube_video(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_path
        )

        # Verify yt-dlp was called correctly
        mock_yt_dlp.YoutubeDL.assert_called_once()
        ydl_opts = mock_yt_dlp.YoutubeDL.call_args[0][0]
        assert "format" in ydl_opts
        assert "outtmpl" in ydl_opts
        assert ydl_opts["merge_output_format"] == "mp4"

        mock_ydl_instance.download.assert_called_once_with(
            ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
        )

        # Verify ffprobe was called
        mock_subprocess.run.assert_called_once()
        ffprobe_call = mock_subprocess.run.call_args
        assert "ffprobe" in ffprobe_call[0][0]
        assert str(output_path) in ffprobe_call[0][0]

        # Verify metadata
        assert metadata.title == "Test Video"
        assert metadata.duration == 120.5
        assert metadata.width == 1920
        assert metadata.height == 1080
        assert metadata.fps == 30.0

    def test_download_with_youtu_be_url(
        self, tmp_path, mock_yt_dlp, mock_subprocess, valid_ffprobe_output
    ):
        """Test downloading with youtu.be short URL."""
        output_path = tmp_path / "video.mp4"

        mock_ydl_instance = MagicMock()
        mock_yt_dlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl_instance
        mock_ydl_instance.download.side_effect = (
            lambda *args, **kwargs: output_path.touch()
        )

        mock_result = Mock()
        mock_result.stdout = valid_ffprobe_output
        mock_subprocess.run.return_value = mock_result

        metadata = download_youtube_video("https://youtu.be/dQw4w9WgXcQ", output_path)

        assert metadata.title == "Test Video"
        mock_ydl_instance.download.assert_called_once()

    def test_empty_url_raises_error(self, tmp_path):
        """Test that empty URL raises error."""
        with pytest.raises(ValueError, match="URL cannot be empty"):
            download_youtube_video("", tmp_path / "video.mp4")

        with pytest.raises(ValueError, match="URL cannot be empty"):
            download_youtube_video("   ", tmp_path / "video.mp4")

    def test_non_youtube_url_raises_error(self, tmp_path):
        """Test that non-YouTube URL raises error."""
        with pytest.raises(ValueError, match="Not a valid YouTube URL"):
            download_youtube_video("https://vimeo.com/123456", tmp_path / "video.mp4")

    def test_output_directory_not_exists_raises_error(self):
        """Test that non-existent output directory raises error."""
        with pytest.raises(ValueError, match="Output directory does not exist"):
            download_youtube_video(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                Path("/nonexistent/path/video.mp4"),
            )

    def test_output_file_exists_raises_error(self, tmp_path):
        """Test that existing output file raises error."""
        output_path = tmp_path / "video.mp4"
        output_path.touch()

        with pytest.raises(ValueError, match="Output file already exists"):
            download_youtube_video(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_path
            )

    def test_yt_dlp_download_error_raises_download_error(
        self, tmp_path, mock_yt_dlp, mock_subprocess
    ):
        """Test that yt-dlp download error raises DownloadError."""
        output_path = tmp_path / "video.mp4"

        mock_ydl_instance = MagicMock()
        mock_yt_dlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl_instance
        mock_ydl_instance.download.side_effect = Exception("Network error")

        with pytest.raises(DownloadError, match="Failed to download video"):
            download_youtube_video(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_path
            )

    def test_ffprobe_error_raises_download_error_and_cleans_up(
        self, tmp_path, mock_yt_dlp, mock_subprocess
    ):
        """Test that ffprobe error raises DownloadError and cleans up file."""
        output_path = tmp_path / "video.mp4"

        # Mock yt-dlp download
        mock_ydl_instance = MagicMock()
        mock_yt_dlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl_instance
        mock_ydl_instance.download.side_effect = (
            lambda *args, **kwargs: output_path.touch()
        )

        # Mock ffprobe error
        mock_subprocess.run.side_effect = subprocess.CalledProcessError(1, "ffprobe")

        with pytest.raises(DownloadError, match="Failed to extract metadata"):
            download_youtube_video(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_path
            )

        # Verify file was cleaned up
        assert not output_path.exists()

    def test_ffprobe_no_video_stream_raises_error(
        self, tmp_path, mock_yt_dlp, mock_subprocess
    ):
        """Test that missing video stream in ffprobe output raises error."""
        output_path = tmp_path / "video.mp4"

        mock_ydl_instance = MagicMock()
        mock_yt_dlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl_instance
        mock_ydl_instance.download.side_effect = (
            lambda *args, **kwargs: output_path.touch()
        )

        # Mock ffprobe with no video stream
        mock_result = Mock()
        mock_result.stdout = json.dumps(
            {
                "streams": [
                    {"codec_type": "audio"}  # Only audio stream
                ],
                "format": {"duration": "120.0"},
            }
        )
        mock_subprocess.run.return_value = mock_result

        with pytest.raises(DownloadError, match="No video stream found"):
            download_youtube_video(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_path
            )

        # Verify file was cleaned up
        assert not output_path.exists()

    def test_ffprobe_invalid_json_raises_error(
        self, tmp_path, mock_yt_dlp, mock_subprocess
    ):
        """Test that invalid JSON from ffprobe raises error."""
        output_path = tmp_path / "video.mp4"

        mock_ydl_instance = MagicMock()
        mock_yt_dlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl_instance
        mock_ydl_instance.download.side_effect = (
            lambda *args, **kwargs: output_path.touch()
        )

        # Mock ffprobe with invalid JSON
        mock_result = Mock()
        mock_result.stdout = "invalid json"
        mock_subprocess.run.return_value = mock_result

        with pytest.raises(DownloadError, match="Failed to extract metadata"):
            download_youtube_video(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_path
            )

        assert not output_path.exists()

    def test_ffprobe_missing_title_uses_filename(
        self, tmp_path, mock_yt_dlp, mock_subprocess
    ):
        """Test that missing title in ffprobe uses filename as fallback."""
        output_path = tmp_path / "my_video.mp4"

        mock_ydl_instance = MagicMock()
        mock_yt_dlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl_instance
        mock_ydl_instance.download.side_effect = (
            lambda *args, **kwargs: output_path.touch()
        )

        # Mock ffprobe without title
        mock_result = Mock()
        mock_result.stdout = json.dumps(
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "width": 1920,
                        "height": 1080,
                        "r_frame_rate": "30/1",
                    }
                ],
                "format": {
                    "duration": "120.5",
                    "tags": {},  # No title
                },
            }
        )
        mock_subprocess.run.return_value = mock_result

        metadata = download_youtube_video(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_path
        )

        assert metadata.title == "my_video"

    def test_ffprobe_fractional_fps(self, tmp_path, mock_yt_dlp, mock_subprocess):
        """Test parsing fractional FPS like 30000/1001."""
        output_path = tmp_path / "video.mp4"

        mock_ydl_instance = MagicMock()
        mock_yt_dlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl_instance
        mock_ydl_instance.download.side_effect = (
            lambda *args, **kwargs: output_path.touch()
        )

        # Mock ffprobe with fractional fps
        mock_result = Mock()
        mock_result.stdout = json.dumps(
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "width": 1920,
                        "height": 1080,
                        "r_frame_rate": "30000/1001",  # NTSC fps
                    }
                ],
                "format": {
                    "duration": "120.5",
                    "tags": {"title": "Test"},
                },
            }
        )
        mock_subprocess.run.return_value = mock_result

        metadata = download_youtube_video(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_path
        )

        assert metadata.fps == pytest.approx(29.97, rel=0.01)

    def test_yt_dlp_adds_mp4_extension(
        self, tmp_path, mock_yt_dlp, mock_subprocess, valid_ffprobe_output
    ):
        """Test handling when yt-dlp adds .mp4 extension."""
        output_path = tmp_path / "video.mkv"  # Request .mkv

        mock_ydl_instance = MagicMock()
        mock_yt_dlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl_instance

        # Simulate yt-dlp creating .mp4 instead
        def create_mp4_file(*args, **kwargs):
            (tmp_path / "video.mp4").touch()

        mock_ydl_instance.download.side_effect = create_mp4_file

        mock_result = Mock()
        mock_result.stdout = valid_ffprobe_output
        mock_subprocess.run.return_value = mock_result

        metadata = download_youtube_video(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_path
        )

        # Verify file was renamed
        assert output_path.exists()
        assert not (tmp_path / "video.mp4").exists()
        assert metadata.title == "Test Video"

    @pytest.mark.unit
    def test_all_youtube_url_formats_accepted(self, tmp_path):
        """Test that all common YouTube URL formats are accepted."""
        valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
        ]

        for url in valid_urls:
            # Just test URL validation, not actual download
            with (
                patch("bilingualsub.core.downloader._download_video"),
                patch(
                    "bilingualsub.core.downloader._extract_metadata_with_ffprobe"
                ) as mock_extract,
            ):
                mock_extract.return_value = VideoMetadata(
                    title="Test",
                    duration=120.0,
                    width=1920,
                    height=1080,
                    fps=30.0,
                )
                output_path = tmp_path / f"video_{valid_urls.index(url)}.mp4"
                # Should not raise ValueError
                download_youtube_video(url, output_path)
