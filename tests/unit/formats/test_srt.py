"""Unit tests for SRT parser and serializer."""

from datetime import timedelta

import pytest

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.formats.srt import SRTParseError, parse_srt, serialize_srt


class TestParseSRT:
    """Test cases for SRT parsing."""

    def test_parse_valid_single_entry(self):
        """Test parsing a valid single entry SRT."""
        content = """1
00:00:01,000 --> 00:00:03,000
Hello, world!
"""
        result = parse_srt(content)

        assert len(result) == 1
        assert result[0].index == 1
        assert result[0].start == timedelta(seconds=1)
        assert result[0].end == timedelta(seconds=3)
        assert result[0].text == "Hello, world!"

    def test_parse_valid_multiple_entries(self):
        """Test parsing multiple entries."""
        content = """1
00:00:01,000 --> 00:00:03,000
First subtitle

2
00:00:04,500 --> 00:00:06,500
Second subtitle
"""
        result = parse_srt(content)

        assert len(result) == 2
        assert result[0].text == "First subtitle"
        assert result[1].text == "Second subtitle"

    def test_parse_multiline_text(self):
        """Test parsing entry with multiline text."""
        content = """1
00:00:01,000 --> 00:00:03,000
Line one
Line two
Line three
"""
        result = parse_srt(content)

        assert len(result) == 1
        assert result[0].text == "Line one\nLine two\nLine three"

    def test_parse_with_extra_whitespace(self):
        """Test parsing with extra blank lines and whitespace."""
        content = """

1
00:00:01,000 --> 00:00:03,000
Hello



2
00:00:04,000 --> 00:00:05,000
World

"""
        result = parse_srt(content)

        assert len(result) == 2
        assert result[0].text == "Hello"
        assert result[1].text == "World"

    def test_parse_with_various_timing_formats(self):
        """Test parsing with different timing values."""
        content = """1
00:00:00,001 --> 00:00:00,999
Milliseconds test

2
01:30:45,123 --> 02:45:30,456
Hour test
"""
        result = parse_srt(content)

        assert len(result) == 2
        assert result[0].start == timedelta(milliseconds=1)
        assert result[0].end == timedelta(milliseconds=999)
        assert result[1].start == timedelta(
            hours=1, minutes=30, seconds=45, milliseconds=123
        )
        assert result[1].end == timedelta(
            hours=2, minutes=45, seconds=30, milliseconds=456
        )

    def test_parse_empty_content_raises_error(self):
        """Test that empty content raises error."""
        with pytest.raises(SRTParseError, match="Content cannot be empty"):
            parse_srt("")

        with pytest.raises(SRTParseError, match="Content cannot be empty"):
            parse_srt("   \n\n  ")

    def test_parse_missing_lines_raises_error(self):
        """Test that blocks with missing lines raise error."""
        content = """1
00:00:01,000 --> 00:00:03,000
"""
        with pytest.raises(
            SRTParseError, match="Block 1: Invalid format, expected at least 3 lines"
        ):
            parse_srt(content)

    def test_parse_invalid_index_raises_error(self):
        """Test that invalid index raises error."""
        content = """abc
00:00:01,000 --> 00:00:03,000
Text
"""
        with pytest.raises(SRTParseError, match="Block 1: Invalid index 'abc'"):
            parse_srt(content)

    def test_parse_invalid_timing_format_raises_error(self):
        """Test that invalid timing format raises error."""
        content = """1
00:00:01 -> 00:00:03
Text
"""
        with pytest.raises(SRTParseError, match="Block 1: Invalid timing format"):
            parse_srt(content)

        content = """1
invalid timing
Text
"""
        with pytest.raises(SRTParseError, match="Block 1: Invalid timing format"):
            parse_srt(content)

    def test_parse_empty_text_raises_error(self):
        """Test that empty text raises error."""
        content = """1
00:00:01,000 --> 00:00:03,000

"""
        with pytest.raises(
            SRTParseError, match="Block 1: Invalid format, expected at least 3 lines"
        ):
            parse_srt(content)

    def test_parse_start_after_end_raises_error(self):
        """Test that start time after end time raises error."""
        content = """1
00:00:05,000 --> 00:00:03,000
Text
"""
        with pytest.raises(
            SRTParseError, match="Block 1: Start time.*must be before end time"
        ):
            parse_srt(content)

    def test_parse_non_sequential_indices_raises_error(self):
        """Test that non-sequential indices raise error."""
        content = """1
00:00:01,000 --> 00:00:02,000
First

3
00:00:03,000 --> 00:00:04,000
Third
"""
        with pytest.raises(
            SRTParseError,
            match="Invalid subtitle structure.*indices must be sequential",
        ):
            parse_srt(content)

    def test_parse_overlapping_times_raises_error(self):
        """Test that overlapping time ranges raise error."""
        content = """1
00:00:01,000 --> 00:00:05,000
First

2
00:00:03,000 --> 00:00:06,000
Second
"""
        with pytest.raises(
            SRTParseError, match="Invalid subtitle structure.*Overlapping"
        ):
            parse_srt(content)


