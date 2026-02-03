"""LLM-based subtitle translation using Agno + Groq."""

import os

from agno.agent import Agent
from agno.models.groq import Groq

from bilingualsub.core.subtitle import Subtitle, SubtitleEntry


class TranslationError(Exception):
    """Raised when translation fails."""


def translate_subtitle(
    subtitle: Subtitle,
    *,
    source_lang: str = "en",
    target_lang: str = "zh-TW",
) -> Subtitle:
    """Translate all entries in a subtitle using LLM.

    Args:
        subtitle: The subtitle to translate
        source_lang: Source language code (default: "en")
        target_lang: Target language code (default: "zh-TW")

    Returns:
        New Subtitle object with translated text

    Raises:
        TranslationError: If translation fails
        ValueError: If GROQ_API_KEY is not set
    """
    # Check API key
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY environment variable is not set. "
            "Please set it with your Groq API key."
        )

    # Create translator agent
    translator = Agent(
        model=Groq(id="qwen-qwq-32b"),
        description=(
            f"You are a professional subtitle translator. "
            f"Translate {source_lang} to {target_lang} naturally and fluently. "
            f"Keep the translation conversational and easy to understand. "
            f"Only return the translated text, nothing else."
        ),
    )

    # Translate each entry
    translated_entries = []
    for entry in subtitle.entries:
        try:
            response = translator.run(
                f"Translate this subtitle text from {source_lang} to {target_lang}: "
                f"{entry.text}"
            )

            # Extract translated text from response
            translated_text = response.content.strip() if response.content else ""
            if not translated_text:
                raise TranslationError(
                    f"Empty or whitespace-only translation for entry {entry.index}: {entry.text}"
                )

            # Create new entry with translated text
            translated_entry = SubtitleEntry(
                index=entry.index,
                start=entry.start,
                end=entry.end,
                text=translated_text,
            )
            translated_entries.append(translated_entry)

        except TranslationError:
            # Re-raise TranslationError as-is
            raise
        except Exception as e:
            raise TranslationError(
                f"Failed to translate entry {entry.index}: {entry.text}"
            ) from e

    return Subtitle(entries=translated_entries)
