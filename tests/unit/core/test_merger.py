"""Tests for subtitle merger module."""

from datetime import timedelta

import pytest

from bilingualsub.core.merger import merge_subtitles
from bilingualsub.core.subtitle import SubtitleEntry


class TestMergeSubtitles:
    """Test merge_subtitles function."""

    def test_merge_basic(self):
        """Test basic merge with matching entries."""
        original = [
            SubtitleEntry(
                index=1, start=timedelta(0), end=timedelta(seconds=2), text="Hello"
            ),
            SubtitleEntry(
                index=2,
                start=timedelta(seconds=2.5),
                end=timedelta(seconds=4.5),
                text="World",
            ),
        ]
        translated = [
            SubtitleEntry(
                index=1, start=timedelta(0), end=timedelta(seconds=2), text="你好"
            ),
            SubtitleEntry(
                index=2,
                start=timedelta(seconds=2.5),
                end=timedelta(seconds=4.5),
                text="世界",
            ),
        ]

        result = merge_subtitles(original, translated)

        assert len(result) == 2
        assert result[0].text == "你好\nHello"
        assert result[0].start == timedelta(0)
        assert result[0].end == timedelta(seconds=2)
        assert result[0].index == 1

        assert result[1].text == "世界\nWorld"
        assert result[1].start == timedelta(seconds=2.5)
        assert result[1].end == timedelta(seconds=4.5)
        assert result[1].index == 2

    def test_uses_original_timing(self):
        """Test that original timing is used even when translated differs."""
        original = [
            SubtitleEntry(
                index=1,
                start=timedelta(seconds=1),
                end=timedelta(seconds=3),
                text="Original",
            ),
        ]
        translated = [
            SubtitleEntry(
                index=1,
                start=timedelta(seconds=1.1),
                end=timedelta(seconds=3.1),
                text="Translated",
            ),
        ]

        result = merge_subtitles(original, translated)

        # Should use original timing
        assert result[0].start == timedelta(seconds=1)
        assert result[0].end == timedelta(seconds=3)

    def test_uses_original_index(self):
        """Test that original index is used."""
        original = [
            SubtitleEntry(
                index=5,
                start=timedelta(seconds=1),
                end=timedelta(seconds=3),
                text="Original",
            ),
        ]
        translated = [
            SubtitleEntry(
                index=99,
                start=timedelta(seconds=1),
                end=timedelta(seconds=3),
                text="Translated",
            ),
        ]

        result = merge_subtitles(original, translated)

        # Should use original index
        assert result[0].index == 5

    def test_mismatch_count_more_original(self):
        """Test error when original has more entries."""
        original = [
            SubtitleEntry(
                index=1, start=timedelta(0), end=timedelta(seconds=2), text="One"
            ),
            SubtitleEntry(
                index=2,
                start=timedelta(seconds=2),
                end=timedelta(seconds=4),
                text="Two",
            ),
        ]
        translated = [
            SubtitleEntry(
                index=1, start=timedelta(0), end=timedelta(seconds=2), text="一"
            ),
        ]

        with pytest.raises(ValueError, match="Entry count mismatch.*2.*1"):
            merge_subtitles(original, translated)

    def test_mismatch_count_more_translated(self):
        """Test error when translated has more entries."""
        original = [
            SubtitleEntry(
                index=1, start=timedelta(0), end=timedelta(seconds=2), text="One"
            ),
        ]
        translated = [
            SubtitleEntry(
                index=1, start=timedelta(0), end=timedelta(seconds=2), text="一"
            ),
            SubtitleEntry(
                index=2, start=timedelta(seconds=2), end=timedelta(seconds=4), text="二"
            ),
        ]

        with pytest.raises(ValueError, match="Entry count mismatch.*1.*2"):
            merge_subtitles(original, translated)

    def test_empty_lists(self):
        """Test with empty input lists."""
        result = merge_subtitles([], [])
        assert result == []

    def test_matches_by_index_position(self):
        """Test that matching is by position, not by entry index field."""
        # Different index values but should match by position
        original = [
            SubtitleEntry(
                index=10, start=timedelta(0), end=timedelta(seconds=2), text="First"
            ),
            SubtitleEntry(
                index=20,
                start=timedelta(seconds=2),
                end=timedelta(seconds=4),
                text="Second",
            ),
        ]
        translated = [
            SubtitleEntry(
                index=1, start=timedelta(0), end=timedelta(seconds=2), text="第一"
            ),
            SubtitleEntry(
                index=2,
                start=timedelta(seconds=2),
                end=timedelta(seconds=4),
                text="第二",
            ),
        ]

        result = merge_subtitles(original, translated)

        # Position 0 matches position 0
        assert result[0].text == "第一\nFirst"
        assert result[0].index == 10

        # Position 1 matches position 1
        assert result[1].text == "第二\nSecond"
        assert result[1].index == 20

    def test_multiline_text(self):
        """Test with multiline text in entries."""
        original = [
            SubtitleEntry(
                index=1,
                start=timedelta(0),
                end=timedelta(seconds=2),
                text="Line 1\nLine 2",
            ),
        ]
        translated = [
            SubtitleEntry(
                index=1, start=timedelta(0), end=timedelta(seconds=2), text="行 1\n行 2"
            ),
        ]

        result = merge_subtitles(original, translated)

        # Should preserve multiline format
        assert result[0].text == "行 1\n行 2\nLine 1\nLine 2"

    def test_special_characters(self):
        """Test with special characters in text."""
        original = [
            SubtitleEntry(
                index=1,
                start=timedelta(0),
                end=timedelta(seconds=2),
                text="Hello, world! [music]",
            ),
        ]
        translated = [
            SubtitleEntry(
                index=1,
                start=timedelta(0),
                end=timedelta(seconds=2),
                text="你好，世界！[音樂]",
            ),
        ]

        result = merge_subtitles(original, translated)

        assert result[0].text == "你好，世界！[音樂]\nHello, world! [music]"

    def test_preserves_all_entries(self):
        """Test that all entries are preserved in correct order."""
        original = [
            SubtitleEntry(
                index=i,
                start=timedelta(seconds=i),
                end=timedelta(seconds=i + 1),
                text=f"Entry {i}",
            )
            for i in range(1, 6)
        ]
        translated = [
            SubtitleEntry(
                index=i,
                start=timedelta(seconds=i),
                end=timedelta(seconds=i + 1),
                text=f"條目 {i}",
            )
            for i in range(1, 6)
        ]

        result = merge_subtitles(original, translated)

        assert len(result) == 5
        for i, entry in enumerate(result, start=1):
            assert entry.index == i
            assert entry.text == f"條目 {i}\nEntry {i}"
            assert entry.start == timedelta(seconds=i)
            assert entry.end == timedelta(seconds=i + 1)

    def test_different_timing_values(self):
        """Test with various timing values including milliseconds."""
        original = [
            SubtitleEntry(
                index=1,
                start=timedelta(seconds=1, milliseconds=500),
                end=timedelta(seconds=3, milliseconds=250),
                text="Timing test",
            ),
        ]
        translated = [
            SubtitleEntry(
                index=1,
                start=timedelta(seconds=2),  # Different timing
                end=timedelta(seconds=4),  # Different timing
                text="時間測試",
            ),
        ]

        result = merge_subtitles(original, translated)

        # Should use original timing with milliseconds
        assert result[0].start == timedelta(seconds=1, milliseconds=500)
        assert result[0].end == timedelta(seconds=3, milliseconds=250)
        assert result[0].text == "時間測試\nTiming test"
