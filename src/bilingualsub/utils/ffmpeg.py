"""FFmpeg utilities for burning subtitles into videos."""

import json
import subprocess
from pathlib import Path

import ffmpeg


class FFmpegError(Exception):
    """Exception raised when FFmpeg operations fail."""


def burn_subtitles(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path,
) -> Path:
    """Burn subtitles into video.

    Args:
        video_path: Input video file
        subtitle_path: Subtitle file (.srt or .ass)
        output_path: Output video file

    Returns:
        Path to output video file

    Raises:
        ValueError: If paths are invalid
        FFmpegError: If ffmpeg fails
    """
    # Validate input video file
    if not video_path.exists():
        raise ValueError(f"Video file does not exist: {video_path}")
    if not video_path.is_file():
        raise ValueError(f"Video path is not a file: {video_path}")

    # Validate subtitle file
    if not subtitle_path.exists():
        raise ValueError(f"Subtitle file does not exist: {subtitle_path}")
    if not subtitle_path.is_file():
        raise ValueError(f"Subtitle path is not a file: {subtitle_path}")

    # Validate subtitle format
    subtitle_suffix = subtitle_path.suffix.lower()
    if subtitle_suffix not in {".srt", ".ass"}:
        raise ValueError(
            f"Unsupported subtitle format: {subtitle_suffix}. "
            "Supported formats: .srt, .ass"
        )

    # Determine the appropriate ffmpeg filter based on subtitle format
    if subtitle_suffix == ".ass":
        # Use ass filter for ASS subtitles
        vf_filter = f"ass={subtitle_path}"
    else:
        # Use subtitles filter for SRT subtitles with yellow text + black outline
        force_style = (
            "Fontname=Arial,Fontsize=22,"
            "PrimaryColour=&H0000FFFF,"
            "OutlineColour=&H00000000,"
            "Outline=2,Shadow=0,"
            "Alignment=2,MarginL=30,MarginR=30,MarginV=30"
        )
        vf_filter = f"subtitles={subtitle_path}:force_style='{force_style}'"

    # Burn subtitles using ffmpeg
    try:
        (
            ffmpeg.input(str(video_path))
            .output(str(output_path), vf=vf_filter, acodec="copy")
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except Exception as e:
        # Catch all exceptions from ffmpeg (ffmpeg.Error or any other error)
        if hasattr(e, "stderr") and e.stderr:
            stderr = e.stderr
            error_message = (
                stderr.decode() if isinstance(stderr, bytes) else str(stderr)
            )
        else:
            error_message = str(e)
        raise FFmpegError(f"Failed to burn subtitles: {error_message}") from e

    return output_path


def extract_audio(
    video_path: Path,
    output_path: Path,
    *,
    bitrate: str = "64k",
) -> Path:
    """Extract audio from video as compressed MP3.

    Args:
        video_path: Input video file
        output_path: Output audio file (.mp3)
        bitrate: Audio bitrate (default 64k, sufficient for speech recognition)

    Returns:
        Path to output audio file

    Raises:
        FFmpegError: If video file does not exist or ffmpeg fails
    """
    if not video_path.exists():
        raise FFmpegError(f"Video file does not exist: {video_path}")
    if not video_path.is_file():
        raise FFmpegError(f"Video path is not a file: {video_path}")

    try:
        (
            ffmpeg.input(str(video_path))
            .output(
                str(output_path), acodec="libmp3lame", audio_bitrate=bitrate, vn=None
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except Exception as e:
        if hasattr(e, "stderr") and e.stderr:
            stderr = e.stderr
            error_message = (
                stderr.decode() if isinstance(stderr, bytes) else str(stderr)
            )
        else:
            error_message = str(e)
        raise FFmpegError(f"Failed to extract audio: {error_message}") from e

    return output_path


def trim_video(
    video_path: Path,
    output_path: Path,
    start_time: float,
    end_time: float,
) -> Path:
    """Trim video to specified time range using FFmpeg.

    Args:
        video_path: Input video file
        output_path: Output trimmed video file
        start_time: Start time in seconds
        end_time: End time in seconds

    Returns:
        Path to output video file

    Raises:
        FFmpegError: If video file does not exist or ffmpeg fails
    """
    if not video_path.exists():
        raise FFmpegError(f"Video file does not exist: {video_path}")
    if not video_path.is_file():
        raise FFmpegError(f"Video path is not a file: {video_path}")

    try:
        (
            ffmpeg.input(str(video_path), ss=start_time, to=end_time)
            .output(str(output_path), c="copy")
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except Exception as e:
        if hasattr(e, "stderr") and e.stderr:
            stderr = e.stderr
            error_message = (
                stderr.decode() if isinstance(stderr, bytes) else str(stderr)
            )
        else:
            error_message = str(e)
        raise FFmpegError(f"Failed to trim video: {error_message}") from e

    return output_path


def extract_video_metadata(video_path: Path) -> dict[str, str | float | int]:
    """Extract video metadata using ffprobe.

    Args:
        video_path: Path to the video file

    Returns:
        Dict with keys: title, duration, width, height, fps

    Raises:
        FFmpegError: If ffprobe fails or no video stream found
    """
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

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise FFmpegError(f"ffprobe failed for {video_path}: {e}") from e

    data = json.loads(result.stdout)

    # Find video stream
    video_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if not video_stream:
        raise FFmpegError(f"No video stream found in {video_path}")

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
        raise FFmpegError(f"Failed to parse metadata: {e}") from e

    return {
        "title": title,
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
    }


def get_audio_duration(audio_path: Path) -> float:
    """Get audio duration in seconds using ffprobe.

    Args:
        audio_path: Path to the audio file

    Returns:
        Duration in seconds

    Raises:
        FFmpegError: If ffprobe fails or duration is missing
    """
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        str(audio_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise FFmpegError(f"ffprobe failed for {audio_path}: {e}") from e

    data = json.loads(result.stdout)

    try:
        return float(data["format"]["duration"])
    except (KeyError, ValueError, TypeError) as e:
        raise FFmpegError(f"Failed to get duration from {audio_path}: {e}") from e


def split_audio(
    audio_path: Path,
    output_dir: Path,
    chunk_duration: float = 1500.0,
) -> list[tuple[Path, float]]:
    """Split audio into chunks.

    Args:
        audio_path: Path to the audio file
        output_dir: Directory for output chunks
        chunk_duration: Maximum chunk duration in seconds (default 25 min)

    Returns:
        List of (chunk_path, time_offset_seconds) tuples

    Raises:
        FFmpegError: If ffmpeg/ffprobe fails
        ValueError: If audio file does not exist
    """
    if not audio_path.exists():
        raise ValueError(f"Audio file does not exist: {audio_path}")
    if not audio_path.is_file():
        raise ValueError(f"Audio path is not a file: {audio_path}")

    total_duration = get_audio_duration(audio_path)
    chunks: list[tuple[Path, float]] = []
    offset = 0.0
    chunk_idx = 0

    while offset < total_duration:
        chunk_path = (
            output_dir / f"{audio_path.stem}_chunk{chunk_idx}{audio_path.suffix}"
        )
        duration = min(chunk_duration, total_duration - offset)

        try:
            (
                ffmpeg.input(str(audio_path), ss=offset, t=duration)
                .output(str(chunk_path), acodec="copy")
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
        except Exception as e:
            if hasattr(e, "stderr") and e.stderr:
                stderr = e.stderr
                error_message = (
                    stderr.decode() if isinstance(stderr, bytes) else str(stderr)
                )
            else:
                error_message = str(e)
            raise FFmpegError(f"Failed to split audio: {error_message}") from e

        chunks.append((chunk_path, offset))
        offset += chunk_duration
        chunk_idx += 1

    return chunks