class TestSerializeSRT:
    """Test cases for SRT serialization."""

    def test_serialize_single_entry(self):
        """Test serializing a single entry."""
        subtitle = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=3),
                    text="Hello, world!",
                )
            ]
        )

        result = serialize_srt(subtitle)

        expected = """1
00:00:01,000 --> 00:00:03,000
Hello, world!
"""
        assert result == expected

    def test_serialize_multiple_entries(self):
        """Test serializing multiple entries."""
        subtitle = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=3),
                    text="First",
                ),
                SubtitleEntry(
                    index=2,
                    start=timedelta(seconds=4, milliseconds=500),
                    end=timedelta(seconds=6, milliseconds=500),
                    text="Second",
                ),
            ]
        )

        result = serialize_srt(subtitle)

        expected = """1
00:00:01,000 --> 00:00:03,000
First

2
00:00:04,500 --> 00:00:06,500
Second
"""
        assert result == expected

    def test_serialize_multiline_text(self):
        """Test serializing entry with multiline text."""
        subtitle = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=3),
                    text="Line one\nLine two\nLine three",
                )
            ]
        )

        result = serialize_srt(subtitle)

        expected = """1
00:00:01,000 --> 00:00:03,000
Line one
Line two
Line three
"""
        assert result == expected

    def test_serialize_with_milliseconds(self):
        """Test serializing with precise millisecond timing."""
        subtitle = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(milliseconds=1),
                    end=timedelta(milliseconds=999),
                    text="Short",
                )
            ]
        )

        result = serialize_srt(subtitle)

        expected = """1
00:00:00,001 --> 00:00:00,999
Short
"""
        assert result == expected

    def test_serialize_with_hours(self):
        """Test serializing with hour values."""
        subtitle = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(hours=1, minutes=30, seconds=45, milliseconds=123),
                    end=timedelta(hours=2, minutes=45, seconds=30, milliseconds=456),
                    text="Long duration",
                )
            ]
        )

        result = serialize_srt(subtitle)

        expected = """1
01:30:45,123 --> 02:45:30,456
Long duration
"""
        assert result == expected

    @pytest.mark.unit
    def test_serialize_should_handle_duration_over_24_hours_when_given_long_video(
        self,
    ):
        """Given subtitle with > 24 hour duration, when serializing, then output correct timing."""
        subtitle = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(hours=25, minutes=30, seconds=15, milliseconds=500),
                    end=timedelta(hours=26, minutes=45, seconds=30, milliseconds=123),
                    text="Very long video",
                )
            ]
        )

        result = serialize_srt(subtitle)

        expected = """1
25:30:15,500 --> 26:45:30,123
Very long video
"""
        assert result == expected


class TestRoundTrip:
    """Test round-trip parsing and serialization."""

    def test_roundtrip_preserves_data(self):
        """Test that parse -> serialize -> parse preserves data."""
        original_content = """1
00:00:01,000 --> 00:00:03,000
Hello, world!

2
00:00:04,500 --> 00:00:06,500
Goodbye!
"""
        subtitle = parse_srt(original_content)
        serialized = serialize_srt(subtitle)
        reparsed = parse_srt(serialized)

        assert len(reparsed) == 2
        assert reparsed[0].index == 1
        assert reparsed[0].text == "Hello, world!"
        assert reparsed[1].index == 2
        assert reparsed[1].text == "Goodbye!"

    def test_roundtrip_multiline(self):
        """Test round-trip with multiline text."""
        original = """1
00:00:01,000 --> 00:00:03,000
Line 1
Line 2
Line 3
"""
        subtitle = parse_srt(original)
        serialized = serialize_srt(subtitle)
        reparsed = parse_srt(serialized)

        assert reparsed[0].text == "Line 1\nLine 2\nLine 3"
