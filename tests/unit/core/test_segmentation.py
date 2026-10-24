"""Behavior checks for conservative phrase segmentation."""

from datetime import timedelta
from itertools import pairwise

import pytest

from bilingualsub.core.segmentation import split_at_phrase_boundaries
from bilingualsub.core.subtitle import SubtitleEntry


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Our carefully calibrated coefficient 3.14 provides stable numerical behavior throughout repeated measurements",
            [
                "Our carefully calibrated coefficient 3.14 provides stable numerical behavior throughout repeated measurements"
            ],
        ),
        (
            "I worked very hard on establishing the deterministic tools that each agent would use",
            [
                "I worked very hard on establishing the deterministic tools",
                "that each agent would use",
            ],
        ),
        (
            "We carefully establish deterministic tools for every individual automated agent",
            [
                "We carefully establish deterministic tools for every individual automated agent"
            ],
        ),
        (
            "We verify all the results and keep the application running safely",
            ["We verify all the results", "and keep the application running safely"],
        ),
    ],
)
def test_given_long_source_cue_only_phrase_boundaries_split(
    text: str, expected: list[str]
) -> None:
    """Regression: portrait limits separate deterministic from tools (6e50ae3)."""
    source = SubtitleEntry(1, timedelta(seconds=2), timedelta(seconds=10), text)
    result = split_at_phrase_boundaries([source], max_duration_sec=4, max_chars=60)
    assert [entry.text for entry in result] == expected
    assert result[0].start == source.start
    assert result[-1].end == source.end
    assert " ".join(entry.text for entry in result) == text
    assert all(left.end == right.start for left, right in pairwise(result))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "我們在設計系統架構的時候，必須清楚描述請求如何在各模組間流轉",
            [
                "我們在設計系統架構的時候，",
                "必須清楚描述請求如何在各模組間流轉",
            ],
        ),
        (
            "第一階段的任務已經順利完成了。接下來我們將進入第二階段的系統部署",
            [
                "第一階段的任務已經順利完成了。",
                "接下來我們將進入第二階段的系統部署",
            ],
        ),
        (
            "你好，這是一段簡短的說明",
            ["你好，這是一段簡短的說明"],
        ),
        (
            "這是一段稍微長一點的說明文字但是完全沒有標點符號所以不應該切分",
            ["這是一段稍微長一點的說明文字但是完全沒有標點符號所以不應該切分"],
        ),
    ],
)
def test_given_cjk_source_cue_splits_at_punctuation_boundaries(
    text: str, expected: list[str]
) -> None:
    """Regression: CJK punctuation boundaries should split long cues (6e50ae3)."""
    source = SubtitleEntry(1, timedelta(seconds=2), timedelta(seconds=10), text)
    result = split_at_phrase_boundaries([source], max_duration_sec=4, max_chars=20)
    assert [entry.text for entry in result] == expected
    assert result[0].start == source.start
    assert result[-1].end == source.end
    assert "".join(entry.text for entry in result) == text
    assert all(left.end == right.start for left, right in pairwise(result))


@pytest.mark.unit
def test_given_empty_entries_returns_empty_list() -> None:
    """Empty entry list should return an empty list without error."""
    assert split_at_phrase_boundaries([], max_duration_sec=4, max_chars=60) == []


@pytest.mark.unit
def test_given_multiple_entries_preserves_sequential_indices_and_boundaries() -> None:
    """Multiple sequential entries re-index smoothly and maintain boundary timing."""
    entries = [
        SubtitleEntry(1, timedelta(seconds=0), timedelta(seconds=2), "First short cue"),
        SubtitleEntry(
            2,
            timedelta(seconds=3),
            timedelta(seconds=11),
            "I worked very hard on establishing the deterministic tools that each agent would use",
        ),
        SubtitleEntry(
            3, timedelta(seconds=12), timedelta(seconds=14), "Final short cue"
        ),
    ]
    result = split_at_phrase_boundaries(entries, max_duration_sec=4, max_chars=60)
    assert len(result) == 4
    assert [entry.index for entry in result] == [1, 2, 3, 4]
    assert result[0].text == "First short cue"
    assert result[-1].text == "Final short cue"
