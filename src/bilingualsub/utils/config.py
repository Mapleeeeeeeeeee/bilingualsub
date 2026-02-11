"""Application configuration using pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Attributes:
        groq_api_key: API key for Groq services (Whisper + LLM)
        openai_api_key: API key for OpenAI services
        transcriber_provider: Whisper provider ("groq" or "openai")
        transcriber_model: Whisper model name
        translator_model: Agno model string (e.g. "ollama:model_id", "groq:model_id")
    """

    groq_api_key: str = ""
    openai_api_key: str = ""

    transcriber_provider: str = "groq"
    transcriber_model: str = "whisper-large-v3-turbo"

    translator_model: str = "groq:openai/gpt-oss-120b"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Returns:
        Settings instance loaded from environment

    Note:
        Settings are cached for performance. Use get_settings.cache_clear()
        to reload settings in tests.
    """
    return Settings()


def get_groq_api_key() -> str:
    """Get Groq API key from environment.

    Returns:
        Groq API key string

    Raises:
        ValueError: If GROQ_API_KEY is not set or empty
    """
    settings = get_settings()
    if not settings.groq_api_key:
        raise ValueError(
            "GROQ_API_KEY environment variable is not set. "
            "Please set it with your Groq API key."
        )
    return settings.groq_api_key


def get_openai_api_key() -> str:
    """Get OpenAI API key from environment.

    Returns:
        OpenAI API key string

    Raises:
        ValueError: If OPENAI_API_KEY is not set or empty
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable is not set. "
            "Please set it with your OpenAI API key."
        )
    return settings.openai_api_key
