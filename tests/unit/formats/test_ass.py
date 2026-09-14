"""Unit tests for ASS serializer."""

import re
from datetime import timedelta

import pytest

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.formats.ass import serialize_bilingual_ass


def _dialogue_position(result: str, style: str) -> tuple[int, int, int]:
    match = re.search(
        rf"Dialogue: 0,[^,]+,[^,]+,{style},,0,0,0,,"
        rf"\{{\\an8\\pos\((\d+),(\d+)\)\\fs(\d+)\\q2\}}",
        result,
    )
    assert match is not None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


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

        # Check styles with fixed colors and dynamic top-anchored layout.
        assert "Style: Translated" in result
        assert "Style: Original" in result
        assert "&H0000FFFF" in result  # Yellow color
        assert "&H00000000" in result  # Black outline
        assert ",3,0,8,60,60,0," in result  # Translated top-aligned
        assert ",2,0,8,60,60,0," in result  # Original top-aligned

        # Check dialogue lines
        assert (
            "Dialogue: 0,0:00:01.00,0:00:03.00,Translated,,0,0,0,,"
            "{\\an8\\pos(960,898)\\fs46\\q2}你好，世界！" in result
        )
        assert (
            "Dialogue: 0,0:00:01.00,0:00:03.00,Original,,0,0,0,,"
            "{\\an8\\pos(960,967)\\fs26\\q2}Hello, world!" in result
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
        assert "Dialogue: 0,0:00:01.00,0:00:03.00,Translated" in result
        assert "{\\an8\\pos(960,898)\\fs46\\q2}第一" in result
        assert "{\\an8\\pos(960,967)\\fs26\\q2}First" in result
        assert "Dialogue: 0,0:00:04.50,0:00:06.50,Translated" in result
        assert "{\\an8\\pos(960,898)\\fs46\\q2}第二" in result
        assert "{\\an8\\pos(960,967)\\fs26\\q2}Second" in result

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
            "Dialogue: 0,0:00:01.00,0:00:03.00,Translated,,0,0,0,,"
            "{\\an8\\pos(960,813)\\fs46\\q2}第一行\\N第二行" in result
        )
        assert (
            "Dialogue: 0,0:00:01.00,0:00:03.00,Original,,0,0,0,,"
            "{\\an8\\pos(960,936)\\fs26\\q2}Line one\\NLine two" in result
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
        assert "{\\an8\\pos(960,898)\\fs46\\q2}短" in result
        assert "{\\an8\\pos(960,967)\\fs26\\q2}Short" in result

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
        assert "Dialogue: 0,1:30:45.12,2:45:30.45,Translated" in result
        assert "{\\an8\\pos(960,898)\\fs46\\q2}長時間" in result
        assert "Dialogue: 0,1:30:45.12,2:45:30.45,Original" in result
        assert "{\\an8\\pos(960,967)\\fs26\\q2}Long duration" in result

    def test_serialize_preserves_landscape_playres_at_different_resolutions(self):
        """16:9 video keeps the established 1920x1080 subtitle canvas."""
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

        # Test 720p input -> still 1920x1080 PlayRes
        result_720p = serialize_bilingual_ass(
            original, translated, video_width=1280, video_height=720
        )
        assert "PlayResX: 1920" in result_720p
        assert "PlayResY: 1080" in result_720p

        # Test 4K input -> still 1920x1080 PlayRes
        result_4k = serialize_bilingual_ass(
            original, translated, video_width=3840, video_height=2160
        )
        assert "PlayResX: 1920" in result_4k
        assert "PlayResY: 1080" in result_4k

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

    def test_serialize_uses_translation_first_visual_hierarchy(self):
        """Translated line should be larger and brighter than the original line."""
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

        assert (
            "Style: Translated,Arial,46,"
            "&H0000FFFF,&H0000FFFF,&H00000000,&H00000000,"
            "0,0,0,0,100,100,0,0,1,3,0,8,60,60,0,1"
        ) in result
        assert (
            "Style: Original,Arial,26,"
            "&H00909090,&H00909090,&H00000000,&H00000000,"
            "0,0,0,0,100,100,0,0,1,2,0,8,60,60,0,1"
        ) in result

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
        assert "Dialogue: 0,25:30:15.50,26:45:30.12,Translated" in result
        assert "{\\an8\\pos(960,898)\\fs46\\q2}超长视频" in result
        assert "Dialogue: 0,25:30:15.50,26:45:30.12,Original" in result
        assert "{\\an8\\pos(960,967)\\fs26\\q2}Very long video" in result

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

    @pytest.mark.unit
    def test_serialize_wraps_long_original_below_translated_line(self):
        """Long original text wraps downward instead of pushing above translation."""
        original = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=3),
                    text=(
                        "It can be an architecture diagram drawn from the actual "
                        "codebase, a walkthrough of how a request moves through it, "
                        "or a dashboard of the data that a session had already pulled."
                    ),
                )
            ]
        )
        translated = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=3),
                    text="也可以是依實際程式碼產生的架構圖、請求流向說明，或是已抓取資料的儀表板。",
                )
            ]
        )

        result = serialize_bilingual_ass(
            original, translated, video_width=1920, video_height=1080
        )

        assert "{\\an8\\pos(960,867)\\fs46\\q2}" in result
        assert "{\\an8\\pos(960,936)\\fs26\\q2}" in result
        assert "actual codebase, a walkthrough" in result
        assert "\\Ndashboard of the data" in result

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("original_text", "expected_original_lines"),
        [
            ("A short original line.", 1),
            (
                "It can be an architecture diagram drawn from the actual codebase, "
                "a walkthrough of how a request moves through it, or a dashboard "
                "of the data that a session had already pulled.",
                2,
            ),
            (
                "This is a deliberately longer original subtitle used to exercise "
                "the dynamic bilingual layout when English wraps across three lines "
                "while the translated line remains readable and visually grouped "
                "with the original reference text below it, including additional "
                "details that force another wrap without requiring an unrealistic "
                "font size or a narrow subtitle region.",
                3,
            ),
        ],
    )
    def test_serialize_keeps_multiline_original_below_translation(
        self, original_text: str, expected_original_lines: int
    ):
        """Original text with 1-3 lines stays below the translated subtitle."""
        original = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=3),
                    text=original_text,
                )
            ]
        )
        translated = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=3),
                    text="這是用來驗證雙語字幕動態排版的翻譯文字。",
                )
            ]
        )

        result = serialize_bilingual_ass(
            original, translated, video_width=1920, video_height=1080
        )

        _, translated_y, translated_size = _dialogue_position(result, "Translated")
        _, original_y, original_size = _dialogue_position(result, "Original")
        original_dialogue = next(
            line for line in result.splitlines() if ",Original," in line
        )

        assert original_dialogue.count("\\N") + 1 == expected_original_lines
        assert original_y > translated_y + translated_size
        assert original_y + expected_original_lines * original_size <= 1080 - 30


