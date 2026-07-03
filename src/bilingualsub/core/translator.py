"""LLM-based subtitle translation using Agno."""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from json import JSONDecodeError, loads
from typing import Any
from urllib.parse import urlparse

import structlog
from agno.agent import Agent
from agno.models.base import Model
from agno.models.openai import OpenAIChat

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.utils.config import (
    Settings,
    get_groq_api_key,
    get_openai_api_key,
    get_settings,
)

logger = structlog.get_logger()

_BATCH_SIZE = 10
_CONTEXT_SIZE = 5  # Number of previous entries to include as context
_LOOKAHEAD_SIZE = 3  # Number of upcoming entries to include as forward context
_MAX_RETRIES = 5
_PARTIAL_CONTEXT_WINDOW = 5
_MAX_METADATA_TITLE_CHARS = 200
_MAX_METADATA_DESC_CHARS = 1200
_GROQ_PREFIX = "groq:"
_OPENAI_PREFIX = "openai:"
_PROXY_PLACEHOLDER_API_KEY = "dummy"  # pragma: allowlist secret


class TranslationError(Exception):
    """Raised when translation fails."""


class RateLimitError(TranslationError):
    """Raised when API rate limit is hit."""

    def __init__(self, retry_after: float, message: str = "") -> None:
        self.retry_after = retry_after
        super().__init__(message or f"Rate limited, retry after {retry_after:.0f}s")


@dataclass
class RetranslateEntry:
    """Subtitle row used by partial re-translation."""

    index: int
    original: str
    translated: str = ""


@dataclass
class RetranslateResult:
    """Structured result from partial re-translation."""

    index: int
    original: str
    translated: str


def _is_openai_model(model_str: str) -> bool:
    return model_str.strip().lower().startswith(_OPENAI_PREFIX)


def _ensure_translator_api_key(settings: Settings) -> None:
    """Validate API key for managed translator providers.

    Skips the OpenAI key check when a proxy base URL is configured,
    since proxies supply their own authentication.

    Raises:
        ValueError: If required provider key is missing.
    """
    model_str = settings.translator_model
    if model_str.strip().lower().startswith(_GROQ_PREFIX):
        get_groq_api_key()
    elif _is_openai_model(model_str) and not settings.openai_base_url:
        get_openai_api_key()


def _build_model(settings: Settings) -> str | Model:
    """Build an Agno model instance or model string for the translator.

    When the translator model has an ``openai:`` prefix AND a custom
    ``OPENAI_BASE_URL`` is configured, constructs an :class:`OpenAIChat` model
    pointed at the proxy endpoint.  This allows OpenAI-compatible proxies
    (e.g. CLIProxyAPI) to be used without touching the Agno provider registry.

    In all other cases the raw model string is returned and Agno handles
    provider resolution itself (existing behavior).
    """
    model_str = settings.translator_model
    if _is_openai_model(model_str) and settings.openai_base_url:
        # _is_openai_model lowercases; slice original to preserve casing
        model_id = model_str.strip()[len(_OPENAI_PREFIX) :]
        return OpenAIChat(
            id=model_id,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key or _PROXY_PLACEHOLDER_API_KEY,
        )
    return model_str


def _model_log_metadata(settings: Settings) -> dict[str, str | None]:
    """Return safe model metadata for structured logs."""
    model_str = settings.translator_model.strip()
    provider_kind = "agno"
    model_id = model_str
    lower_model = model_str.lower()
    if lower_model.startswith(_GROQ_PREFIX):
        provider_kind = "groq"
        model_id = model_str[len(_GROQ_PREFIX) :]
    elif lower_model.startswith(_OPENAI_PREFIX):
        provider_kind = "openai"
        model_id = model_str[len(_OPENAI_PREFIX) :]

    parsed_base_url = urlparse(settings.openai_base_url or "")
    base_url_host = parsed_base_url.hostname if parsed_base_url.hostname else None
    return {
        "model_id": model_id,
        "provider_kind": provider_kind,
        "base_url_host": base_url_host,
    }


def _compact_text(text: str) -> str:
    """Normalize whitespace while preserving readable punctuation."""
    return re.sub(r"\s+", " ", text).strip()


