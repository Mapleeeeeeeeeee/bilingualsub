"""FFmpeg utilities for burning subtitles into videos."""

import json
import subprocess  # nosec B404
import sys
import tempfile
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path

import ffmpeg

# ---------------------------------------------------------------------------
# Bundled font paths — assets/fonts/ next to the project root
# ---------------------------------------------------------------------------

_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "fonts"
_FONT_EN_REGULAR = _ASSETS_DIR / "LINESeedSans_Rg.ttf"
_FONT_EN_BOLD = _ASSETS_DIR / "LINESeedSans_Bd.ttf"
_FONT_ZH_REGULAR = _ASSETS_DIR / "NotoSansTC-Regular.ttf"
_FONT_ZH_BOLD = _ASSETS_DIR / "NotoSansTC-Bold.ttf"
_FONT_ZH_FALLBACK = "Noto Sans CJK TC"


def _font_arg(fontfile: Path, fallback_name: str) -> str:
    """Return a drawtext font option.

    Uses ``fontfile='<path>'`` when the bundled file exists, otherwise falls
    back to ``font='<name>'`` so the filter chain still works without the
    assets directory (e.g. inside Docker where system fonts are available).
    """
    if fontfile.exists():
        # fontfile= needs an absolute path; resolve() guarantees that.
        escaped = str(fontfile.resolve()).replace("'", "'").replace(":", r"\:")
        return f"fontfile='{escaped}'"
    return f"font='{fallback_name}'"


class FFmpegError(Exception):
    """Exception raised when FFmpeg operations fail."""


def _parse_and_report_progress(
    stream: Iterable[bytes],
    *,
    total_duration: float,
    on_progress: Callable[[float], None],
) -> None:
    """Parse ffmpeg progress stream and emit percentage updates."""
    for line in stream:
        decoded = line.decode("utf-8", errors="replace").strip()
        if not decoded.startswith("out_time_us="):
            continue

        try:
            time_us = int(decoded.split("=")[1])
            progress = min(time_us / (total_duration * 1_000_000) * 100, 99.0)
            on_progress(progress)
        except (ValueError, IndexError):
            continue


def _escape_drawtext(text: str) -> str:
    """Escape special characters for FFmpeg drawtext filter."""
    return (
        text.replace("\\", "\\\\")
        .replace("%", "%%")
        .replace("'", "\\'")
        .replace(":", "\\:")
    )


def _run_ffmpeg_with_progress(
    cmd: list[str],
    *,
    total_duration: float,
    on_progress: Callable[[float], None] | None,
    error_prefix: str,
) -> None:
    """Run an FFmpeg command, streaming progress and raising FFmpegError on failure."""
    stdout_target: int = (
        subprocess.PIPE
        if on_progress is not None and total_duration > 0
        else subprocess.DEVNULL
    )

    with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as stderr_file:
        try:
            process = subprocess.Popen(  # nosec B603
                cmd,
                stdout=stdout_target,
                stderr=stderr_file,
            )

            if process.stdout:
                try:
                    if on_progress is not None:
                        _parse_and_report_progress(
                            process.stdout,
                            total_duration=total_duration,
                            on_progress=on_progress,
                        )
                finally:
                    close_stdout = getattr(process.stdout, "close", None)
                    if callable(close_stdout):
                        close_stdout()

            returncode = process.wait()
            if returncode != 0:
                stderr_file.seek(0)
                stderr_output = stderr_file.read().decode("utf-8", errors="replace")
                raise FFmpegError(f"{error_prefix}: {stderr_output}")
        except FFmpegError:
            raise
        except Exception as e:
            raise FFmpegError(f"{error_prefix}: {e}") from e


def _append_watermark_drawtext(vf_filter: str, watermark_text: str) -> str:
    """Append a corner watermark drawtext filter to an existing vf filter chain."""
    safe_text = _escape_drawtext(watermark_text)
    watermark_drawtext = (
        f"drawtext=text='{safe_text}'"
        f":{_font_arg(_FONT_EN_REGULAR, 'Arial')}"
        ":fontsize=16"
        ":fontcolor=white@0.6"
        ":shadowcolor=black@0.8"
        ":shadowx=1:shadowy=1"
        ":x=w-tw-20"
        ":y=18"
    )
    return f"{vf_filter},{watermark_drawtext}"


