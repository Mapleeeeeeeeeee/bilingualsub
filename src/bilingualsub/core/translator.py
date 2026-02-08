"""LLM-based subtitle translation using Agno + Ollama."""

import logging
import re
from collections.abc import Callable

from agno.agent import Agent
from agno.models.ollama import Ollama

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry

logger = logging.getLogger(__name__)

_BATCH_SIZE = 10


class TranslationError(Exception):
    """Raised when translation fails."""


def _parse_batch_response(response_text: str, expected_count: int) -> list[str]:
    """Parse numbered batch translation response into a list of translated strings.

    Args:
        response_text: Raw response text with numbered lines like "1. translated text"
        expected_count: Expected number of translations

    Returns:
        List of translated strings in order

    Raises:
        TranslationError: If parsing fails or count doesn't match
    """
    pattern = re.compile(r"^\s*(\d+)\s*[.):\uff0e]\s*(.+)$")
    translations: dict[int, str] = {}

    for line in response_text.strip().splitlines():
        match = pattern.match(line)
        if match:
            num = int(match.group(1))
            text = match.group(2).strip()
            translations[num] = text

    if len(translations) != expected_count:
        raise TranslationError(
            f"Expected {expected_count} translations, got {len(translations)}"
        )

    result = []
    for i in range(1, expected_count + 1):
        if i not in translations:
            raise TranslationError(f"Missing translation for line {i}")
        result.append(translations[i])

    return result


def _translate_batch(
    translator: Agent,
    batch: list[SubtitleEntry],
    source_lang: str,
    target_lang: str,
) -> list[str]:
    """Translate a batch of subtitle entries in a single API call.

    Args:
        translator: Agno Agent instance
        batch: List of SubtitleEntry to translate
        source_lang: Source language code
        target_lang: Target language code

    Returns:
        List of translated strings

    Raises:
        TranslationError: If batch translation or parsing fails
    """
    numbered_lines = "\n".join(f"{i}. {entry.text}" for i, entry in enumerate(batch, 1))
    prompt = (
        f"將以下編號字幕從{source_lang}翻譯成{target_lang}。\n"
        f"只回傳編號翻譯，每行一條，編號與原文一致。\n\n"  # noqa: RUF001
        f"{numbered_lines}"
    )

    response = translator.run(prompt)
    response_text = response.content.strip() if response.content else ""
    if not response_text:
        raise TranslationError("Empty batch translation response")

    return _parse_batch_response(response_text, len(batch))


def _translate_one_by_one(
    translator: Agent,
    batch: list[SubtitleEntry],
    source_lang: str,
    target_lang: str,
) -> list[str]:
    """Translate subtitle entries one at a time as fallback.

    Args:
        translator: Agno Agent instance
        batch: List of SubtitleEntry to translate
        source_lang: Source language code
        target_lang: Target language code

    Returns:
        List of translated strings

    Raises:
        TranslationError: If any individual translation fails
    """
    results = []
    for entry in batch:
        response = translator.run(
            f"將這段字幕從{source_lang}翻譯成{target_lang}：{entry.text}"  # noqa: RUF001
        )
        translated_text = response.content.strip() if response.content else ""
        if not translated_text:
            raise TranslationError(
                f"Empty or whitespace-only translation for entry "
                f"{entry.index}: {entry.text}"
            )
        results.append(translated_text)
    return results


def translate_subtitle(
    subtitle: Subtitle,
    *,
    source_lang: str = "en",
    target_lang: str = "zh-TW",
    on_progress: Callable[[int, int], None] | None = None,
) -> Subtitle:
    """Translate all entries in a subtitle using LLM.

    Uses batch translation (10 entries per API call) for efficiency.
    Falls back to one-by-one translation if batch parsing fails.

    Args:
        subtitle: The subtitle to translate
        source_lang: Source language code (default: "en")
        target_lang: Target language code (default: "zh-TW")
        on_progress: Optional callback for progress updates. Called with
            (completed_count, total_count) after each batch.

    Returns:
        New Subtitle object with translated text

    Raises:
        TranslationError: If translation fails
    """
    translator = Agent(
        model=Ollama(id="TwinkleAI/gemma-3-4B-T1-it"),
        description=(
            "你是專業的影片字幕翻譯員。"
            "將英文字幕翻譯成道地的台灣繁體中文。"
            "規則：意譯為主，忠於語意但用自然口語表達；簡短有力，適合字幕閱讀；"  # noqa: RUF001
            "收到編號字幕，只回傳相同編號的翻譯結果；不要加任何解釋或額外文字。"  # noqa: RUF001
        ),
    )

    entries = subtitle.entries
    translated_texts: list[str] = []

    for i in range(0, len(entries), _BATCH_SIZE):
        batch = entries[i : i + _BATCH_SIZE]
        try:
            batch_translations = _translate_batch(
                translator, batch, source_lang, target_lang
            )
            translated_texts.extend(batch_translations)
            if on_progress is not None:
                on_progress(len(translated_texts), len(entries))
        except (TranslationError, Exception) as exc:
            logger.warning(
                "Batch translation failed for entries %d-%d, falling back to "
                "one-by-one: %s",
                i + 1,
                i + len(batch),
                exc,
            )
            try:
                fallback_translations = _translate_one_by_one(
                    translator, batch, source_lang, target_lang
                )
                translated_texts.extend(fallback_translations)
                if on_progress is not None:
                    on_progress(len(translated_texts), len(entries))
            except TranslationError:
                raise
            except Exception as e:
                raise TranslationError(
                    f"Failed to translate entries {i + 1}-{i + len(batch)}"
                ) from e

    translated_entries = [
        SubtitleEntry(
            index=entry.index,
            start=entry.start,
            end=entry.end,
            text=text,
        )
        for entry, text in zip(entries, translated_texts, strict=True)
    ]

    return Subtitle(entries=translated_entries)
