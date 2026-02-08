"""LLM-based subtitle translation using Agno + Groq."""

import logging
import re
from collections.abc import Callable

from agno.agent import Agent
from agno.models.groq import Groq

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.utils.config import get_groq_api_key

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
        f"Translate the following subtitle lines from {source_lang} to {target_lang}.\n"
        f"Return ONLY the numbered translations, one per line, "
        f"matching the input numbering exactly.\n\n"
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
            f"Translate this subtitle text from {source_lang} to {target_lang}: "
            f"{entry.text}"
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
        ValueError: If GROQ_API_KEY is not set
    """
    api_key = get_groq_api_key()

    translator = Agent(
        model=Groq(
            id="qwen/qwen3-32b",
            api_key=api_key,
            request_params={"reasoning_format": "hidden"},
        ),
        description=(
            f"You are a professional subtitle translator. "
            f"Translate {source_lang} to {target_lang} naturally and fluently. "
            f"Keep the translation conversational and easy to understand. "
            f"You will receive numbered subtitle lines. "
            f"Return ONLY the numbered translations in the same format. "
            f"Do not add explanations, notes, or extra text."
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
