"""FFmpeg utilities for burning subtitles into videos."""

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
        # Use subtitles filter for SRT subtitles
        vf_filter = f"subtitles={subtitle_path}"

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
