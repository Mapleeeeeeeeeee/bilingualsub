"""Unit tests for generate_intro, concat_videos, and burn_subtitles watermark branch."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bilingualsub.utils.ffmpeg import (
    FFmpegError,
    _escape_drawtext,
    burn_subtitles,
    concat_videos,
    generate_intro,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_MOCK_METADATA = {
    "duration": 10.0,
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
    "title": "test video",
    "has_audio": True,
}


def _make_popen_mock(returncode: int = 0) -> MagicMock:
    """Return a pre-configured Popen mock that reports success by default."""
    process = MagicMock()
    process.stdout = []  # no progress lines → no on_progress calls
    process.wait.return_value = returncode
    return process


def _get_popen_cmd(mock_popen: MagicMock) -> list[str]:
    """Extract the command list from the first Popen call."""
    return mock_popen.call_args[0][0]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_burn_ffmpeg():
    """Mock subprocess.Popen, extract_video_metadata, and SpooledTemporaryFile
    for burn_subtitles tests."""
    with (
        patch("bilingualsub.utils.ffmpeg.subprocess.Popen") as mock_popen,
        patch("bilingualsub.utils.ffmpeg.extract_video_metadata") as mock_metadata,
        patch("bilingualsub.utils.ffmpeg.tempfile.SpooledTemporaryFile") as mock_stderr,
    ):
        mock_popen.return_value = _make_popen_mock(returncode=0)

        mock_file = MagicMock()
        mock_file.read.return_value = b""
        mock_stderr.return_value.__enter__.return_value = mock_file

        mock_metadata.return_value = _MOCK_METADATA

        yield {
            "popen": mock_popen,
            "metadata": mock_metadata,
            "stderr_file": mock_stderr,
        }


@pytest.fixture
def mock_intro_ffmpeg():
    """Mock subprocess.Popen and SpooledTemporaryFile for generate_intro tests."""
    with (
        patch("bilingualsub.utils.ffmpeg.subprocess.Popen") as mock_popen,
        patch("bilingualsub.utils.ffmpeg.tempfile.SpooledTemporaryFile") as mock_stderr,
    ):
        mock_popen.return_value = _make_popen_mock(returncode=0)

        mock_file = MagicMock()
        mock_file.read.return_value = b""
        mock_stderr.return_value.__enter__.return_value = mock_file

        yield {
            "popen": mock_popen,
            "stderr_file": mock_stderr,
        }


# ---------------------------------------------------------------------------
# burn_subtitles — watermark branch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBurnSubtitlesWatermark:
    """Tests for the watermark_text parameter of burn_subtitles."""

    def test_when_watermark_text_given_then_vf_contains_drawtext(
        self, tmp_path: Path, mock_burn_ffmpeg: dict
    ) -> None:
        """Given watermark_text, the -vf filter must include a drawtext segment."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")
        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")
        output_path = tmp_path / "output.mp4"

        burn_subtitles(
            video_path, subtitle_path, output_path, watermark_text="Source: TestChannel"
        )

        cmd = _get_popen_cmd(mock_burn_ffmpeg["popen"])
        vf_idx = cmd.index("-vf")
        vf_filter = cmd[vf_idx + 1]
        # The filter chain must contain a drawtext element after a comma
        assert "drawtext=" in vf_filter
        assert "Source\\: TestChannel" in vf_filter

    def test_when_watermark_text_is_none_then_vf_has_no_drawtext(
        self, tmp_path: Path, mock_burn_ffmpeg: dict
    ) -> None:
        """Given watermark_text=None, the -vf filter must NOT include drawtext (regression guard)."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")
        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")
        output_path = tmp_path / "output.mp4"

        burn_subtitles(video_path, subtitle_path, output_path, watermark_text=None)

        cmd = _get_popen_cmd(mock_burn_ffmpeg["popen"])
        vf_idx = cmd.index("-vf")
        vf_filter = cmd[vf_idx + 1]
        assert "drawtext=" not in vf_filter

    def test_when_watermark_text_contains_colon_then_escaped_in_drawtext(
        self, tmp_path: Path, mock_burn_ffmpeg: dict
    ) -> None:
        """Given watermark_text with ':', the colon must be escaped as \\: in the filter."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")
        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")
        output_path = tmp_path / "output.mp4"

        burn_subtitles(video_path, subtitle_path, output_path, watermark_text="Ch:Name")

        cmd = _get_popen_cmd(mock_burn_ffmpeg["popen"])
        vf_idx = cmd.index("-vf")
        vf_filter = cmd[vf_idx + 1]
        # Raw ':' must not appear as a bare character inside the drawtext value
        assert "Ch\\:Name" in vf_filter

    def test_when_watermark_text_contains_single_quote_then_escaped_in_drawtext(
        self, tmp_path: Path, mock_burn_ffmpeg: dict
    ) -> None:
        """Given watermark_text with \"'\", it must be escaped as \\' in the filter."""
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")
        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_bytes(b"fake subtitle")
        output_path = tmp_path / "output.mp4"

        burn_subtitles(
            video_path, subtitle_path, output_path, watermark_text="Bob's Channel"
        )

        cmd = _get_popen_cmd(mock_burn_ffmpeg["popen"])
        vf_idx = cmd.index("-vf")
        vf_filter = cmd[vf_idx + 1]
        assert "Bob\\'s Channel" in vf_filter


