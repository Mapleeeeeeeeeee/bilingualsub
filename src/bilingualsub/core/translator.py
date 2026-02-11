"""LLM-based subtitle translation using Agno."""

import re
import time
from collections.abc import Callable

import structlog
from agno.agent import Agent

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.utils.config import get_settings

logger = structlog.get_logger()

_BATCH_SIZE = 10
_CONTEXT_SIZE = 3  # Number of previous entries to include as context
_LOOKAHEAD_SIZE = 3  # Number of upcoming entries to include as forward context
_MAX_RETRIES = 5


class TranslationError(Exception):
    """Raised when translation fails."""


class RateLimitError(TranslationError):
    """Raised when API rate limit is hit."""

    def __init__(self, retry_after: float, message: str = "") -> None:
        self.retry_after = retry_after
        super().__init__(message or f"Rate limited, retry after {retry_after:.0f}s")


def _check_rate_limit(response_text: str) -> None:
    """Raise RateLimitError if response contains rate limit error.

    Args:
        response_text: Raw response text from LLM

    Raises:
        RateLimitError: If rate limit detected, with parsed retry_after seconds
    """
    if "rate_limit_exceeded" not in response_text:
        return

    # Parse "Please try again in 4m25.248s" or "1m6.095s"
    match = re.search(r"try again in (?:(\d+)m)?(\d+(?:\.\d+)?)s", response_text)
    if match:
        minutes = int(match.group(1) or 0)
        seconds = float(match.group(2))
        retry_after = minutes * 60 + seconds
    else:
        retry_after = 60.0  # Default fallback

    raise RateLimitError(retry_after=retry_after, message=response_text)


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
    context: list[tuple[str, str]] | None = None,
    lookahead: list[SubtitleEntry] | None = None,
) -> list[str]:
    """Translate a batch of subtitle entries in a single API call.

    Args:
        translator: Agno Agent instance
        batch: List of SubtitleEntry to translate
        source_lang: Source language code
        target_lang: Target language code
        context: Optional list of (original, translated) pairs from previous batch
        lookahead: Optional list of upcoming SubtitleEntry for forward context

    Returns:
        List of translated strings

    Raises:
        TranslationError: If batch translation or parsing fails
    """
    context_section = ""
    if context:
        context_lines = "\n".join(f"- {orig} → {trans}" for orig, trans in context)
        context_section = f"【上文參考】\n{context_lines}\n\n"

    numbered_lines = "\n".join(f"{i}. {entry.text}" for i, entry in enumerate(batch, 1))

    lookahead_section = ""
    if lookahead:
        lookahead_lines = "\n".join(f"- {entry.text}" for entry in lookahead)
        lookahead_section = (
            f"\n\n【下文參考（僅供理解語意，不需翻譯）】\n{lookahead_lines}"  # noqa: RUF001
        )

    prompt = (
        f"{context_section}"
        f"將以下編號字幕從{source_lang}翻譯成{target_lang}。\n"
        f"只回傳編號翻譯，每行一條，編號與原文一致。\n\n"  # noqa: RUF001
        f"{numbered_lines}"
        f"{lookahead_section}"
    )

    logger.debug(
        "Batch translation prompt (entries %d-%d):\n%s",
        batch[0].index,
        batch[-1].index,
        prompt,
    )

    response = translator.run(prompt)
    response_text = response.content.strip() if response.content else ""
    if not response_text:
        raise TranslationError("Empty batch translation response")

    _check_rate_limit(response_text)

    logger.debug(
        "Batch translation response (entries %d-%d):\n%s",
        batch[0].index,
        batch[-1].index,
        response_text,
    )

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
        _check_rate_limit(translated_text)
        if not translated_text:
            raise TranslationError(
                f"Empty or whitespace-only translation for entry "
                f"{entry.index}: {entry.text}"
            )
        logger.debug(
            "One-by-one translation for entry %d: '%s' -> '%s'",
            entry.index,
            entry.text,
            translated_text,
        )
        results.append(translated_text)
    return results


