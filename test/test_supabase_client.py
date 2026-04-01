"""Unit tests for gitlab_stats.database.supabase_client."""

import datetime

import pytest

from gitlab_stats.database import supabase_client

# pylint: disable=protected-access


class DummySettings:  # pylint: disable=too-few-public-methods
    """Patchable settings for testing."""

    def __init__(self, url: str | None = None, key: str | None = None):
        self.url = url
        self.key = key

    def __call__(self, name: str):
        if name == "SUPABASE_URL":
            return self.url
        if name == "SUPABASE_SERVICE_ROLE_KEY":
            return self.key
        return None


def patch_settings(
    monkeypatch,
    url: str | None = "https://dummy.supabase.co",
    key: str | None = "dummy-key",
):
    """Patch supabase settings reader for deterministic tests."""
    monkeypatch.setattr(supabase_client, "read_setting", DummySettings(url, key))


def test_missing_url(monkeypatch):
    """Raise a config error when SUPABASE_URL is missing."""
    patch_settings(monkeypatch, url=None)
    with pytest.raises(supabase_client.SupabaseConfigError) as exc:
        supabase_client._supabase_rest_base_url()  # type: ignore[attr-defined]
    assert "SUPABASE_URL" in str(exc.value)


def test_missing_read_key(monkeypatch):
    """Raise a config error when read key is missing."""
    patch_settings(monkeypatch, key=None)
    with pytest.raises(supabase_client.SupabaseConfigError) as exc:
        supabase_client._read_api_keys_for_select()  # type: ignore[attr-defined]
    assert "read key" in str(exc.value)


def test_missing_write_key(monkeypatch):
    """Raise a config error when write key is missing."""
    patch_settings(monkeypatch, key=None)
    with pytest.raises(supabase_client.SupabaseConfigError) as exc:
        supabase_client._write_api_key()  # type: ignore[attr-defined]
    assert "write key" in str(exc.value) or "SUPABASE_SERVICE_ROLE_KEY" in str(
        exc.value,
    )


def test_chunked():
    """Split items into expected fixed-size chunks."""
    items = [{"i": i} for i in range(10)]
    chunks = supabase_client._chunked(items, 3)  # type: ignore[attr-defined]
    assert len(chunks) == 4
    assert sum(len(chunk) for chunk in chunks) == 10
    assert chunks[0] == [{"i": 0}, {"i": 1}, {"i": 2}]
    assert chunks[-1] == [{"i": 9}]


def test_parse_iso_date():
    """Parse valid values and reject invalid date-like inputs."""
    today = datetime.datetime.now(tz=datetime.UTC).date()
    assert supabase_client._parse_iso_date(today.isoformat()) == today  # type: ignore[attr-defined]
    assert supabase_client._parse_iso_date(None) is None  # type: ignore[attr-defined]
    assert supabase_client._parse_iso_date("") is None  # type: ignore[attr-defined]
    assert supabase_client._parse_iso_date("not-a-date") is None  # type: ignore[attr-defined]
    # Accepts date object
    assert supabase_client._parse_iso_date(today) == today  # type: ignore[attr-defined]


def test_supabase_request_error_messages():
    """Build descriptive request error messages."""
    err = supabase_client.SupabaseRequestError.expected_list_payload()
    assert "Expected list payload" in str(err)
    err = supabase_client.SupabaseRequestError.http_failure("GET", "url", 404, "fail")
    assert "404" in str(err)
    assert "fail" in str(err)
    err = supabase_client.SupabaseRequestError.network_failure("GET", "url", "timeout")
    assert "network failure" in str(err).lower()


def test_supabase_config_error_messages():
    """Build descriptive configuration error messages."""
    assert (
        "missing url" in str(supabase_client.SupabaseConfigError.missing_url()).lower()
    )
    assert (
        "missing read key"
        in str(supabase_client.SupabaseConfigError.missing_read_key()).lower()
    )
    assert (
        "missing write key"
        in str(supabase_client.SupabaseConfigError.missing_write_key()).lower()
    )
