"""Application configuration using pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Attributes:
        groq_api_key: API key for Groq services (Whisper + LLM)
    """

    groq_api_key: str = ""

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