def translate_subtitle(
    subtitle: Subtitle,
    *,
    source_lang: str = "en",
    target_lang: str = "zh-TW",
    on_progress: Callable[[int, int], None] | None = None,
    on_rate_limit: Callable[[float, int, int], None] | None = None,
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
        on_rate_limit: Optional callback when rate limited. Called with
            (retry_after_seconds, attempt, max_retries).

    Returns:
        New Subtitle object with translated text

    Raises:
        TranslationError: If translation fails
    """
    settings = get_settings()
    translator = Agent(
        model=settings.translator_model,
        description=(
            "你是專業的影片字幕翻譯員。"
            "將英文字幕翻譯成道地的台灣繁體中文。"
            "規則：意譯為主，忠於語意但用自然口語表達；簡短有力，適合字幕閱讀；"  # noqa: RUF001
            "收到編號字幕，只回傳相同編號的翻譯結果；不要加任何解釋或額外文字。"  # noqa: RUF001
            "字幕可能在句子中間被截斷，這是正常的，請照樣翻譯，不要提示原文不完整。"  # noqa: RUF001
        ),
    )

    entries = subtitle.entries
    translated_texts: list[str] = []

    for i in range(0, len(entries), _BATCH_SIZE):
        batch = entries[i : i + _BATCH_SIZE]

        logger.debug(
            "Processing batch %d/%d (entries %d-%d)",
            i // _BATCH_SIZE + 1,
            (len(entries) + _BATCH_SIZE - 1) // _BATCH_SIZE,
            batch[0].index,
            batch[-1].index,
        )

        # Collect context from previously translated entries
        context_start = max(0, i - _CONTEXT_SIZE)
        context: list[tuple[str, str]] | None = (
            [(entries[j].text, translated_texts[j]) for j in range(context_start, i)]
            if i > 0
            else None
        )

        # Collect lookahead entries for forward context
        lookahead_end = min(i + _BATCH_SIZE + _LOOKAHEAD_SIZE, len(entries))
        lookahead = (
            entries[i + _BATCH_SIZE : lookahead_end]
            if i + _BATCH_SIZE < len(entries)
            else None
        )

        for attempt in range(_MAX_RETRIES + 1):
            try:
                # Try batch translation first
                try:
                    batch_translations = _translate_batch(
                        translator,
                        batch,
                        source_lang,
                        target_lang,
                        context=context,
                        lookahead=lookahead,
                    )
                except RateLimitError:
                    raise  # Don't fallback on rate limit
                except (TranslationError, Exception) as exc:
                    # Fallback to one-by-one for non-rate-limit errors
                    logger.warning(
                        "Batch translation failed for entries %d-%d, "
                        "falling back to one-by-one: %s",
                        i + 1,
                        i + len(batch),
                        exc,
                    )
                    logger.debug(
                        "Falling back to one-by-one for entries %d-%d",
                        i + 1,
                        i + len(batch),
                    )
                    batch_translations = _translate_one_by_one(
                        translator, batch, source_lang, target_lang
                    )

                translated_texts.extend(batch_translations)
                if on_progress is not None:
                    on_progress(len(translated_texts), len(entries))
                break  # Success, exit retry loop

            except RateLimitError as exc:
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "Rate limited at entries %d-%d (attempt %d/%d), waiting %.0fs",
                        batch[0].index,
                        batch[-1].index,
                        attempt + 1,
                        _MAX_RETRIES,
                        exc.retry_after,
                    )
                    if on_rate_limit is not None:
                        on_rate_limit(exc.retry_after, attempt + 1, _MAX_RETRIES)
                    time.sleep(exc.retry_after)
                else:
                    raise TranslationError(
                        f"Rate limit exceeded after {_MAX_RETRIES} retries "
                        f"for entries {batch[0].index}-{batch[-1].index}"
                    ) from exc
        else:
            raise TranslationError(
                f"Failed to translate entries {batch[0].index}-{batch[-1].index}"
            )

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
