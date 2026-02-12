"""Integration tests: translator -> merger -> serializer data flow."""

from datetime import timedelta
from unittest.mock import Mock, patch

import pytest

from bilingualsub.core.merger import merge_subtitles
from bilingualsub.core.subtitle import Subtitle
from bilingualsub.core.translator import translate_subtitle
from bilingualsub.formats.ass import serialize_bilingual_ass
from bilingualsub.formats.srt import parse_srt, serialize_srt


def _make_mock_agent(translated_texts: list[str]) -> Mock:
    """Create a mock Agent that returns batch translation response."""
    agent = Mock()
    batch_content = "\n".join(
        f"{i}. {text}" for i, text in enumerate(translated_texts, 1)
    )
    resp = Mock()
    resp.content = batch_content
    agent.run.return_value = resp
    return agent


@pytest.mark.integration
class TestTranslatorToMergerToSerializer:
    """Verify translator -> merger -> serializer data flow."""

    def test_translator_output_merges_and_serializes_to_srt(
        self,
        set_fake_api_key: None,
        sample_subtitle_3_entries: Subtitle,
    ) -> None:
        translated_texts = [
            "你好，這是一個測試。",
            "這是第二個字幕。",
            "這是第三個。",
        ]
        mock_agent = _make_mock_agent(translated_texts)

        with patch(
            "bilingualsub.core.translator.Agent",
            return_value=mock_agent,
        ):
            translated = translate_subtitle(sample_subtitle_3_entries)

        merged = merge_subtitles(
            sample_subtitle_3_entries.entries,
            translated.entries,
        )
        merged_sub = Subtitle(entries=merged)
        srt_str = serialize_srt(merged_sub)
        parsed = parse_srt(srt_str)

        assert len(parsed.entries) == 3

        for i, entry in enumerate(parsed.entries):
            orig = sample_subtitle_3_entries.entries[i]
            assert entry.start == orig.start
            assert entry.end == orig.end
            assert translated_texts[i] in entry.text
            assert orig.text in entry.text

    def test_translator_output_serializes_to_ass_with_metadata(
        self,
        set_fake_api_key: None,
        sample_subtitle_3_entries: Subtitle,
    ) -> None:
        translated_texts = [
            "你好，這是一個測試。",
            "這是第二個字幕。",
            "這是第三個。",
        ]
        mock_agent = _make_mock_agent(translated_texts)

        with patch(
            "bilingualsub.core.translator.Agent",
            return_value=mock_agent,
        ):
            translated = translate_subtitle(sample_subtitle_3_entries)

        ass_output = serialize_bilingual_ass(
            sample_subtitle_3_entries,
            translated,
            video_width=1920,
            video_height=1080,
        )

        assert "PlayResX: 1920" in ass_output
        assert "PlayResY: 1080" in ass_output
        assert "[Script Info]" in ass_output
        assert "[V4+ Styles]" in ass_output
        assert "[Events]" in ass_output

        dialogue_lines = [
            line for line in ass_output.splitlines() if line.startswith("Dialogue:")
        ]
        assert len(dialogue_lines) == 6

    def test_merged_entries_form_valid_subtitle_for_srt(
        self,
        sample_subtitle_3_entries: Subtitle,
        sample_translated_3_entries: Subtitle,
    ) -> None:
        merged = merge_subtitles(
            sample_subtitle_3_entries.entries,
            sample_translated_3_entries.entries,
        )
        merged_sub = Subtitle(entries=merged)
        srt_str = serialize_srt(merged_sub)

        for entry in sample_subtitle_3_entries.entries:
            assert entry.text in srt_str
        for entry in sample_translated_3_entries.entries:
            assert entry.text in srt_str

        assert "-->" in srt_str

    def test_merger_preserves_timing_through_srt_round_trip(
        self,
        sample_subtitle_3_entries: Subtitle,
        sample_translated_3_entries: Subtitle,
    ) -> None:
        merged = merge_subtitles(
            sample_subtitle_3_entries.entries,
            sample_translated_3_entries.entries,
        )
        merged_sub = Subtitle(entries=merged)
        srt_str = serialize_srt(merged_sub)
        parsed = parse_srt(srt_str)

        expected_timings = [
            (timedelta(seconds=1), timedelta(seconds=4)),
            (timedelta(seconds=5), timedelta(seconds=8)),
            (timedelta(seconds=9), timedelta(seconds=12)),
        ]

        for i, (start, end) in enumerate(expected_timings):
            assert parsed.entries[i].start == start
            assert parsed.entries[i].end == end
