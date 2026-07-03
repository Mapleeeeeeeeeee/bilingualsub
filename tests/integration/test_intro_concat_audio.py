"""Regression tests for intro + video concat audio preservation."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from bilingualsub.utils.ffmpeg import concat_videos, generate_intro

if TYPE_CHECKING:
    from pathlib import Path


def _has_ffmpeg_tools() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


requires_ffmpeg_tools = pytest.mark.skipif(
    not _has_ffmpeg_tools(),
    reason="ffmpeg and ffprobe are required for media regression tests",
)


def _create_video_with_audio(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=24:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-shortest",
            "-y",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _audio_stream_count(path: Path) -> int:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-select_streams",
            "a",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return len(json.loads(result.stdout).get("streams", []))


@pytest.mark.integration
@requires_ffmpeg_tools
def test_intro_concat_preserves_main_video_audio(tmp_path: Path) -> None:
    """Regression: a silent intro must not make the final concat output video-only."""
    intro = tmp_path / "intro.mp4"
    main = tmp_path / "main.mp4"
    final = tmp_path / "final.mp4"

    generate_intro(
        intro,
        width=320,
        height=180,
        fps=24.0,
        channel="ClaudeDevs",
        video_title="Artifacts in Claude Code",
        video_url="https://x.com/ClaudeDevs/status/2072770790114914317?s=20",
        channel_url="https://x.com/ClaudeDevs",
        duration=1.0,
    )
    _create_video_with_audio(main)

    concat_videos(intro, main, final)

    assert _audio_stream_count(final) == 1