# ---------------------------------------------------------------------------
# generate_intro
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateIntro:
    """Tests for generate_intro."""

    def test_when_channel_url_given_then_cmd_contains_color_source_and_channel_url(
        self, tmp_path: Path, mock_intro_ffmpeg: dict
    ) -> None:
        """generate_intro with channel_url must use lavfi color source and embed the URL."""
        output_path = tmp_path / "intro.mp4"

        generate_intro(
            output_path,
            width=1280,
            height=720,
            fps=30.0,
            channel="TestChannel",
            video_title="My Video",
            video_url="https://youtube.com/watch?v=abc",
            channel_url="https://youtube.com/@TestChannel",
        )

        cmd = _get_popen_cmd(mock_intro_ffmpeg["popen"])
        # Must use lavfi color input (not a file path)
        assert "-f" in cmd
        lavfi_idx = cmd.index("-f")
        assert cmd[lavfi_idx + 1] == "lavfi"
        assert any("color=c=black" in arg for arg in cmd)
        # Channel URL must appear in the -vf filter
        vf_idx = cmd.index("-vf")
        vf_value = cmd[vf_idx + 1]
        assert "TestChannel" in vf_value
        # _escape_drawtext converts ":" to "\:", so the colon in https: is escaped
        assert "https\\://youtube.com/@TestChannel" in vf_value
        # 13 drawtext blocks when channel_url is present (12 without)
        assert vf_value.count("drawtext=") == 13

    def test_when_channel_url_empty_then_vf_does_not_contain_channel_url_value(
        self, tmp_path: Path, mock_intro_ffmpeg: dict
    ) -> None:
        """generate_intro with channel_url='' must NOT embed the URL in the filter."""
        output_path = tmp_path / "intro.mp4"
        channel_url = "https://youtube.com/@ShouldNotAppear"

        generate_intro(
            output_path,
            width=1280,
            height=720,
            fps=30.0,
            channel="TestChannel",
            video_title="My Video",
            video_url="https://youtube.com/watch?v=abc",
            channel_url="",  # empty → skip channel URL drawtext block
        )

        cmd = _get_popen_cmd(mock_intro_ffmpeg["popen"])
        vf_idx = cmd.index("-vf")
        vf_value = cmd[vf_idx + 1]
        assert channel_url not in vf_value
        # Exactly 12 drawtext blocks when channel_url is omitted (13 when present)
        assert vf_value.count("drawtext=") == 12

    def test_generate_intro_uses_cjk_font_fallback_for_chinese_text(
        self, tmp_path: Path, mock_intro_ffmpeg: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Chinese intro text should target an installed CJK font, not generic serif."""
        output_path = tmp_path / "intro.mp4"
        monkeypatch.setattr(
            "bilingualsub.utils.ffmpeg._FONT_ZH_REGULAR",
            tmp_path / "missing-noto-sans-tc.ttf",
        )

        generate_intro(
            output_path,
            width=1280,
            height=720,
            fps=30.0,
            channel="ClaudeDevs",
            video_title="ClaudeDevs - Artifacts in Claude Code",
            video_url="https://x.com/ClaudeDevs/status/2072770790114914317?s=20",
            channel_url="https://x.com/ClaudeDevs",
        )

        cmd = _get_popen_cmd(mock_intro_ffmpeg["popen"])
        vf_idx = cmd.index("-vf")
        vf_value = cmd[vf_idx + 1]

        assert "font='Noto Sans CJK TC'" in vf_value
        assert "font='serif'" not in vf_value

    def test_when_ffmpeg_fails_then_raises_ffmpeg_error(
        self, tmp_path: Path, mock_intro_ffmpeg: dict
    ) -> None:
        """generate_intro must raise FFmpegError when the subprocess exits non-zero."""
        output_path = tmp_path / "intro.mp4"

        mock_process = mock_intro_ffmpeg["popen"].return_value
        mock_process.wait.return_value = 1  # non-zero → failure

        mock_file = mock_intro_ffmpeg["stderr_file"].return_value.__enter__.return_value
        mock_file.read.return_value = b"lavfi color error"

        with pytest.raises(FFmpegError, match="Failed to generate intro"):
            generate_intro(
                output_path,
                width=1280,
                height=720,
                fps=30.0,
                channel="Ch",
                video_title="T",
                video_url="https://example.com",
            )

    def test_generate_intro_always_uses_libx264_regardless_of_platform(
        self, tmp_path: Path, mock_intro_ffmpeg: dict
    ) -> None:
        """generate_intro must always pass -c:v libx264 even when platform is darwin."""
        output_path = tmp_path / "intro.mp4"

        with patch("bilingualsub.utils.ffmpeg.sys.platform", "darwin"):
            generate_intro(
                output_path,
                width=1920,
                height=1080,
                fps=30.0,
                channel="Ch",
                video_title="T",
                video_url="https://example.com",
            )

        cmd = _get_popen_cmd(mock_intro_ffmpeg["popen"])
        assert "-c:v" in cmd
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "libx264"
        # VideoToolbox must NOT be used for intro
        assert "h264_videotoolbox" not in cmd

    def test_generate_intro_includes_silent_audio_track_for_concat(
        self, tmp_path: Path, mock_intro_ffmpeg: dict
    ) -> None:
        """Intro must include silent AAC audio so concat keeps the main video's audio."""
        output_path = tmp_path / "intro.mp4"

        generate_intro(
            output_path,
            width=1920,
            height=1080,
            fps=30.0,
            channel="Ch",
            video_title="T",
            video_url="https://example.com",
        )

        cmd = _get_popen_cmd(mock_intro_ffmpeg["popen"])
        assert "anullsrc=channel_layout=stereo:sample_rate=48000" in cmd
        assert "-an" not in cmd
        assert "-c:a" in cmd
        ca_idx = cmd.index("-c:a")
        assert cmd[ca_idx + 1] == "aac"
        assert "-shortest" in cmd


# ---------------------------------------------------------------------------
# concat_videos
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConcatVideos:
    """Tests for concat_videos."""

    @pytest.fixture
    def mock_concat_ffmpeg(self):
        """Mock subprocess.Popen, SpooledTemporaryFile, and extract_video_metadata
        for concat_videos tests."""
        with (
            patch("bilingualsub.utils.ffmpeg.subprocess.Popen") as mock_popen,
            patch(
                "bilingualsub.utils.ffmpeg.tempfile.SpooledTemporaryFile"
            ) as mock_stderr,
            patch("bilingualsub.utils.ffmpeg.extract_video_metadata") as mock_metadata,
        ):
            mock_popen.return_value = _make_popen_mock(returncode=0)

            mock_file = MagicMock()
            mock_file.read.return_value = b""
            mock_stderr.return_value.__enter__.return_value = mock_file

            mock_metadata.return_value = _MOCK_METADATA

            yield {
                "popen": mock_popen,
                "stderr_file": mock_stderr,
                "metadata": mock_metadata,
            }

    def test_when_both_inputs_exist_then_video_is_copied_via_concat_demuxer(
        self, tmp_path: Path, mock_concat_ffmpeg: dict
    ) -> None:
        """concat_videos must splice video via the concat demuxer with -c:v copy.

        Video re-encoding is unnecessary (both clips are matching h264 from
        this pipeline), so the video track must still be a stream copy.
        """
        first = tmp_path / "intro.mp4"
        first.write_bytes(b"fake intro")
        second = tmp_path / "main.mp4"
        second.write_bytes(b"fake main")
        output = tmp_path / "final.mp4"

        concat_videos(first, second, output)

        cmd = _get_popen_cmd(mock_concat_ffmpeg["popen"])

        # Must specify concat demuxer
        assert "-f" in cmd
        f_idx = cmd.index("-f")
        assert cmd[f_idx + 1] == "concat"

        # Video must remain a stream copy
        assert "-c:v" in cmd
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "copy"

        # Video track must be mapped from the concat-demuxer input
        assert "-map" in cmd
        assert "0:v" in cmd

    def test_when_both_inputs_exist_then_audio_is_normalized_and_reencoded(
        self, tmp_path: Path, mock_concat_ffmpeg: dict
    ) -> None:
        """concat_videos must NOT stream-copy audio.

        Regression guard: `-c:a copy` under the concat demuxer assumes the
        intro and main video's audio share identical sample rate/channel
        layout, which is false when the main video's downloaded audio (e.g.
        44.1kHz) differs from the generated intro's audio (48kHz). Copying
        raw packets under one container-level format mislabels the second
        clip's audio, producing decode errors / silence. The command must
        instead decode each source's audio independently (`[1:a]`, `[2:a]`
        from the two extra -i inputs), normalize via aformat, join with the
        concat audio filter, and re-encode once with -c:a aac.
        """
        first = tmp_path / "intro.mp4"
        first.write_bytes(b"fake intro")
        second = tmp_path / "main.mp4"
        second.write_bytes(b"fake main")
        output = tmp_path / "final.mp4"

        concat_videos(first, second, output)

        cmd = _get_popen_cmd(mock_concat_ffmpeg["popen"])

        # Audio must be re-encoded, not copied
        assert "-c:a" in cmd
        ca_idx = cmd.index("-c:a")
        assert cmd[ca_idx + 1] == "aac"

        # A top-level "-c copy" (both streams) must no longer be used
        assert "-c" not in cmd

        # Each source's audio must be decoded independently (not via the
        # concat-demuxer input) and joined with the concat audio filter
        assert "-filter_complex" in cmd
        fc_idx = cmd.index("-filter_complex")
        filter_graph = cmd[fc_idx + 1]
        assert "[1:a]" in filter_graph
        assert "[2:a]" in filter_graph
        assert "concat=n=2:v=0:a=1" in filter_graph

        # Both original files must be passed as extra inputs for that filter
        assert str(first) in cmd
        assert str(second) in cmd

        # Filtered audio output must be mapped into the final stream
        assert "[aout]" in cmd

    def test_when_first_input_does_not_exist_then_raises_ffmpeg_error(
        self, tmp_path: Path
    ) -> None:
        """concat_videos must raise FFmpegError when the first input file is missing."""
        first = tmp_path / "nonexistent.mp4"  # does not exist
        second = tmp_path / "main.mp4"
        second.write_bytes(b"fake main")
        output = tmp_path / "final.mp4"

        with pytest.raises(FFmpegError, match="First video does not exist"):
            concat_videos(first, second, output)

    def test_when_second_input_does_not_exist_then_raises_ffmpeg_error(
        self, tmp_path: Path
    ) -> None:
        """concat_videos must raise FFmpegError when the second input file is missing."""
        first = tmp_path / "intro.mp4"
        first.write_bytes(b"fake intro")
        second = tmp_path / "nonexistent.mp4"  # does not exist
        output = tmp_path / "final.mp4"

        with pytest.raises(FFmpegError, match="Second video does not exist"):
            concat_videos(first, second, output)

    def test_given_both_inputs_have_audio_when_concat_then_each_side_is_trimmed_to_its_own_duration(
        self, tmp_path: Path, mock_concat_ffmpeg: dict
    ) -> None:
        """Regression: untrimmed [1:a]/[2:a] concat used to splice each side's
        full (possibly drifted) audio length instead of clamping it to that
        side's own video duration. yt-dlp downloads video and audio as
        separate streams that get muxed together, so small duration drift
        between a file's video and audio stream is routine; without trimming,
        that drift causes audio desync (trailing audio past video end, or a
        silent gap) in the concatenated output. Each side's atrim=duration=
        must match that side's own metadata duration, not the other side's.
        """
        first = tmp_path / "intro.mp4"
        first.write_bytes(b"fake intro")
        second = tmp_path / "main.mp4"
        second.write_bytes(b"fake main")
        output = tmp_path / "final.mp4"

        meta_first = {**_MOCK_METADATA, "duration": 1.5, "has_audio": True}
        meta_second = {**_MOCK_METADATA, "duration": 7.25, "has_audio": True}
        mock_concat_ffmpeg["metadata"].side_effect = [meta_first, meta_second]

        concat_videos(first, second, output)

        cmd = _get_popen_cmd(mock_concat_ffmpeg["popen"])
        fc_idx = cmd.index("-filter_complex")
        filter_graph = cmd[fc_idx + 1]

        assert "atrim=duration=1.5" in filter_graph
        assert "atrim=duration=7.25" in filter_graph

    def test_given_only_first_input_has_audio_when_concat_then_second_side_is_padded_with_silence(
        self, tmp_path: Path, mock_concat_ffmpeg: dict
    ) -> None:
        """When one side has no audio stream at all, hardcoded [1:a]/[2:a]
        used to make ffmpeg fail with "Error binding filtergraph
        inputs/outputs" because the nonexistent stream can't be referenced.
        The silent side must instead be padded with a generated anullsrc
        segment so the concat audio filter always joins two real streams.
        """
        first = tmp_path / "intro.mp4"
        first.write_bytes(b"fake intro")
        second = tmp_path / "main.mp4"
        second.write_bytes(b"fake main")
        output = tmp_path / "final.mp4"

        meta_first = {**_MOCK_METADATA, "duration": 2.0, "has_audio": True}
        meta_second = {**_MOCK_METADATA, "duration": 5.0, "has_audio": False}
        mock_concat_ffmpeg["metadata"].side_effect = [meta_first, meta_second]

        concat_videos(first, second, output)

        cmd = _get_popen_cmd(mock_concat_ffmpeg["popen"])
        fc_idx = cmd.index("-filter_complex")
        filter_graph = cmd[fc_idx + 1]

        assert "anullsrc" in filter_graph
        assert "-map" in cmd
        assert "[aout]" in cmd

    def test_given_only_second_input_has_audio_when_concat_then_first_side_is_padded_with_silence(
        self, tmp_path: Path, mock_concat_ffmpeg: dict
    ) -> None:
        """Mirror of the above with the silent side swapped: the intro (first
        input) commonly has no real audio in some pipeline configurations, so
        the padding logic must work symmetrically regardless of which side
        lacks an audio stream.
        """
        first = tmp_path / "intro.mp4"
        first.write_bytes(b"fake intro")
        second = tmp_path / "main.mp4"
        second.write_bytes(b"fake main")
        output = tmp_path / "final.mp4"

        meta_first = {**_MOCK_METADATA, "duration": 1.0, "has_audio": False}
        meta_second = {**_MOCK_METADATA, "duration": 3.0, "has_audio": True}
        mock_concat_ffmpeg["metadata"].side_effect = [meta_first, meta_second]

        concat_videos(first, second, output)

        cmd = _get_popen_cmd(mock_concat_ffmpeg["popen"])
        fc_idx = cmd.index("-filter_complex")
        filter_graph = cmd[fc_idx + 1]

        assert "anullsrc" in filter_graph
        assert "[aout]" in cmd

    def test_given_neither_input_has_audio_when_concat_then_no_filter_complex_and_video_only_map(
        self, tmp_path: Path, mock_concat_ffmpeg: dict
    ) -> None:
        """When neither side has an audio stream, the command must not claim
        an audio stream it can't build: no -filter_complex, no -c:a, and the
        only -map must be the video track from the concat-demuxer input.
        """
        first = tmp_path / "intro.mp4"
        first.write_bytes(b"fake intro")
        second = tmp_path / "main.mp4"
        second.write_bytes(b"fake main")
        output = tmp_path / "final.mp4"

        meta_first = {**_MOCK_METADATA, "has_audio": False}
        meta_second = {**_MOCK_METADATA, "has_audio": False}
        mock_concat_ffmpeg["metadata"].side_effect = [meta_first, meta_second]

        concat_videos(first, second, output)

        cmd = _get_popen_cmd(mock_concat_ffmpeg["popen"])

        assert "-filter_complex" not in cmd
        assert "-c:a" not in cmd
        assert "[aout]" not in cmd
        assert "-map" in cmd
        assert cmd.count("-map") == 1
        map_idx = cmd.index("-map")
        assert cmd[map_idx + 1] == "0:v"
        assert "-c:v" in cmd
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "copy"


# ---------------------------------------------------------------------------
# _escape_drawtext (pure-function unit tests)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEscapeDrawtext:
    """Tests for the _escape_drawtext helper."""

    def test_colon_is_escaped(self) -> None:
        assert _escape_drawtext("a:b") == "a\\:b"

    def test_single_quote_is_escaped(self) -> None:
        assert _escape_drawtext("it's") == "it\\'s"

    def test_backslash_is_doubled(self) -> None:
        assert _escape_drawtext("a\\b") == "a\\\\b"

    def test_plain_text_unchanged(self) -> None:
        assert _escape_drawtext("hello world") == "hello world"

    def test_percent_is_doubled(self) -> None:
        assert _escape_drawtext("100%") == "100%%"
