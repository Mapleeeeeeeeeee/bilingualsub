"""YouTube video downloader with metadata extraction."""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

    # Download video and get info_dict
    try:
        info_dict = _download_video(url, output_path)
    except Exception as e:
        raise DownloadError(f"Failed to download video: {e}") from e

    # Extract metadata - try FFprobe first, fallback to info_dict
    try:
        metadata = _extract_metadata_with_ffprobe(output_path)
    except (FileNotFoundError, OSError, subprocess.CalledProcessError):
        # FFprobe not available or failed, use info_dict as fallback
        try:
            metadata = _extract_metadata_from_info_dict(info_dict, output_path)
        except Exception as e:
            # Clean up downloaded file on metadata extraction failure
            if output_path.exists():
                output_path.unlink()
            raise DownloadError(f"Failed to extract metadata: {e}") from e
    except Exception as e:
        # Other ffprobe errors (e.g., invalid JSON, no video stream)
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


def _download_video(url: str, output_path: Path) -> dict[str, Any]:
    """Download video using yt-dlp and return info_dict."""
    # Check if FFmpeg is available
    has_ffmpeg = shutil.which("ffmpeg") is not None

    if has_ffmpeg:
        # High quality format (requires FFmpeg for merging)
        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": str(output_path.with_suffix("")),  # yt-dlp adds extension
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }
    else:
        # Fallback format (no merge required, works without FFmpeg)
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": str(output_path.with_suffix("")),  # yt-dlp adds extension
            "quiet": True,
            "no_warnings": True,
        }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict_result = ydl.extract_info(url, download=True)
        if not isinstance(info_dict_result, dict):
            raise DownloadError("Failed to extract video info")
        info_dict: dict[str, Any] = info_dict_result

    # yt-dlp may add different extensions depending on format
    possible_extensions = [".mp4", ".webm", ".mkv", ".mov", ".avi"]
    actual_output = None
    for ext in possible_extensions:
        candidate = output_path.with_suffix("").with_suffix(ext)
        if candidate.exists():
            actual_output = candidate
            break

    if actual_output and actual_output != output_path:
        actual_output.rename(output_path)
    elif not output_path.exists():
        # Check if file exists without suffix (some formats)
        no_suffix = output_path.with_suffix("")
        if no_suffix.exists():
            no_suffix.rename(output_path)

    return info_dict


def _extract_metadata_from_info_dict(
    info_dict: dict[str, Any], output_path: Path
) -> VideoMetadata:
    """
    Extract metadata from yt-dlp's info_dict.

    Fallback when FFprobe is unavailable.
    """
    # Extract fields from info_dict with defaults
    title = info_dict.get("title") or output_path.stem
    duration = info_dict.get("duration")
    width = info_dict.get("width")
    height = info_dict.get("height")
    fps = info_dict.get("fps")

    # Validate required fields
    if duration is None or duration <= 0:
        raise DownloadError(
            f"Duration is required but got {duration}. "
            "Please install FFmpeg/FFprobe for reliable metadata extraction."
        )

    if not title or not title.strip():
        raise DownloadError("Title is required but missing from video info")

    # Use defaults for optional fields if missing
    if width is None or width <= 0:
        width = 1920
    if height is None or height <= 0:
        height = 1080
    if fps is None or fps <= 0:
        fps = 30.0

    return VideoMetadata(
        title=title,
        duration=float(duration),
        width=int(width),
        height=int(height),
        fps=float(fps),
    )


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
