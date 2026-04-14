"""Unit tests for settings helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gitlab_stats import settings


class _FakeSecrets:  # pylint: disable=too-few-public-methods
    """Minimal secrets stub for streamlit-style access."""

    def __init__(self, value_by_key=None, error=None):
        self._value_by_key = value_by_key or {}
        self._error = error

    def get(self, name):
        """Get secret value by key, simulating streamlit secrets behavior."""
        if self._error is not None:
            raise self._error
        return self._value_by_key.get(name)


def test_read_setting_returns_trimmed_env_value(monkeypatch):
    """Return env value when present and strip surrounding whitespace."""
    # Arrange
    monkeypatch.setenv("MY_SETTING", "  value-from-env  ")

    # Act
    result = settings.read_setting("MY_SETTING")

    # Assert
    assert result == "value-from-env"


def test_read_setting_prefers_env_over_streamlit_secrets(monkeypatch):
    """Environment variables take precedence over streamlit secrets."""
    # Arrange
    monkeypatch.setenv("MY_SETTING", "env-wins")
    fake_st = SimpleNamespace(secrets=_FakeSecrets({"MY_SETTING": "secret-loses"}))
    monkeypatch.setattr(settings, "st", fake_st)

    # Act
    result = settings.read_setting("MY_SETTING")

    # Assert
    assert result == "env-wins"


def test_read_setting_returns_empty_when_no_env_and_no_streamlit(monkeypatch):
    """Return empty string when streamlit runtime is unavailable."""
    # Arrange
    monkeypatch.delenv("MY_SETTING", raising=False)
    monkeypatch.setattr(settings, "st", None)

    # Act
    result = settings.read_setting("MY_SETTING")

    # Assert
    assert result == ""


def test_read_setting_returns_trimmed_secret_when_env_missing(monkeypatch):
    """Use streamlit secrets when env is absent and streamlit exists."""
    # Arrange
    monkeypatch.delenv("MY_SETTING", raising=False)
    fake_st = SimpleNamespace(secrets=_FakeSecrets({"MY_SETTING": "  secret-value  "}))
    monkeypatch.setattr(settings, "st", fake_st)

    # Act
    result = settings.read_setting("MY_SETTING")

    # Assert
    assert result == "secret-value"


@pytest.mark.parametrize(
    "raised_error",
    [AttributeError("x"), RuntimeError("x"), KeyError("x"), TypeError("x")],
)
def test_read_setting_returns_empty_for_supported_secret_errors(
    monkeypatch,
    raised_error,
):
    """Treat supported streamlit secret failures as missing values."""
    # Arrange
    monkeypatch.delenv("MY_SETTING", raising=False)
    fake_st = SimpleNamespace(secrets=_FakeSecrets(error=raised_error))
    monkeypatch.setattr(settings, "st", fake_st)

    # Act
    result = settings.read_setting("MY_SETTING")

    # Assert
    assert result == ""


def test_read_setting_returns_empty_for_falsy_secret(monkeypatch):
    """Return empty string for missing or falsy secret values."""
    # Arrange
    monkeypatch.delenv("MY_SETTING", raising=False)
    fake_st = SimpleNamespace(secrets=_FakeSecrets({"MY_SETTING": ""}))
    monkeypatch.setattr(settings, "st", fake_st)

    # Act
    result = settings.read_setting("MY_SETTING")

    # Assert
    assert result == ""


def test_read_supabase_setting_prefers_dev_scoped_value(monkeypatch):
    """SUPABASE_TARGET=dev should prefer SUPABASE_DEV_* values."""
    # Arrange
    monkeypatch.setenv("SUPABASE_TARGET", "dev")
    monkeypatch.setenv("SUPABASE_DEV_URL", "https://dev.example.supabase.co")
    monkeypatch.setenv("SUPABASE_URL", "https://prod.example.supabase.co")

    # Act
    result = settings.read_supabase_setting("SUPABASE_URL")

    # Assert
    assert result == "https://dev.example.supabase.co"


def test_read_supabase_setting_falls_back_to_legacy_name(monkeypatch):
    """When scoped key is missing, fallback should use legacy SUPABASE_* name."""
    # Arrange
    monkeypatch.setenv("SUPABASE_TARGET", "prod")
    monkeypatch.delenv("SUPABASE_PROD_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "legacy-key")

    # Act
    result = settings.read_supabase_setting("SUPABASE_SERVICE_ROLE_KEY")

    # Assert
    assert result == "legacy-key"