def _truncate_text(text: str, max_chars: int) -> str:
    """Trim overly long metadata to keep prompts focused."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _build_metadata_section(video_title: str, video_description: str) -> str:
    """Build metadata context block used in system prompt."""
    title = _truncate_text(_compact_text(video_title), _MAX_METADATA_TITLE_CHARS)
    description = _truncate_text(
        _compact_text(video_description), _MAX_METADATA_DESC_CHARS
    )

    lines = []
    if title:
        lines.append(f"影片標題：{title}")  # noqa: RUF001
    if description:
        lines.append(f"影片說明：{description}")  # noqa: RUF001
    return "\n".join(lines)


def _build_translator_description(
    *,
    source_lang: str,
    target_lang: str,
    video_title: str,
    video_description: str,
    glossary_text: str = "",
) -> str:
    """Build agent system prompt description."""
    base = (
        "你是專業的影片字幕翻譯員。"
        f"將{source_lang}字幕翻譯成自然、道地的{target_lang}。"
        "規則：意譯為主，忠於語意但用自然口語表達；簡短有力，適合字幕閱讀；"  # noqa: RUF001
        "收到編號字幕，只回傳相同編號的翻譯結果；不要加任何解釋或額外文字。"  # noqa: RUF001
        "字幕可能在句子中間被截斷，這是正常的，請照樣翻譯，不要提示原文不完整。"  # noqa: RUF001
    )
    metadata_section = _build_metadata_section(video_title, video_description)
    result = base
    if metadata_section:
        result = (
            f"{base}\n\n"
            "以下是影片背景資訊，請用於理解語境、專有名詞與代稱，但不要逐字照抄："  # noqa: RUF001
            f"\n{metadata_section}"
        )
    if glossary_text:
        result = f"{result}\n\n{glossary_text}"
    return result


def _strip_number_prefix(text: str) -> str:
    """Remove optional leading numbering (e.g. '1. ...') from model output."""
    return re.sub(r"^\s*\d+\s*[.):\uff0e]\s*", "", text, count=1)


def _strip_json_fence(text: str) -> str:
    """Remove a Markdown JSON fence if the model wrapped the response."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _extract_retranslate_payload(payload: Any, expected_index: int) -> dict[str, Any]:
    """Extract one re-translation object from supported JSON response shapes."""
    if isinstance(payload, dict):
        if "results" in payload:
            return _extract_retranslate_payload(payload["results"], expected_index)
        if str(expected_index) in payload:
            value = payload[str(expected_index)]
            if isinstance(value, dict):
                return {"index": expected_index, **value}
            return {"index": expected_index, "translated": value}
        if "original" in payload or "translated" in payload:
            return payload
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("index") == expected_index:
                return item
        if len(payload) == 1 and isinstance(payload[0], dict):
            return payload[0]
    raise TranslationError(f"Could not parse re-translation JSON for {expected_index}")


