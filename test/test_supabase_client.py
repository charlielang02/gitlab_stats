"""Unit tests for gitlab_stats.database.supabase_client."""

import datetime
from io import BytesIO
from urllib.error import HTTPError
from urllib.error import URLError

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
    monkeypatch.setattr(
        supabase_client,
        "read_supabase_setting",
        DummySettings(url, key),
    )


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


class _FakeHttpResponse:  # pylint: disable=too-few-public-methods
    """Minimal context-managed HTTP response for request_json tests."""

    def __init__(self, body: str, headers: dict | None = None):
        self._body = body
        self.headers = headers or {}

    def __enter__(self):
        """Return response object in context manager."""
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """Allow context manager exit without suppressing exceptions."""
        return False

    def read(self):
        """Return encoded response body bytes."""
        return self._body.encode("utf-8")


def test_request_json_returns_none_for_empty_response_body(monkeypatch):
    """Empty response bodies should be treated as no payload."""
    # Arrange
    patch_settings(monkeypatch)

    def _fake_urlopen(*_, **__):
        """Return an empty-body HTTP response."""
        return _FakeHttpResponse("   ")

    monkeypatch.setattr(supabase_client, "urlopen", _fake_urlopen)

    # Act
    payload = supabase_client._request_json("GET", "events", "dummy-key")

    # Assert
    assert payload is None


def test_request_json_decodes_json_payload(monkeypatch):
    """JSON responses should be decoded into Python values."""
    # Arrange
    patch_settings(monkeypatch)

    def _fake_urlopen(*_, **__):
        """Return a response body with JSON content."""
        return _FakeHttpResponse('[{"project":"repo","count":2}]')

    monkeypatch.setattr(supabase_client, "urlopen", _fake_urlopen)

    # Act
    payload = supabase_client._request_json("GET", "events", "dummy-key")

    # Assert
    assert payload == [{"project": "repo", "count": 2}]


def test_request_json_raises_request_error_on_http_failure(monkeypatch):
    """HTTPError responses should be wrapped in SupabaseRequestError."""
    # Arrange
    patch_settings(monkeypatch)

    def _fake_urlopen(*_, **__):
        """Raise an HTTP error containing a decodable response body."""
        raise HTTPError(
            url="https://dummy.supabase.co/rest/v1/events",
            code=400,
            msg="Bad Request",
            hdrs=None,  # type: ignore
            fp=BytesIO(b'{"message":"invalid"}'),
        )

    monkeypatch.setattr(supabase_client, "urlopen", _fake_urlopen)

    # Act / Assert
    with pytest.raises(supabase_client.SupabaseRequestError) as exc:
        supabase_client._request_json("GET", "events", "dummy-key")

    error_message = str(exc.value)
    assert "400" in error_message
    assert "invalid" in error_message


def test_request_json_raises_request_error_on_network_failure(monkeypatch):
    """URLError responses should be wrapped in SupabaseRequestError."""
    # Arrange
    patch_settings(monkeypatch)

    def _fake_urlopen(*_, **__):
        """Raise a network error for request path coverage."""
        raise URLError("connection reset")

    monkeypatch.setattr(supabase_client, "urlopen", _fake_urlopen)

    # Act / Assert
    with pytest.raises(supabase_client.SupabaseRequestError) as exc:
        supabase_client._request_json("GET", "events", "dummy-key")

    assert "network failure" in str(exc.value).lower()


def test_fetch_event_date_bounds_from_supabase_returns_sorted_dates(monkeypatch):
    """Oldest/newest payloads should produce an ordered start/end tuple."""
    # Arrange
    monkeypatch.setattr(supabase_client, "_read_api_keys_for_select", lambda: ["k1"])
    responses = [
        [{"event_date": "2026-03-10"}],
        [{"event_date": "2026-03-01"}],
    ]

    def _fake_request_json(*_):
        """Return oldest then newest payloads for bounds lookup."""
        return responses.pop(0)

    monkeypatch.setattr(supabase_client, "_request_json", _fake_request_json)

    # Act
    bounds = supabase_client.fetch_event_date_bounds_from_supabase()

    # Assert
    assert bounds == (datetime.date(2026, 3, 1), datetime.date(2026, 3, 10))


def test_fetch_event_date_bounds_from_supabase_raises_last_error_after_retries(
    monkeypatch,
):
    """All failing read keys should re-raise the final request error."""
    # Arrange
    monkeypatch.setattr(
        supabase_client,
        "_read_api_keys_for_select",
        lambda: ["k1", "k2"],
    )
    failure = supabase_client.SupabaseRequestError.network_failure(
        "GET",
        "events",
        "timeout",
    )

    def _fake_request_json(*_):
        """Raise a request error across read-key retries."""
        raise failure

    monkeypatch.setattr(supabase_client, "_request_json", _fake_request_json)

    # Act / Assert
    with pytest.raises(supabase_client.SupabaseRequestError) as exc:
        supabase_client.fetch_event_date_bounds_from_supabase()

    assert str(exc.value) == str(failure)


def test_fetch_events_from_supabase_swaps_period_boundaries(monkeypatch):
    """Explicit period bounds should be normalized before querying."""
    # Arrange
    monkeypatch.setattr(supabase_client, "_read_api_keys_for_select", lambda: ["k1"])

    captured = {}

    def _fake_request_json(method, path, key):
        """Capture query path and return a valid list payload."""
        captured["method"] = method
        captured["path"] = path
        captured["key"] = key
        return [
            {
                "event_date": "2026-03-01",
                "project": "x",
                "event_type": "commits",
                "count": 1,
            },
        ]

    monkeypatch.setattr(supabase_client, "_request_json", _fake_request_json)

    # Act
    rows = supabase_client.fetch_events_from_supabase(
        lookback_days=30,
        period_start=datetime.date(2026, 3, 10),
        period_end=datetime.date(2026, 3, 1),
    )

    # Assert
    assert rows[0]["count"] == 1
    assert captured["method"] == "GET"
    assert "event_date.gte.2026-03-01" in captured["path"]
    assert "event_date.lte.2026-03-10" in captured["path"]