@pytest.fixture
def long_bilingual_pair() -> tuple[Subtitle, Subtitle]:
    def subtitle(text: str) -> Subtitle:
        return Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(seconds=1),
                    end=timedelta(seconds=5),
                    text=text,
                )
            ]
        )

    return (
        subtitle(
            "When we explain software architecture, we should describe how a "
            "request moves through the system and why each component exists, "
            "so the next person can understand the decisions behind the code."
        ),
        subtitle(
            "說明軟體架構時，我們應該描述請求如何經過系統，以及每個元件存在的原因，"
            "讓下一位維護者能夠理解程式碼背後的設計決策。"
        ),
    )


def _canvas_size(result: str) -> tuple[int, int]:
    width = re.search(r"^PlayResX: (\d+)$", result, re.MULTILINE)
    height = re.search(r"^PlayResY: (\d+)$", result, re.MULTILINE)
    assert width is not None and height is not None
    return int(width.group(1)), int(height.group(1))


def _dialogue_text(result: str, style: str) -> str:
    dialogue = next(
        line
        for line in result.splitlines()
        if line.startswith("Dialogue:") and line.split(",", 9)[3] == style
    )
    return dialogue.split(",", 9)[9].split("}", 1)[1]


@pytest.mark.unit
@pytest.mark.parametrize("style", ["Translated", "Original"])
def test_given_portrait_video_long_subtitles_wrap_more_than_landscape(
    long_bilingual_pair: tuple[Subtitle, Subtitle], style: str
) -> None:
    """Regression: portrait videos reuse landscape subtitle wrapping (68ce84f)."""
    landscape = serialize_bilingual_ass(
        *long_bilingual_pair, video_width=1920, video_height=1080
    )
    portrait = serialize_bilingual_ass(
        *long_bilingual_pair, video_width=720, video_height=1280
    )

    assert _dialogue_text(portrait, style).count(r"\N") > _dialogue_text(
        landscape, style
    ).count(r"\N")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("video_width", "video_height"),
    [(720, 1280), (1080, 1920), (1080, 1080), (1440, 1080), (1920, 1080)],
)
def test_given_video_shape_subtitles_keep_proportions_and_centered_complete_pair(
    long_bilingual_pair: tuple[Subtitle, Subtitle],
    video_width: int,
    video_height: int,
) -> None:
    """Regression: subtitle canvas ignores portrait and square video shape (68ce84f)."""
    result = serialize_bilingual_ass(
        *long_bilingual_pair, video_width=video_width, video_height=video_height
    )
    canvas_width, canvas_height = _canvas_size(result)
    assert canvas_width == pytest.approx(
        canvas_height * video_width / video_height, abs=1
    )

    for style, subtitle in zip(
        ("Original", "Translated"), long_bilingual_pair, strict=True
    ):
        x, y, font_size = _dialogue_position(result, style)
        assert x == pytest.approx(canvas_width / 2, abs=1)
        text = _dialogue_text(result, style)
        assert "".join(text.replace(r"\N", " ").split()) == "".join(
            subtitle.entries[0].text.split()
        )
        assert 0 <= y < canvas_height
        assert y + (text.count(r"\N") + 1) * font_size < canvas_height

    _, translated_y, translated_size = _dialogue_position(result, "Translated")
    _, original_y, _ = _dialogue_position(result, "Original")
    translated_lines = _dialogue_text(result, "Translated").count(r"\N") + 1
    assert translated_y + translated_lines * translated_size < original_y