def _parse_retranslate_response(
    response_text: str,
    *,
    expected_index: int,
    fallback_original: str,
) -> RetranslateResult:
    """Parse structured partial re-translation output, with plain-text fallback."""
    cleaned = _strip_json_fence(response_text)
    try:
        payload = _extract_retranslate_payload(loads(cleaned), expected_index)
    except (JSONDecodeError, TranslationError) as err:
        translated = _strip_number_prefix(response_text).strip()
        if not translated:
            raise TranslationError(
                f"Empty re-translation response for entry {expected_index}"
            ) from err
        return RetranslateResult(
            index=expected_index,
            original=fallback_original,
            translated=translated,
        )

    translated = str(payload.get("translated") or "").strip()
    original = str(payload.get("original") or fallback_original).strip()
    index = int(payload.get("index") or expected_index)
    if index != expected_index:
        raise TranslationError(
            f"Expected re-translation index {expected_index}, got {index}"
        )
    if not translated:
        raise TranslationError(
            f"Empty re-translation response for entry {expected_index}"
        )
    return RetranslateResult(index=index, original=original, translated=translated)


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
        f"只回傳編號翻譯，每行一條，編號與原文一致。\n"  # noqa: RUF001
        "若原文專有名詞疑似語音辨識錯字，請依上文、下文、影片背景與術語表修正後翻譯。"  # noqa: RUF001
        "例如同一影片已出現的品牌、人名、產品名與網域應保持一致。\n\n"
        f"{numbered_lines}"
        f"{lookahead_section}"
    )

    logger.debug(
        "translation_batch_request",
        source_lang=source_lang,
        target_lang=target_lang,
        entry_count=len(batch),
        batch_start_index=batch[0].index,
        batch_end_index=batch[-1].index,
        has_context=bool(context),
        lookahead_count=len(lookahead or []),
    )

    started_at = time.monotonic()
    response = translator.run(prompt)
    duration_ms = round((time.monotonic() - started_at) * 1000)
    response_text = response.content.strip() if response.content else ""
    if not response_text:
        raise TranslationError("Empty batch translation response")

    _check_rate_limit(response_text)

    logger.debug(
        "translation_batch_response",
        source_lang=source_lang,
        target_lang=target_lang,
        entry_count=len(batch),
        batch_start_index=batch[0].index,
        batch_end_index=batch[-1].index,
        duration_ms=duration_ms,
        response_chars=len(response_text),
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
        try:
            response = translator.run(
                f"將這段字幕從{source_lang}翻譯成{target_lang}：{entry.text}"  # noqa: RUF001
            )
        except Exception as exc:
            raise TranslationError(
                f"Failed to translate entry {entry.index}: {entry.text}"
            ) from exc
        translated_text = response.content.strip() if response.content else ""
        _check_rate_limit(translated_text)
        if not translated_text:
            raise TranslationError(
                f"Empty or whitespace-only translation for entry "
                f"{entry.index}: {entry.text}"
            )
        logger.debug(
            "translation_one_by_one_entry_completed",
            index=entry.index,
            source_lang=source_lang,
            target_lang=target_lang,
            response_chars=len(translated_text),
        )
        results.append(translated_text)
    return results


def translate_subtitle(
    subtitle: Subtitle,
    *,
    source_lang: str = "en",
    target_lang: str = "zh-TW",
    video_title: str = "",
    video_description: str = "",
    glossary_text: str = "",
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
        video_title: Video title for translation context.
        video_description: Video description for translation context.
        on_progress: Optional callback for progress updates. Called with
            (completed_count, total_count) after each batch.
        on_rate_limit: Optional callback when rate limited. Called with
            (retry_after_seconds, attempt, max_retries).

    Returns:
        New Subtitle object with translated text

    Raises:
        TranslationError: If translation fails
        ValueError: If provider API key is missing
    """
    settings = get_settings()
    _ensure_translator_api_key(settings)
    model_metadata = _model_log_metadata(settings)
    translator = Agent(
        model=_build_model(settings),
        description=_build_translator_description(
            source_lang=source_lang,
            target_lang=target_lang,
            video_title=video_title,
            video_description=video_description,
            glossary_text=glossary_text,
        ),
    )

    entries = subtitle.entries
    translated_texts: list[str] = []
    logger.info(
        "translation_started",
        **model_metadata,
        source_lang=source_lang,
        target_lang=target_lang,
        entry_count=len(entries),
        batch_size=_BATCH_SIZE,
    )
    started_at = time.monotonic()

    for i in range(0, len(entries), _BATCH_SIZE):
        batch = entries[i : i + _BATCH_SIZE]

        logger.debug(
            "translation_batch_started",
            **model_metadata,
            source_lang=source_lang,
            target_lang=target_lang,
            batch_number=i // _BATCH_SIZE + 1,
            batch_count=(len(entries) + _BATCH_SIZE - 1) // _BATCH_SIZE,
            batch_start_index=batch[0].index,
            batch_end_index=batch[-1].index,
            entry_count=len(batch),
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
                        "translation_batch_fallback",
                        **model_metadata,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        batch_start_index=batch[0].index,
                        batch_end_index=batch[-1].index,
                        entry_count=len(batch),
                        error_type=type(exc).__name__,
                    )
                    logger.debug(
                        "translation_one_by_one_fallback_started",
                        batch_start_index=batch[0].index,
                        batch_end_index=batch[-1].index,
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
                        "translation_rate_limited",
                        **model_metadata,
                        batch_start_index=batch[0].index,
                        batch_end_index=batch[-1].index,
                        attempt=attempt + 1,
                        max_retries=_MAX_RETRIES,
                        retry_after_seconds=exc.retry_after,
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

    logger.info(
        "translation_completed",
        **model_metadata,
        source_lang=source_lang,
        target_lang=target_lang,
        entry_count=len(entries),
        duration_ms=round((time.monotonic() - started_at) * 1000),
    )

    return Subtitle(entries=translated_entries)


def _build_retranslate_prompt(
    *,
    target_entry: RetranslateEntry,
    prev_entries: list[RetranslateEntry],
    next_entries: list[RetranslateEntry],
    normalized_user_context: str,
    source_lang: str,
    target_lang: str,
) -> str:
    """Build the partial re-translation prompt for one selected entry."""
    sections: list[str] = []
    if prev_entries:
        prev_lines = "\n".join(
            f"- {entry.original} → {entry.translated or '(待翻譯)'}"
            for entry in prev_entries
        )
        sections.append(f"【上文參考】\n{prev_lines}")

    if next_entries:
        next_lines = "\n".join(
            f"- {entry.original} → {entry.translated or '(待翻譯)'}"
            for entry in next_entries
        )
        sections.append(f"【下文參考】\n{next_lines}")

    if normalized_user_context:
        sections.append(f"【使用者補充上下文】\n{normalized_user_context}")

    prompt_sections = "\n\n".join(sections)
    instruction = (
        f"請將以下字幕從{source_lang}翻譯成{target_lang}。\n"
        "只回傳一個 JSON 物件，不要加 Markdown、引號外文字或任何說明。\n"  # noqa: RUF001
        '格式：{"index": 數字, "original": "修正後原文", '  # noqa: RUF001
        '"translated": "目標語言翻譯"}。\n'
        "若原文專有名詞疑似語音辨識錯字，請依上文、下文、影片背景、術語表與使用者補充上下文修正後翻譯。"  # noqa: RUF001
        "例如同一影片已出現的品牌、人名、產品名與網域應保持一致。\n\n"
        f"index: {target_entry.index}\n"
        f"原文: {target_entry.original}\n"
        f"目前翻譯（可修正）: {target_entry.translated or '(空)'}"  # noqa: RUF001
    )
    return (f"{prompt_sections}\n\n" if prompt_sections else "") + instruction


def retranslate_entries(
    *,
    entries: list[RetranslateEntry],
    selected_indices: list[int],
    source_lang: str = "en",
    target_lang: str = "zh-TW",
    video_title: str = "",
    video_description: str = "",
    glossary_text: str = "",
    user_context: str | None = None,
) -> dict[int, RetranslateResult]:
    """Re-translate selected subtitle entries with local context.

    Args:
        entries: Full subtitle rows in current editor order.
        selected_indices: Entry indices that should be re-translated.
        source_lang: Source language code.
        target_lang: Target language code.
        video_title: Video title for translation context.
        video_description: Video description for translation context.
        user_context: Optional extra context provided by user.

    Returns:
        Mapping: entry index -> structured result containing corrected source and
            translated text.

    Raises:
        ValueError: If request payload is invalid.
        ValueError: If provider API key is missing.
        TranslationError: If translation fails after retries.
    """
    if not entries:
        raise ValueError("entries cannot be empty")
    if not selected_indices:
        raise ValueError("selected_indices cannot be empty")

    ordered_indices = list(dict.fromkeys(selected_indices))
    position_by_index = {entry.index: i for i, entry in enumerate(entries)}
    missing = [idx for idx in ordered_indices if idx not in position_by_index]
    if missing:
        raise ValueError(f"selected_indices not found: {missing}")

    settings = get_settings()
    _ensure_translator_api_key(settings)
    model_metadata = _model_log_metadata(settings)
    translator = Agent(
        model=_build_model(settings),
        description=_build_translator_description(
            source_lang=source_lang,
            target_lang=target_lang,
            video_title=video_title,
            video_description=video_description,
            glossary_text=glossary_text,
        ),
    )

    normalized_user_context = _compact_text(user_context or "")
    results: dict[int, RetranslateResult] = {}
    logger.info(
        "retranslation_started",
        **model_metadata,
        source_lang=source_lang,
        target_lang=target_lang,
        entry_count=len(entries),
        selected_indices_count=len(ordered_indices),
    )
    retranslation_started_at = time.monotonic()

    for target_index in ordered_indices:
        entry_started_at = time.monotonic()
        position = position_by_index[target_index]
        target_entry = entries[position]
        prev_entries = entries[max(0, position - _PARTIAL_CONTEXT_WINDOW) : position]
        next_entries = entries[position + 1 : position + 1 + _PARTIAL_CONTEXT_WINDOW]
        prompt = _build_retranslate_prompt(
            target_entry=target_entry,
            prev_entries=prev_entries,
            next_entries=next_entries,
            normalized_user_context=normalized_user_context,
            source_lang=source_lang,
            target_lang=target_lang,
        )

        logger.debug(
            "retranslation_entry_request",
            **model_metadata,
            source_lang=source_lang,
            target_lang=target_lang,
            index=target_index,
            previous_context_count=len(prev_entries),
            next_context_count=len(next_entries),
            has_user_context=bool(normalized_user_context),
        )

        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = translator.run(prompt)
                response_text = response.content.strip() if response.content else ""
                if not response_text:
                    raise TranslationError(
                        f"Empty re-translation response for entry {target_index}"
                    )
                _check_rate_limit(response_text)
                results[target_index] = _parse_retranslate_response(
                    response_text,
                    expected_index=target_index,
                    fallback_original=target_entry.original,
                )
                logger.debug(
                    "retranslation_entry_response",
                    **model_metadata,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    index=target_index,
                    duration_ms=round((time.monotonic() - entry_started_at) * 1000),
                    response_chars=len(response_text),
                )
                break
            except RateLimitError as exc:
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "retranslation_rate_limited",
                        **model_metadata,
                        index=target_index,
                        attempt=attempt + 1,
                        max_retries=_MAX_RETRIES,
                        retry_after_seconds=exc.retry_after,
                    )
                    time.sleep(exc.retry_after)
                else:
                    raise TranslationError(
                        f"Rate limit exceeded after {_MAX_RETRIES} retries "
                        f"for entry {target_index}"
                    ) from exc
        else:
            raise TranslationError(f"Failed to re-translate entry {target_index}")

    logger.info(
        "retranslation_completed",
        **model_metadata,
        source_lang=source_lang,
        target_lang=target_lang,
        entry_count=len(entries),
        selected_indices_count=len(ordered_indices),
        duration_ms=round((time.monotonic() - retranslation_started_at) * 1000),
    )

    return results
