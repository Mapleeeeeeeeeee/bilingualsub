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
    glossary_path: str = "glossary.json"
    gemini_api_key: str = ""
    visual_description_model: str = "gemini-3.1-flash-lite-preview"

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


def _require_api_key(attr: str, env_var: str) -> str:
    value = getattr(get_settings(), attr)
    if not value:
        raise ValueError(
            f"{env_var} environment variable is not set. "
            f"Please set it with your {env_var} key."
        )
    return str(value)


def get_groq_api_key() -> str:
    return _require_api_key("groq_api_key", "GROQ_API_KEY")


def get_openai_api_key() -> str:
    return _require_api_key("openai_api_key", "OPENAI_API_KEY")


def get_gemini_api_key() -> str:
    return _require_api_key("gemini_api_key", "GEMINI_API_KEY")
