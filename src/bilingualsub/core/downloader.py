"""YouTube video downloader with metadata extraction."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yt_dlp


class DownloadError(Exception):
    """Raised when video download or metadata extraction fails."""


@dataclass
class VideoMetadata:
    """Video metadata extracted from downloaded video."""

    title: str
    duration: float  # seconds
    width: int
    height: int
    fps: float

    def __post_init__(self) -> None:
        """Validate metadata constraints."""
        if self.duration <= 0:
            raise ValueError(f"Duration must be positive, got {self.duration}")
        if self.width <= 0:
            raise ValueError(f"Width must be positive, got {self.width}")
        if self.height <= 0:
            raise ValueError(f"Height must be positive, got {self.height}")
        if self.fps <= 0:
            raise ValueError(f"FPS must be positive, got {self.fps}")
        if not self.title.strip():
            raise ValueError("Title cannot be empty or whitespace-only")


def download_youtube_video(url: str, output_path: Path) -> VideoMetadata:
    """
    Download YouTube video and extract metadata.

    Args:
        url: YouTube video URL
        output_path: Path where video will be saved (including extension)

    Returns:
        VideoMetadata with video information

    Raises:
        DownloadError: If download fails or metadata extraction fails
        ValueError: If URL is invalid or output_path is invalid
    """
    if not url.strip():
        raise ValueError("URL cannot be empty")

    if not _is_youtube_url(url):
        raise ValueError(f"Not a valid YouTube URL: {url}")

    if not output_path.parent.exists():
        raise ValueError(f"Output directory does not exist: {output_path.parent}")

    if output_path.exists():
        raise ValueError(f"Output file already exists: {output_path}")

    # Download video
    try:
        _download_video(url, output_path)
    except Exception as e:
        raise DownloadError(f"Failed to download video: {e}") from e

    # Extract metadata using ffprobe
    try:
        metadata = _extract_metadata_with_ffprobe(output_path)
    except Exception as e:
        # Clean up downloaded file on metadata extraction failure
        if output_path.exists():
            output_path.unlink()
        raise DownloadError(f"Failed to extract metadata: {e}") from e

    return metadata


def _is_youtube_url(url: str) -> bool:
    """Check if URL is a valid YouTube URL."""
    youtube_domains = [
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
    ]
    return any(domain in url for domain in youtube_domains)


def _download_video(url: str, output_path: Path) -> None:
    """Download video using yt-dlp."""
    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(output_path.with_suffix("")),  # yt-dlp adds extension
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # yt-dlp adds .mp4 extension, rename if needed
    actual_output = output_path.with_suffix(".mp4")
    if actual_output != output_path and actual_output.exists():
        actual_output.rename(output_path)


def _extract_metadata_with_ffprobe(video_path: Path) -> VideoMetadata:
    """Extract video metadata using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    # Find video stream
    video_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if not video_stream:
        raise DownloadError("No video stream found in file")

    # Extract metadata
    try:
        title = data.get("format", {}).get("tags", {}).get("title", video_path.stem)
        duration = float(data.get("format", {}).get("duration", 0))
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))

        # Parse FPS from r_frame_rate (e.g., "30/1" or "30000/1001")
        fps_str = video_stream.get("r_frame_rate", "0/1")
        num, denom = fps_str.split("/")
        fps = float(num) / float(denom) if float(denom) > 0 else 0.0

    except (KeyError, ValueError, ZeroDivisionError) as e:
        raise DownloadError(f"Failed to parse metadata: {e}") from e

    return VideoMetadata(
        title=title,
        duration=duration,
        width=width,
        height=height,
        fps=fps,
    )
