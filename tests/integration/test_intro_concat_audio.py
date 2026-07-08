"""Regression tests for intro + video concat audio preservation.

Bug this guards against: concat_videos() used to splice the intro and the
main video's audio with `-c:a copy` (raw packet concatenation) under the
FFmpeg concat demuxer. That assumes both clips' audio streams share the same
sample rate/channel layout/codec parameters. The intro's audio is always
generated at 48kHz, while the main video's audio (downloaded via yt-dlp) is
commonly 44.1kHz. Copy-concatenating packets from two different sample rates
mislabels the second clip's raw AAC data under the first clip's container-level
format, which strict decoders either reject ("Error submitting packet to
decoder", "Number of bands exceeds limit") or render as silence/garbage —
i.e. "burned video has no sound" after the intro. These tests exercise that
exact mismatch (48kHz intro vs. 44.1kHz main video) and assert the final
output decodes cleanly and is actually audible for the ENTIRE duration,
not just structurally has one audio stream.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import TYPE_CHECKING, NamedTuple

import pytest

from bilingualsub.utils.ffmpeg import concat_videos, generate_intro

if TYPE_CHECKING:
    from pathlib import Path

# Near-total-silence threshold in dBFS. FFmpeg's volumedetect reports
# mean_volume close to this (~-91dB) for a fully silent/corrupted PCM stream.
_NEAR_SILENCE_DB = -85.0

_MAIN_VIDEO_SAMPLE_RATE = 44100  # Deliberately mismatched vs. the intro's 48kHz.
_INTRO_DURATION = 1.0
_MAIN_VIDEO_DURATION = 3.0

# AAC decodes in whole frames (~21.3ms @ 48kHz): a `-t` cutoff placed exactly
# on the intro/main-video boundary decodes one extra trailing AAC frame that
# spans into the main video's audible audio, polluting a mean_volume check
# with a few milliseconds of real signal even when the intro segment itself
# is genuinely silent. Backing the window off by this margin keeps the check
# inside the intro's own audio and away from that decoder-frame rounding.
_INTRO_SILENCE_CHECK_MARGIN = 0.1
_INTRO_SILENCE_CHECK_DURATION = _INTRO_DURATION - _INTRO_SILENCE_CHECK_MARGIN


def _has_ffmpeg_tools() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


requires_ffmpeg_tools = pytest.mark.skipif(
    not _has_ffmpeg_tools(),
    reason="ffmpeg and ffprobe are required for media regression tests",
)


def _create_video_with_audio(path: Path, *, sample_rate: int, duration: float) -> None:
    """Create a test video whose audio is an audible sine tone.

    `sample_rate` is intentionally a parameter (not hardcoded) so tests can
    create a main-video audio track at a different rate than the intro's,
    reproducing the real-world mismatch this bug was about.
    """
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=320x180:rate=24:d={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate={sample_rate}:d={duration}",
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


def _create_video_without_audio(path: Path, *, duration: float) -> None:
    """Create a test video with no audio stream at all (ffmpeg -an).

    Used to exercise concat_videos()'s "one side has no audio" branch: a
    main video with zero audio streams must still concat successfully with
    a (silent-audio) generated intro, instead of ffmpeg failing to bind a
    nonexistent [N:a] filtergraph input.
    """
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=320x180:rate=24:d={duration}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
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


class VolumeDetectResult(NamedTuple):
    stderr: str
    mean_volume_db: float


def _run_volumedetect(
    path: Path, *, start_time: float = 0.0, duration: float | None = None
) -> VolumeDetectResult:
    """Decode `path`'s audio stream (or the segment [`start_time`,
    `start_time + duration`)) end to end.

    Uses `-af volumedetect -f null -` to force full decoding without writing
    output, so decoder errors surface in stderr and loudness stats let us
    assert the audio isn't silent/corrupted. `duration`, when given, bounds
    the decode window with `-t` so callers can isolate e.g. just the intro's
    own segment instead of decoding to end-of-file.

    `-map 0:a` explicitly selects only the audio stream. concat_videos()'s
    output always has video + audio muxed together; without an explicit map,
    `-t` (used here as an output-duration limiter, since it's positioned
    after `-i` with a single input) is resolved against *all* muxed output
    streams. FFmpeg 6.1.1 (Ubuntu 24.04, the CI runner's apt package) and
    8.1.2 (this repo's macOS dev baseline) disagree on how that limiter
    interacts with a video stream sharing the output: measured on identical
    inputs (1.0s intro + 3.0s 44.1kHz main video), an unmapped `-t 0.9`
    decodes 90112 audio samples (938.7ms, matching a `-map 0:a`-scoped decode
    on *both* ffmpeg versions) on 8.1.2, but 102400 samples (1066.7ms) on
    6.1.1 — 6144 samples/channel (128ms) past the intended cutoff, far enough
    to pull real signal from the main video's audio into what should be an
    intro-only window and produce a false "intro segment is audible" failure.
    `silencedetect` on the `-map 0:a`-scoped stream (no `-t` at all) confirms
    the actual audio content is identical between versions (silence_end at
    0.997646s on both) — the mismatch is entirely in how `-t` resolves
    against unmapped multi-stream output, not in concat_videos()'s audio
    boundary. Scoping to `-map 0:a` removes that version-dependent confound.
    """
    cmd = ["ffmpeg"]
    if start_time > 0:
        cmd += ["-ss", str(start_time)]
    cmd += ["-i", str(path), "-map", "0:a"]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += ["-af", "volumedetect", "-f", "null", "-"]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, (
        f"ffmpeg exited with {result.returncode}; stderr:\n{result.stderr}"
    )
    match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", result.stderr)
    assert match, f"volumedetect did not report mean_volume; stderr:\n{result.stderr}"
    return VolumeDetectResult(
        stderr=result.stderr, mean_volume_db=float(match.group(1))
    )


def _assert_no_decoder_errors(stderr: str) -> None:
    decoder_error_markers = (
        "Error submitting packet to decoder",
        "Number of bands exceeds limit",
        "Invalid data found when processing input",
    )
    for marker in decoder_error_markers:
        assert marker not in stderr, (
            f"decoder error {marker!r} found in ffmpeg output:\n{stderr}"
        )


@pytest.fixture
def concatenated_video(tmp_path: Path) -> Path:
    """Build final.mp4 from a 48kHz intro + a 44.1kHz main video."""
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
        duration=_INTRO_DURATION,
    )
    _create_video_with_audio(
        main, sample_rate=_MAIN_VIDEO_SAMPLE_RATE, duration=_MAIN_VIDEO_DURATION
    )

    concat_videos(intro, main, final)
    return final


@pytest.mark.integration
@requires_ffmpeg_tools
def test_given_mismatched_sample_rates_when_concat_then_single_audio_stream_present(
    concatenated_video: Path,
) -> None:
    """Regression: a silent intro must not make the final concat output video-only."""
    assert _audio_stream_count(concatenated_video) == 1


@pytest.mark.integration
@requires_ffmpeg_tools
def test_given_mismatched_sample_rates_when_concat_then_audio_decodes_cleanly(
    concatenated_video: Path,
) -> None:
    """Regression: copy-concat of 48kHz intro + 44.1kHz main audio used to
    mislabel the main video's packets under the intro's sample rate,
    producing decoder errors on strict decoders. The whole file must decode
    without error now that audio is normalized/re-encoded at concat time.
    """
    result = _run_volumedetect(concatenated_video)
    _assert_no_decoder_errors(result.stderr)


@pytest.mark.integration
@requires_ffmpeg_tools
def test_given_mismatched_sample_rates_when_concat_then_main_video_audio_is_audible(
    concatenated_video: Path,
) -> None:
    """Regression: the exact symptom users reported — sound present during
    the intro but silent for the whole main video afterward — because the
    main video's mismatched-sample-rate audio packets decoded as
    garbage/silence past the intro boundary. Checking only the whole-file
    mean volume would not catch this, since a few seconds of real intro
    audio could mask a fully silent main-video segment; the segment
    starting right after the intro must independently be audible.
    """
    result = _run_volumedetect(concatenated_video, start_time=_INTRO_DURATION)
    _assert_no_decoder_errors(result.stderr)
    assert result.mean_volume_db > _NEAR_SILENCE_DB, (
        f"main-video audio segment is near-silent ({result.mean_volume_db} dB); "
        f"stderr:\n{result.stderr}"
    )


@pytest.mark.integration
@requires_ffmpeg_tools
def test_given_mismatched_sample_rates_when_concat_then_full_output_is_audible(
    concatenated_video: Path,
) -> None:
    """Sanity check across the full duration (intro + main video)."""
    result = _run_volumedetect(concatenated_video)
    assert result.mean_volume_db > _NEAR_SILENCE_DB, (
        f"final output audio is near-silent ({result.mean_volume_db} dB); "
        f"stderr:\n{result.stderr}"
    )


@pytest.mark.integration
@requires_ffmpeg_tools
def test_given_mismatched_sample_rates_when_concat_then_intro_segment_is_silent(
    concatenated_video: Path,
) -> None:
    """Regression: a [1:a]/[2:a] swap in concat_videos() would put the main
    video's audible audio in the intro's own window (and the intro's silent
    audio after it) instead of the correct order. generate_intro() always
    produces silent audio (anullsrc), while the main video's audio here is an
    audible 440Hz tone, so the intro's own segment [0, _INTRO_DURATION) must
    independently be near-silent. Without this check, a swapped-input bug
    would still pass the existing "main video segment is audible" and
    "whole file is audible" tests, since a swap just relocates the audible
    segment rather than removing it. The check window is backed off from the
    exact intro/main-video boundary by `_INTRO_SILENCE_CHECK_MARGIN` so an
    AAC decoder-frame overrun at the cut point (see comment on that constant)
    can't leak a few milliseconds of the main video's real audio in and give
    a false positive.
    """
    result = _run_volumedetect(
        concatenated_video, duration=_INTRO_SILENCE_CHECK_DURATION
    )
    assert result.mean_volume_db <= _NEAR_SILENCE_DB, (
        f"intro audio segment is unexpectedly audible ({result.mean_volume_db} dB), "
        f"suggesting the main video's audio was placed in the intro's window; "
        f"stderr:\n{result.stderr}"
    )


@pytest.mark.integration
@requires_ffmpeg_tools
def test_given_main_video_has_no_audio_stream_when_concat_then_output_has_one_audio_stream(
    tmp_path: Path,
) -> None:
    """Regression: hardcoded [1:a]/[2:a] used to make concat_videos() crash
    with "Error binding filtergraph inputs/outputs: Invalid argument" when
    one side had no audio stream at all. A main video downloaded with no
    audio track must still concat successfully with the (silent-audio)
    generated intro, padding the missing side with generated silence.
    """
    intro = tmp_path / "intro.mp4"
    main = tmp_path / "main_no_audio.mp4"
    final = tmp_path / "final_no_audio.mp4"

    generate_intro(
        intro,
        width=320,
        height=180,
        fps=24.0,
        channel="ClaudeDevs",
        video_title="Artifacts in Claude Code",
        video_url="https://x.com/ClaudeDevs/status/2072770790114914317?s=20",
        channel_url="https://x.com/ClaudeDevs",
        duration=_INTRO_DURATION,
    )
    _create_video_without_audio(main, duration=_MAIN_VIDEO_DURATION)

    concat_videos(intro, main, final)

    assert _audio_stream_count(final) == 1