@pytest.mark.unit
@pytest.mark.parametrize(
    ("first_size", "second_size"),
    [((720, 1280), (1080, 1920)), ((1280, 720), (3840, 2160))],
)
def test_given_same_aspect_ratio_resolution_does_not_change_subtitle_layout(
    long_bilingual_pair: tuple[Subtitle, Subtitle],
    first_size: tuple[int, int],
    second_size: tuple[int, int],
) -> None:
    """Equivalent video shapes retain matching line breaks and visual placement."""
    first = serialize_bilingual_ass(
        *long_bilingual_pair, video_width=first_size[0], video_height=first_size[1]
    )
    second = serialize_bilingual_ass(
        *long_bilingual_pair, video_width=second_size[0], video_height=second_size[1]
    )
    first_width, first_height = _canvas_size(first)
    second_width, second_height = _canvas_size(second)
    for style in ("Translated", "Original"):
        assert _dialogue_text(first, style) == _dialogue_text(second, style)
        first_x, first_y, first_font = _dialogue_position(first, style)
        second_x, second_y, second_font = _dialogue_position(second, style)
        assert first_x / first_width == pytest.approx(second_x / second_width)
        assert first_y / first_height == pytest.approx(second_y / second_height)
        assert first_font / first_height == pytest.approx(second_font / second_height)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("video_width", "video_height"),
    [(0, 1080), (-1, 1080), (1920, 0), (1920, -1), (0, 0)],
)
def test_given_nonpositive_video_dimension_serialization_raises_value_error(
    long_bilingual_pair: tuple[Subtitle, Subtitle],
    video_width: int,
    video_height: int,
) -> None:
    """Video dimensions must be positive before a subtitle canvas can be created."""
    with pytest.raises(ValueError, match="Video dimensions must be positive"):
        serialize_bilingual_ass(
            *long_bilingual_pair, video_width=video_width, video_height=video_height
        )