def burn_subtitles(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path,
    *,
    on_progress: Callable[[float], None] | None = None,
    watermark_text: str | None = None,
) -> Path:
    """Burn subtitles into video.

    Args:
        video_path: Input video file
        subtitle_path: Subtitle file (.srt or .ass)
        output_path: Output video file
        on_progress: Optional callback for progress updates (0-100)
        watermark_text: Optional watermark text to overlay in the top-right corner

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
            "Fontname=Arial,Fontsize=16,"
            "PrimaryColour=&H0000FFFF,"
            "OutlineColour=&H00000000,"
            "Outline=2,Shadow=0,"
            "Alignment=2,MarginL=30,MarginR=30,MarginV=30"
        )
        vf_filter = f"subtitles={subtitle_path}:force_style='{force_style}'"

    if watermark_text is not None:
        vf_filter = _append_watermark_drawtext(vf_filter, watermark_text)

    # Get video duration for progress calculation
    metadata = extract_video_metadata(video_path)
    total_duration = float(metadata["duration"])

    # Determine encoder based on platform
    if sys.platform == "darwin":
        # macOS: use VideoToolbox hardware acceleration
        encoder_args = ["-c:v", "h264_videotoolbox", "-b:v", "8M"]
    else:
        # Linux/other: use libx264 software encoder
        encoder_args = ["-c:v", "libx264", "-crf", "23", "-preset", "medium"]

    # Build ffmpeg command with platform-appropriate encoder
    cmd = [
        "ffmpeg",
        "-i",
        str(video_path),
        "-vf",
        vf_filter,
        *encoder_args,
        "-c:a",
        "copy",
        "-progress",
        "pipe:1",
        "-y",
        str(output_path),
    ]

    _run_ffmpeg_with_progress(
        cmd,
        total_duration=total_duration,
        on_progress=on_progress,
        error_prefix="Failed to burn subtitles",
    )
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
        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
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
        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
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


def generate_intro(  # noqa: PLR0915
    output_path: Path,
    *,
    width: int,
    height: int,
    fps: float,
    channel: str,
    video_title: str,
    video_url: str,
    channel_url: str = "",
    duration: float = 5.0,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Generate a black-background intro card video with source attribution text.

    Forces libx264 (not h264_videotoolbox) because lavfi color source does not
    support hardware-accelerated encoding paths on macOS.
    """
    left_margin = int(width * 0.10)

    # Each text layer fades in 0.3 s after the previous; earliest at t=0.3
    fade_step = 0.3
    blocks: list[str] = []

    def _block_enable(start: float) -> str:
        return f"between(t,{start:.1f},{duration:.1f})"

    def _dt(
        text: str,
        font_spec: str,
        fontsize: int,
        fontcolor: str,
        x: str,
        y: str,
        enable_expr: str,
        fade_start: float,
    ) -> str:
        """Build a drawtext filter block.

        ``font_spec`` is the output of ``_font_arg()`` — either
        ``fontfile='<path>'`` or ``font='<name>'``.
        """
        safe = _escape_drawtext(text)
        alpha_expr = f"if(lt(t,{fade_start:.1f}),0,min((t-{fade_start:.1f})/0.3,1))"
        return (
            f"drawtext=text='{safe}'"
            f":{font_spec}"
            f":fontsize={fontsize}"
            f":fontcolor={fontcolor}"
            f":x={x}"
            f":y={y}"
            f":alpha='{alpha_expr}'"
            f":enable='{enable_expr}'"
            ":fix_bounds=1"
        )

    # Y positions: vertically centered with generous spacing
    # Total content height ~50% of frame, starting at ~28%
    y_eyebrow = int(height * 0.22)
    y_chinese_label = y_eyebrow + int(height * 0.04)
    y_channel = y_chinese_label + int(height * 0.05)
    y_channel_url = y_channel + int(height * 0.055)
    y_title = (y_channel_url if channel_url else y_channel) + int(height * 0.06)
    y_video_url = y_title + int(height * 0.04)
    y_decl_zh_1 = y_video_url + int(height * 0.06)
    y_decl_zh_2 = y_decl_zh_1 + int(height * 0.03)
    y_decl_zh_3 = y_decl_zh_2 + int(height * 0.03)
    y_decl_en_1 = y_decl_zh_3 + int(height * 0.04)
    y_decl_en_2 = y_decl_en_1 + int(height * 0.028)
    y_decl_en_3 = y_decl_en_2 + int(height * 0.028)

    x_left = str(left_margin)
    x_brand = f"w-tw-{int(width * 0.04)}"
    y_brand = f"h-th-{int(height * 0.05)}"

    slot = 0

    def _next_start() -> float:
        nonlocal slot
        start = fade_step + slot * fade_step
        slot += 1
        return start

    # Eyebrow
    _start = _next_start()
    blocks.append(
        _dt(
            "ORIGINAL VIDEO FROM",
            _font_arg(_FONT_EN_REGULAR, "Arial"),
            max(1, int(height / 54)),
            "white@0.3",
            x_left,
            str(y_eyebrow),
            _block_enable(_start),
            _start,
        )
    )

    # Chinese label
    _start = _next_start()
    blocks.append(
        _dt(
            "原始影片來自",
            _font_arg(_FONT_ZH_REGULAR, _FONT_ZH_FALLBACK),
            max(1, int(height / 42)),
            "white@0.6",
            x_left,
            str(y_chinese_label),
            _block_enable(_start),
            _start,
        )
    )

    # Channel name
    _start = _next_start()
    blocks.append(
        _dt(
            channel,
            _font_arg(_FONT_EN_BOLD, "Arial"),
            max(1, int(height / 17)),
            "white@1.0",
            x_left,
            str(y_channel),
            _block_enable(_start),
            _start,
        )
    )

    # Channel URL (optional)
    if channel_url:
        _start = _next_start()
        blocks.append(
            _dt(
                channel_url,
                _font_arg(_FONT_EN_REGULAR, "Arial"),
                max(1, int(height / 49)),
                "white@0.35",
                x_left,
                str(y_channel_url),
                _block_enable(_start),
                _start,
            )
        )

    # Video title
    _start = _next_start()
    blocks.append(
        _dt(
            video_title,
            _font_arg(_FONT_ZH_REGULAR, _FONT_ZH_FALLBACK),
            max(1, int(height / 34)),
            "white@0.7",
            x_left,
            str(y_title),
            _block_enable(_start),
            _start,
        )
    )

    # Video URL
    _start = _next_start()
    blocks.append(
        _dt(
            video_url,
            _font_arg(_FONT_EN_REGULAR, "Arial"),
            max(1, int(height / 45)),
            "white@0.5",
            x_left,
            str(y_video_url),
            _block_enable(_start),
            _start,
        )
    )

    # Chinese declaration (3 lines)
    decl_zh = [
        "翻譯字幕使用開源專案 BilingualSub 製作",
        "所有內容及著作權屬於原始創作者所有",
        "如需移除，請聯繫上傳者",  # noqa: RUF001
    ]
    decl_zh_y = [y_decl_zh_1, y_decl_zh_2, y_decl_zh_3]
    decl_zh_start = _next_start()
    for line, y_pos in zip(decl_zh, decl_zh_y, strict=True):
        blocks.append(
            _dt(
                line,
                _font_arg(_FONT_ZH_REGULAR, _FONT_ZH_FALLBACK),
                max(1, int(height / 45)),
                "white@0.45",
                x_left,
                str(y_pos),
                _block_enable(decl_zh_start),
                decl_zh_start,
            )
        )

    # English declaration (3 lines)
    decl_en = [
        "Subtitles created with BilingualSub (open source)",
        "All content and copyrights belong to the original creator",
        "For removal requests, please contact the uploader",
    ]
    decl_en_y = [y_decl_en_1, y_decl_en_2, y_decl_en_3]
    decl_en_start = _next_start()
    for line, y_pos in zip(decl_en, decl_en_y, strict=True):
        blocks.append(
            _dt(
                line,
                _font_arg(_FONT_EN_REGULAR, "Arial"),
                max(1, int(height / 49)),
                "white@0.35",
                x_left,
                str(y_pos),
                _block_enable(decl_en_start),
                decl_en_start,
            )
        )

    # BilingualSub branding at bottom-right corner
    blocks.append(
        _dt(
            "BilingualSub",
            _font_arg(_FONT_EN_REGULAR, "Arial"),
            max(1, int(height / 54)),
            "white@0.25",
            x_brand,
            y_brand,
            _block_enable(fade_step),
            fade_step,
        )
    )

    fade_out_start = duration - 0.5
    drawtext_chain = ",".join(blocks)
    vf = f"{drawtext_chain},fade=t=out:st={fade_out_start:.2f}:d=0.5"

    cmd = [
        "ffmpeg",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={width}x{height}:r={fps}:d={duration}",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-crf",
        "23",
        "-preset",
        "fast",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        "-progress",
        "pipe:1",
        "-y",
        str(output_path),
    ]

    _run_ffmpeg_with_progress(
        cmd,
        total_duration=duration,
        on_progress=on_progress,
        error_prefix="Failed to generate intro",
    )
    return output_path


