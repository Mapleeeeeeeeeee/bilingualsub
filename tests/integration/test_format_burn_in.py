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

        # Mock ffmpeg module to avoid real ffmpeg execution
        with patch("bilingualsub.utils.ffmpeg.ffmpeg") as mock_ffmpeg:
            mock_stream = MagicMock()
            mock_ffmpeg.input.return_value = mock_stream
            mock_stream.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream
            mock_stream.run.return_value = None

            result = burn_subtitles(video_path, srt_path, output_path)

        # Verify burn_subtitles accepted the SRT file
        assert result == output_path
        mock_ffmpeg.input.assert_called_once()
        mock_stream.output.assert_called_once()
        call_kwargs = mock_stream.output.call_args
        assert "subtitles=" in call_kwargs[1]["vf"]

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

        # Mock ffmpeg module to avoid real ffmpeg execution
        with patch("bilingualsub.utils.ffmpeg.ffmpeg") as mock_ffmpeg:
            mock_stream = MagicMock()
            mock_ffmpeg.input.return_value = mock_stream
            mock_stream.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream
            mock_stream.run.return_value = None

            result = burn_subtitles(video_path, ass_path, output_path)

        # Verify burn_subtitles accepted the ASS file
        assert result == output_path
        mock_ffmpeg.input.assert_called_once()
        mock_stream.output.assert_called_once()
        call_kwargs = mock_stream.output.call_args
        assert "ass=" in call_kwargs[1]["vf"]

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
