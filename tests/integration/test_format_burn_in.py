"""Integration tests: serialized subtitle formats -> burn_subtitles compatibility."""

from unittest.mock import MagicMock, patch

import pytest

from bilingualsub.core.merger import merge_subtitles
from bilingualsub.core.subtitle import Subtitle
from bilingualsub.formats.ass import serialize_bilingual_ass
from bilingualsub.formats.srt import serialize_srt
from bilingualsub.utils.ffmpeg import burn_subtitles


@pytest.mark.integration
class TestFormatBurnIn:
    """Verify serialized subtitle output is accepted by burn_subtitles."""

    def test_when_serialized_srt_written_to_file_then_burn_subtitles_accepts_it(
        self,
        sample_subtitle_3_entries: Subtitle,
        sample_translated_3_entries: Subtitle,
        tmp_path: "pytest.TempPathFactory",
    ) -> None:
        # Merge into bilingual entries, then serialize to SRT
        merged = merge_subtitles(
            sample_subtitle_3_entries.entries,
            sample_translated_3_entries.entries,
        )
        bilingual_sub = Subtitle(entries=merged)
        srt_content = serialize_srt(bilingual_sub)

        # Write SRT file
        srt_path = tmp_path / "bilingual.srt"
        srt_path.write_text(srt_content, encoding="utf-8")

        # Create fake video file
        video_path = tmp_path / "input.mp4"
        video_path.write_bytes(b"fake video")

        output_path = tmp_path / "output.mp4"

        with (
            patch(
                "bilingualsub.utils.ffmpeg.extract_video_metadata",
                return_value={
                    "duration": 10.0,
                    "width": 1920,
                    "height": 1080,
                    "fps": 30.0,
                    "title": "test",
                },
            ),
            patch("bilingualsub.utils.ffmpeg.subprocess.Popen") as mock_popen,
        ):
            process = MagicMock()
            process.stdout = []
            process.wait.return_value = 0
            mock_popen.return_value = process
            result = burn_subtitles(video_path, srt_path, output_path)

        # Verify burn_subtitles accepted the SRT file
        assert result == output_path
        mock_popen.assert_called_once()
        ffmpeg_cmd = mock_popen.call_args.args[0]
        vf_idx = ffmpeg_cmd.index("-vf")
        assert "subtitles=" in ffmpeg_cmd[vf_idx + 1]

    def test_when_serialized_ass_written_to_file_then_burn_subtitles_accepts_it(
        self,
        sample_subtitle_3_entries: Subtitle,
        sample_translated_3_entries: Subtitle,
        tmp_path: "pytest.TempPathFactory",
    ) -> None:
        # Serialize to ASS
        ass_content = serialize_bilingual_ass(
            sample_subtitle_3_entries,
            sample_translated_3_entries,
            video_width=1920,
            video_height=1080,
        )

        # Write ASS file
        ass_path = tmp_path / "bilingual.ass"
        ass_path.write_text(ass_content, encoding="utf-8")

        # Create fake video file
        video_path = tmp_path / "input.mp4"
        video_path.write_bytes(b"fake video")

        output_path = tmp_path / "output.mp4"

        with (
            patch(
                "bilingualsub.utils.ffmpeg.extract_video_metadata",
                return_value={
                    "duration": 10.0,
                    "width": 1920,
                    "height": 1080,
                    "fps": 30.0,
                    "title": "test",
                },
            ),
            patch("bilingualsub.utils.ffmpeg.subprocess.Popen") as mock_popen,
        ):
            process = MagicMock()
            process.stdout = []
            process.wait.return_value = 0
            mock_popen.return_value = process
            result = burn_subtitles(video_path, ass_path, output_path)

        # Verify burn_subtitles accepted the ASS file
        assert result == output_path
        mock_popen.assert_called_once()
        ffmpeg_cmd = mock_popen.call_args.args[0]
        vf_idx = ffmpeg_cmd.index("-vf")
        assert "ass=" in ffmpeg_cmd[vf_idx + 1]

    def test_serialized_ass_file_content_is_valid_ass_format(
        self,
        sample_subtitle_3_entries: Subtitle,
        sample_translated_3_entries: Subtitle,
        tmp_path: "pytest.TempPathFactory",
    ) -> None:
        # Serialize to ASS and write to file
        ass_content = serialize_bilingual_ass(
            sample_subtitle_3_entries,
            sample_translated_3_entries,
            video_width=1920,
            video_height=1080,
        )

        ass_path = tmp_path / "bilingual.ass"
        ass_path.write_text(ass_content, encoding="utf-8")

        # Read back and validate ASS structure
        file_content = ass_path.read_text(encoding="utf-8")

        # Validate ASS sections
        assert "[Script Info]" in file_content
        assert "PlayResX: 1920" in file_content
        assert "PlayResY: 1080" in file_content
        assert "[V4+ Styles]" in file_content
        assert "Style: Translated" in file_content
        assert "Style: Original" in file_content
        assert "[Events]" in file_content

        # Validate Dialogue lines: 3 entries x 2 (Translated + Original) = 6
        dialogue_lines = [
            line for line in file_content.splitlines() if line.startswith("Dialogue:")
        ]
        assert len(dialogue_lines) == 6
