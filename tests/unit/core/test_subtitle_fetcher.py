"""Tests for subtitle_fetcher VTT-to-SRT conversion."""

import pytest

from bilingualsub.core.subtitle_fetcher import vtt_to_srt


@pytest.mark.unit
class TestVttToSrt:
    def test_basic_vtt_conversion(self):
        vtt = """WEBVTT

1
00:00:01.000 --> 00:00:04.000
Hello world

2
00:00:05.000 --> 00:00:08.000
Second line"""
        srt = vtt_to_srt(vtt)
        assert "00:00:01,000 --> 00:00:04,000" in srt
        assert "Hello world" in srt
        assert "00:00:05,000 --> 00:00:08,000" in srt
        assert "Second line" in srt

    def test_hour_padding_for_mm_ss_timestamps(self):
        vtt = """WEBVTT

01:30.000 --> 02:00.000
Short timestamp"""
        srt = vtt_to_srt(vtt)
        assert "00:01:30,000 --> 00:02:00,000" in srt

    def test_strips_vtt_tags(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:04.000
<c>Tagged</c> <b>text</b>"""
        srt = vtt_to_srt(vtt)
        assert "Tagged text" in srt
        assert "<c>" not in srt
        assert "<b>" not in srt

    def test_renumbers_blocks(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
First

00:00:03.000 --> 00:00:04.000
Second"""
        srt = vtt_to_srt(vtt)
        lines = srt.strip().split("\n")
        assert lines[0] == "1"
        # Find second block number
        block_nums = [line for line in lines if line.strip().isdigit()]
        assert block_nums == ["1", "2"]
