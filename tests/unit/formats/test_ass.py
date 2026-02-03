"""Unit tests for ASS serializer."""

from datetime import timedelta

import pytest

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.formats.ass import serialize_bilingual_ass


class TestSerializeBilingualASS:
    """Test cases for bilingual ASS serialization."""

    def test_serialize_single_entry(self):
        """Test serializing a single bilingual entry."""
        original = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=3),
                    text="Hello, world!",
                )
            ]
        )
        translated = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=3),
                    text="你好，世界！",
                )
            ]
        )

        result = serialize_bilingual_ass(
            original, translated, video_width=1920, video_height=1080
        )

        # Check header
        assert "[Script Info]" in result
        assert "Title: Bilingual Subtitle" in result
        assert "PlayResX: 1920" in result
        assert "PlayResY: 1080" in result

        # Check styles with fixed colors and margins
        assert "Style: Translated" in result
        assert "Style: Original" in result
        assert "&H0000FFFF" in result  # Yellow color
        assert "&H00000000" in result  # Black outline
        assert ",2,0,2,10,10,40," in result  # Translated MarginV=40
        assert ",2,0,2,10,10,10," in result  # Original MarginV=10

        # Check dialogue lines
        assert (
            "Dialogue: 0,0:00:01.00,0:00:03.00,Translated,,0,0,0,,你好，世界！"
            in result
        )
        assert (
            "Dialogue: 0,0:00:01.00,0:00:03.00,Original,,0,0,0,,Hello, world!" in result
        )

    def test_serialize_multiple_entries(self):
        """Test serializing multiple bilingual entries."""
        original = Subtitle(
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
        translated = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=3),
                    text="第一",
                ),
                SubtitleEntry(
                    index=2,
                    start=timedelta(seconds=4, milliseconds=500),
                    end=timedelta(seconds=6, milliseconds=500),
                    text="第二",
                ),
            ]
        )

        result = serialize_bilingual_ass(
            original, translated, video_width=1280, video_height=720
        )

        # Check both dialogue pairs exist
        assert "Dialogue: 0,0:00:01.00,0:00:03.00,Translated,,0,0,0,,第一" in result
        assert "Dialogue: 0,0:00:01.00,0:00:03.00,Original,,0,0,0,,First" in result
        assert "Dialogue: 0,0:00:04.50,0:00:06.50,Translated,,0,0,0,,第二" in result
        assert "Dialogue: 0,0:00:04.50,0:00:06.50,Original,,0,0,0,,Second" in result

    def test_serialize_multiline_text(self):
        """Test serializing entry with multiline text."""
        original = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=3),
                    text="Line one\nLine two",
                )
            ]
        )
        translated = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=3),
                    text="第一行\n第二行",
                )
            ]
        )

        result = serialize_bilingual_ass(
            original, translated, video_width=1920, video_height=1080
        )

        # Check newlines are converted to \N
        assert (
            "Dialogue: 0,0:00:01.00,0:00:03.00,Translated,,0,0,0,,第一行\\N第二行"
            in result
        )
        assert (
            "Dialogue: 0,0:00:01.00,0:00:03.00,Original,,0,0,0,,Line one\\NLine two"
            in result
        )

    def test_serialize_with_milliseconds(self):
        """Test serializing with precise millisecond timing (centiseconds in ASS)."""
        original = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(milliseconds=10),
                    end=timedelta(milliseconds=990),
                    text="Short",
                )
            ]
        )
        translated = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(milliseconds=10),
                    end=timedelta(milliseconds=990),
                    text="短",
                )
            ]
        )

        result = serialize_bilingual_ass(
            original, translated, video_width=1920, video_height=1080
        )

        # Check centisecond precision (10ms = 1cs, 990ms = 99cs)
        assert "Dialogue: 0,0:00:00.01,0:00:00.99,Translated,,0,0,0,,短" in result
        assert "Dialogue: 0,0:00:00.01,0:00:00.99,Original,,0,0,0,,Short" in result

    def test_serialize_with_hours(self):
        """Test serializing with hour values."""
        original = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(hours=1, minutes=30, seconds=45, milliseconds=120),
                    end=timedelta(hours=2, minutes=45, seconds=30, milliseconds=450),
                    text="Long duration",
                )
            ]
        )
        translated = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(hours=1, minutes=30, seconds=45, milliseconds=120),
                    end=timedelta(hours=2, minutes=45, seconds=30, milliseconds=450),
                    text="長時間",
                )
            ]
        )

        result = serialize_bilingual_ass(
            original, translated, video_width=1920, video_height=1080
        )

        # Check hour format (120ms = 12cs, 450ms = 45cs)
        assert "Dialogue: 0,1:30:45.12,2:45:30.45,Translated,,0,0,0,,長時間" in result
        assert (
            "Dialogue: 0,1:30:45.12,2:45:30.45,Original,,0,0,0,,Long duration" in result
        )

    def test_serialize_different_video_resolutions(self):
        """Test that video resolution affects PlayRes values."""
        original = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=2),
                    text="Test",
                )
            ]
        )
        translated = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=2),
                    text="测试",
                )
            ]
        )

        # Test 1080p
        result_1080p = serialize_bilingual_ass(
            original, translated, video_width=1920, video_height=1080
        )
        assert "PlayResX: 1920" in result_1080p
        assert "PlayResY: 1080" in result_1080p

        # Test 720p
        result_720p = serialize_bilingual_ass(
            original, translated, video_width=1280, video_height=720
        )
        assert "PlayResX: 1280" in result_720p
        assert "PlayResY: 720" in result_720p

        # Test 4K
        result_4k = serialize_bilingual_ass(
            original, translated, video_width=3840, video_height=2160
        )
        assert "PlayResX: 3840" in result_4k
        assert "PlayResY: 2160" in result_4k

    def test_serialize_mismatched_entry_counts_raises_error(self):
        """Test that mismatched entry counts raise error."""
        original = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=2),
                    text="First",
                )
            ]
        )
        translated = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=2),
                    text="第一",
                ),
                SubtitleEntry(
                    index=2,
                    start=timedelta(seconds=3),
                    end=timedelta(seconds=4),
                    text="第二",
                ),
            ]
        )

        with pytest.raises(
            ValueError,
            match="Original and translated subtitles must have same number of entries",
        ):
            serialize_bilingual_ass(
                original, translated, video_width=1920, video_height=1080
            )

    def test_serialize_fixed_outline_width(self):
        """Test that outline width is fixed at 2."""
        original = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=2),
                    text="Test",
                )
            ]
        )
        translated = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=2),
                    text="测试",
                )
            ]
        )

        result = serialize_bilingual_ass(
            original, translated, video_width=1920, video_height=1080
        )

        # Check Outline=2 in both styles (appears before alignment value 2)
        # Format: ...BorderStyle, Outline, Shadow, Alignment...
        # Expected: ...1,2,0,2,...
        assert ",1,2,0,2," in result

    @pytest.mark.unit
    def test_serialize_over_24_hours_when_given_long_video(self):
        """Given subtitle with > 24 hour duration, when serializing, then output correct timing."""
        original = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(hours=25, minutes=30, seconds=15, milliseconds=500),
                    end=timedelta(hours=26, minutes=45, seconds=30, milliseconds=120),
                    text="Very long video",
                )
            ]
        )
        translated = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(hours=25, minutes=30, seconds=15, milliseconds=500),
                    end=timedelta(hours=26, minutes=45, seconds=30, milliseconds=120),
                    text="超长视频",
                )
            ]
        )

        result = serialize_bilingual_ass(
            original, translated, video_width=1920, video_height=1080
        )

        # Check that hours > 24 are handled correctly (500ms = 50cs, 120ms = 12cs)
        assert (
            "Dialogue: 0,25:30:15.50,26:45:30.12,Translated,,0,0,0,,超长视频" in result
        )
        assert (
            "Dialogue: 0,25:30:15.50,26:45:30.12,Original,,0,0,0,,Very long video"
            in result
        )

    @pytest.mark.unit
    def test_serialize_escapes_special_ass_characters(self):
        """Test that ASS special characters are properly escaped."""
        original = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=3),
                    text="Text with {override} and \\backslash",
                )
            ]
        )
        translated = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=3),
                    text="包含{覆蓋}和\\反斜線",
                )
            ]
        )

        result = serialize_bilingual_ass(
            original, translated, video_width=1920, video_height=1080
        )

        # Check that curly braces and backslashes are escaped
        assert "\\{override\\}" in result
        assert "\\\\backslash" in result
        assert "\\{覆蓋\\}" in result
        assert "\\\\反斜線" in result