def test_fetch_events_from_supabase_retries_and_raises_last_error(monkeypatch):
    """When all read keys fail, fetch should raise the final request error."""
    # Arrange
    monkeypatch.setattr(
        supabase_client,
        "_read_api_keys_for_select",
        lambda: ["k1", "k2"],
    )
    failure = supabase_client.SupabaseRequestError.http_failure(
        "GET",
        "events",
        500,
        "boom",
    )

    def _fake_request_json(*_):
        """Raise failures for both keys to cover retry exhaustion."""
        raise failure

    monkeypatch.setattr(supabase_client, "_request_json", _fake_request_json)

    # Act / Assert
    with pytest.raises(supabase_client.SupabaseRequestError) as exc:
        supabase_client.fetch_events_from_supabase(lookback_days=7)

    assert str(exc.value) == str(failure)


def test_upsert_events_to_supabase_aggregates_filters_and_batches(monkeypatch):
    """Upsert should aggregate duplicates, skip invalid rows, and write in chunks."""
    # Arrange
    monkeypatch.setattr(supabase_client, "_write_api_key", lambda: "write-key")
    posted_batches = []

    def _fake_chunked(items, _chunk_size):
        """Force deterministic chunking for payload verification."""
        return [items[:1], items[1:]]

    def _fake_request_json(method, path, api_key, payload=None, extra_headers=None):
        """Capture POST requests used by upsert batching."""
        posted_batches.append(
            {
                "method": method,
                "path": path,
                "api_key": api_key,
                "payload": payload,
                "extra_headers": extra_headers,
            },
        )

    monkeypatch.setattr(supabase_client, "_chunked", _fake_chunked)
    monkeypatch.setattr(supabase_client, "_request_json", _fake_request_json)

    records = [
        {
            "event_date": "2026-03-01",
            "project": "proj-a",
            "event_type": "commits",
            "count": 2,
        },
        {
            "event_date": "2026-03-01",
            "project": "proj-a",
            "event_type": "commits",
            "count": 3,
        },
        {
            "event_date": "2026-03-01",
            "project": "proj-b",
            "event_type": "mr_opened",
            "count": 1,
        },
        {"event_date": "", "project": "proj-c", "event_type": "commits", "count": 1},
        {
            "event_date": "2026-03-01",
            "project": "",
            "event_type": "commits",
            "count": 1,
        },
        {
            "event_date": "2026-03-01",
            "project": "proj-d",
            "event_type": "commits",
            "count": 0,
        },
    ]

    # Act
    inserted = supabase_client.upsert_events_to_supabase(records)

    # Assert
    assert inserted == 2
    assert len(posted_batches) == 2
    assert all(batch["method"] == "POST" for batch in posted_batches)
    assert all(batch["api_key"] == "write-key" for batch in posted_batches)
    assert all(
        "on_conflict=project,event_type,event_date" in batch["path"]
        for batch in posted_batches
    )
    assert all(
        batch["extra_headers"]["Prefer"] == "resolution=merge-duplicates,return=minimal"
        for batch in posted_batches
    )
    flattened = [item for batch in posted_batches for item in batch["payload"]]
    assert sorted(
        (row["project"], row["event_type"], row["count"]) for row in flattened
    ) == [
        ("proj-a", "commits", 5),
        ("proj-b", "mr_opened", 1),
    ]


def test_upsert_events_to_supabase_returns_zero_without_valid_payload(monkeypatch):
    """Upsert should no-op when all records are invalid after filtering."""
    # Arrange
    monkeypatch.setattr(supabase_client, "_write_api_key", lambda: "write-key")

    def _fake_request_json(*_, **__):
        """Fail test if network request is attempted for empty payload."""
        pytest.fail("_request_json should not be called for empty payload")

    monkeypatch.setattr(supabase_client, "_request_json", _fake_request_json)

    records = [
        {"event_date": None, "project": "proj-a", "event_type": "commits", "count": 1},
        {
            "event_date": "2026-03-01",
            "project": "",
            "event_type": "commits",
            "count": 1,
        },
        {
            "event_date": "2026-03-01",
            "project": "proj-a",
            "event_type": "commits",
            "count": 0,
        },
    ]

    # Act
    inserted = supabase_client.upsert_events_to_supabase(records)

    # Assert
    assert inserted == 0


def test_upsert_jira_events_to_supabase_uses_jira_table(monkeypatch):
    """Jira upsert should target the jira_events table."""
    # Arrange
    monkeypatch.setattr(supabase_client, "_write_api_key", lambda: "write-key")
    captured_paths = []

    def _fake_request_json(method, path, _api_key, payload=None, extra_headers=None):
        """Capture path used for Jira POST upsert requests."""
        captured_paths.append(path)
        assert method == "POST"
        assert payload is not None
        assert extra_headers is not None

    monkeypatch.setattr(supabase_client, "_request_json", _fake_request_json)

    records = [
        {
            "event_date": "2026-03-01",
            "project": "PROJ",
            "event_type": "jira_issues_closed",
            "count": 2,
        },
    ]

    # Act
    inserted = supabase_client.upsert_jira_events_to_supabase(records)

    # Assert
    assert inserted == 1
    assert len(captured_paths) == 1
    assert captured_paths[0].startswith("jira_events?on_conflict=")