def concat_videos(
    first_path: Path,
    second_path: Path,
    output_path: Path,
    *,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Concatenate two videos using FFmpeg concat demuxer (no re-encode)."""
    if not first_path.exists() or not first_path.is_file():
        raise FFmpegError(f"First video does not exist: {first_path}")
    if not second_path.exists() or not second_path.is_file():
        raise FFmpegError(f"Second video does not exist: {second_path}")

    concat_list_path = output_path.parent / f"concat_list_{uuid.uuid4().hex[:8]}.txt"
    try:
        concat_list_path.write_text(
            f"file '{first_path.resolve()}'\nfile '{second_path.resolve()}'\n",
            encoding="utf-8",
        )

        # Estimate total duration for progress (sum of both clips)
        try:
            meta1 = extract_video_metadata(first_path)
            meta2 = extract_video_metadata(second_path)
            total_duration = float(meta1["duration"]) + float(meta2["duration"])
        except FFmpegError:
            total_duration = 0.0

        cmd = [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_path),
            "-c",
            "copy",
            "-progress",
            "pipe:1",
            "-y",
            str(output_path),
        ]

        _run_ffmpeg_with_progress(
            cmd,
            total_duration=total_duration,
            on_progress=on_progress,
            error_prefix="Failed to concat videos",
        )
    finally:
        if concat_list_path.exists():
            concat_list_path.unlink()

    return output_path
