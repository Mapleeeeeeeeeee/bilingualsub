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
