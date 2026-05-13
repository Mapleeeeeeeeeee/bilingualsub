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

    def test_when_both_inputs_exist_then_cmd_uses_concat_demuxer_and_copy(
        self, tmp_path: Path, mock_concat_ffmpeg: dict
    ) -> None:
        """concat_videos must build a command with -f concat and -c copy."""
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

        # Must copy streams without re-encoding
        assert "-c" in cmd
        c_idx = cmd.index("-c")
        assert cmd[c_idx + 1] == "copy"

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
