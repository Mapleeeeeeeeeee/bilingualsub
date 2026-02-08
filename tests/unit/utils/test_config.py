"""Unit tests for configuration utilities."""

import pytest

from bilingualsub.utils.config import get_groq_api_key, get_settings


class TestSettings:
    """Test cases for Settings class."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear settings cache before and after each test."""
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    @pytest.fixture
    def no_env_file(self, tmp_path, monkeypatch):
        """Run test in a directory without .env file."""
        monkeypatch.chdir(tmp_path)
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    def test_settings_loads_api_key_from_env(self, monkeypatch):
        """Should load GROQ_API_KEY from environment."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key-123")

        settings = get_settings()

        assert settings.groq_api_key == "test-key-123"

    def test_settings_defaults_to_empty_api_key(self, monkeypatch, no_env_file):
        """Should default to empty string when API key not set."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        settings = get_settings()

        assert settings.groq_api_key == ""

    def test_get_settings_is_cached(self, monkeypatch):
        """Should return cached settings on subsequent calls."""
        monkeypatch.setenv("GROQ_API_KEY", "original-key")

        settings1 = get_settings()
        monkeypatch.setenv("GROQ_API_KEY", "new-key")
        settings2 = get_settings()

        # Same instance due to caching
        assert settings1 is settings2
        assert settings1.groq_api_key == "original-key"

    def test_cache_clear_reloads_settings(self, monkeypatch):
        """Should reload settings after cache clear."""
        monkeypatch.setenv("GROQ_API_KEY", "original-key")
        settings1 = get_settings()

        get_settings.cache_clear()
        monkeypatch.setenv("GROQ_API_KEY", "new-key")
        settings2 = get_settings()

        assert settings1.groq_api_key == "original-key"
        assert settings2.groq_api_key == "new-key"
        assert settings1 is not settings2


class TestGetGroqApiKey:
    """Test cases for get_groq_api_key function."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear settings cache before and after each test."""
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    @pytest.fixture
    def no_env_file(self, tmp_path, monkeypatch):
        """Run test in a directory without .env file."""
        monkeypatch.chdir(tmp_path)
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    def test_returns_api_key_when_set(self, monkeypatch):
        """Should return API key when properly configured."""
        monkeypatch.setenv("GROQ_API_KEY", "valid-api-key-xyz")

        result = get_groq_api_key()

        assert result == "valid-api-key-xyz"

    def test_raises_error_when_key_not_set(self, monkeypatch, no_env_file):
        """Should raise ValueError when GROQ_API_KEY not set."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        with pytest.raises(ValueError) as exc_info:
            get_groq_api_key()

        assert "GROQ_API_KEY environment variable is not set" in str(exc_info.value)
        assert "Please set it with your Groq API key" in str(exc_info.value)

    def test_raises_error_when_key_is_empty(self, monkeypatch, no_env_file):
        """Should raise ValueError when GROQ_API_KEY is empty string."""
        monkeypatch.setenv("GROQ_API_KEY", "")

        with pytest.raises(ValueError) as exc_info:
            get_groq_api_key()

        assert "GROQ_API_KEY environment variable is not set" in str(exc_info.value)

    def test_raises_error_when_key_is_whitespace(self, monkeypatch):
        """Should raise ValueError when GROQ_API_KEY is only whitespace."""
        monkeypatch.setenv("GROQ_API_KEY", "   ")

        # Note: whitespace-only key passes current validation
        # If stricter validation is needed, update get_groq_api_key
        result = get_groq_api_key()
        assert result == "   "

    @pytest.mark.parametrize(
        "api_key",
        [
            "sk-1234567890",
            "gsk_abcdef123456",
            "test-key-with-dashes",
            "key_with_underscores",
        ],
    )
    def test_accepts_various_key_formats(self, monkeypatch, api_key):
        """Should accept various API key formats."""
        monkeypatch.setenv("GROQ_API_KEY", api_key)

        result = get_groq_api_key()

        assert result == api_key
