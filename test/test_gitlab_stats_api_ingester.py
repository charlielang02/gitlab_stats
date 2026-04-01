"""Unit tests for pure helper logic in the GitLab API ingester."""

from __future__ import annotations

from datetime import UTC
from datetime import date
from datetime import datetime
from types import SimpleNamespace

import pytest

from gitlab_stats import gitlab_stats_api_ingester as ingester

# pylint: disable=protected-access


def test_to_int_handles_valid_and_invalid_values():
    """Convert integers robustly and fall back to zero for invalid input."""
    # Arrange / Act / Assert
    assert ingester._to_int("7") == 7
    assert ingester._to_int(3.2) == 3
    assert ingester._to_int(None) == 0
    assert ingester._to_int("not-a-number") == 0


def test_api_window_swaps_explicit_period_boundaries():
    """Explicit period inputs should be normalized to start <= end."""
    # Arrange
    later = date(2026, 3, 5)
    earlier = date(2026, 3, 1)

    # Act
    period_start, period_end = ingester._api_window(
        period_start=later,
        period_end=earlier,
    )

    # Assert
    assert period_start == earlier
    assert period_end == later


def test_api_window_uses_lookback_days_when_period_not_provided(monkeypatch):
    """Missing periods should derive from lookback_days and current UTC date."""
    # Arrange
    frozen_now = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)

    def _now(*, tz=None):
        """Return a deterministic current datetime for window computations."""
        assert tz is UTC
        return frozen_now

    monkeypatch.setattr(ingester.config, "API_LOOKBACK_DAYS", "3")
    monkeypatch.setattr(ingester, "datetime", SimpleNamespace(now=_now))

    # Act
    period_start, period_end = ingester._api_window()

    # Assert
    assert period_start == date(2026, 3, 13)
    assert period_end == date(2026, 3, 15)


def test_event_counts_maps_branch_and_collaboration_actions():
    """Recognized action/target combinations should map to expected metric keys."""
    # Arrange
    push_event = {
        "action_name": "pushed",
        "target_type": "",
        "push_data": {"commit_count": 4, "ref_type": "branch", "ref": "feature/demo"},
    }
    mr_event = {"action_name": "opened", "target_type": "MergeRequest", "push_data": {}}
    comment_event = {
        "action_name": "commented on",
        "target_type": "note",
        "push_data": {},
    }

    # Act
    push_counts = ingester._event_counts_from_event(push_event)
    mr_counts = ingester._event_counts_from_event(mr_event)
    comment_counts = ingester._event_counts_from_event(comment_event)

    # Assert
    assert push_counts["commits"] == 4
    assert mr_counts["mr_opened"] == 1
    assert comment_counts["mr_commented"] == 1


def test_event_counts_treats_branch_creation_push_separately():
    """Branch-creation pushes should count as branch_created, not commits."""
    # Arrange
    event = {
        "action_name": "pushed new",
        "target_type": "",
        "push_data": {
            "commit_count": 10,
            "ref_type": "branch",
            "action": "created",
            "ref": "feature/new",
        },
    }

    # Act
    counts = ingester._event_counts_from_event(event)

    # Assert
    assert counts["branch_created"] == 1
    assert counts["commits"] == 0


def test_derive_project_totals_populates_totals_and_percentages():
    """Project totals should be derived from base metric buckets."""
    # Arrange
    project_data = {
        "commits": 4,
        "branch_created": 2,
        "branch_deleted": 1,
        "mr_opened": 1,
        "mr_merged": 1,
        "mr_approved": 0,
        "mr_commented": 1,
        "issue_opened": 0,
    }

    # Act
    ingester._derive_project_totals(project_data)

    # Assert
    assert project_data["code_contributions"] == 7
    assert project_data["collab_contributions"] == 3
    assert project_data["total_contributions"] == 10
    assert project_data["code_pct"] == 70.0
    assert project_data["collab_pct"] == 30.0


def test_aggregate_totals_combines_project_totals_and_percentages():
    """Aggregated totals should include summed counts and cross-project percentages."""
    # Arrange
    metrics = {
        "project-a": {
            "commits": 2,
            "branch_created": 1,
            "branch_deleted": 0,
            "mr_opened": 1,
            "mr_merged": 0,
            "mr_approved": 0,
            "mr_commented": 0,
            "issue_opened": 1,
        },
        "project-b": {
            "commits": 1,
            "branch_created": 0,
            "branch_deleted": 1,
            "mr_opened": 0,
            "mr_merged": 1,
            "mr_approved": 0,
            "mr_commented": 1,
            "issue_opened": 0,
        },
    }

    # Act
    totals = ingester._aggregate_totals(metrics)

    # Assert
    assert totals["total_contributions"] == 9
    assert totals["code_contributions"] == 5
    assert totals["collab_contributions"] == 4
    assert totals["code_pct"] == 55.6
    assert totals["collab_pct"] == 44.4


def test_resolve_user_id_uses_explicit_positive_value():
    """A positive explicit user id should bypass API user lookup."""
    # Arrange / Act
    resolved = ingester._resolve_user_id(123, "https://example.com", "token")

    # Assert
    assert resolved == 123


def test_resolve_user_id_fetches_authenticated_user_when_missing(monkeypatch):
    """Missing user id should resolve from the authenticated user payload."""
    # Arrange

    def _fake_fetch_authenticated_user(*_):
        """Return a deterministic user payload for id resolution."""
        return {"id": "77"}

    monkeypatch.setattr(
        ingester,
        "_fetch_authenticated_user",
        _fake_fetch_authenticated_user,
    )

    # Act
    resolved = ingester._resolve_user_id(None, "https://example.com", "token")

    # Assert
    assert resolved == 77


def test_request_json_rejects_non_http_schemes():
    """Requests should reject unsupported URL schemes early."""
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        ingester._request_json("ftp://example.com/user", "token")


def test_build_non_zero_metrics_filters_empty_and_tracks_dates(monkeypatch):
    """Only projects with positive totals should remain, with normalized event rows."""
    # Arrange

    def _fake_fetch_project_name(*_):
        """Return a stable project name for event metric aggregation."""
        return "project-a"

    monkeypatch.setattr(
        ingester,
        "_fetch_project_name",
        _fake_fetch_project_name,
    )

    events = [
        {
            "project_id": 1,
            "action_name": "pushed",
            "target_type": "",
            "created_at": "2026-03-05T12:00:00+00:00",
            "push_data": {"commit_count": 2, "ref_type": "branch", "ref": "feature/x"},
        },
        {
            "project_id": 1,
            "action_name": "noop",
            "target_type": "",
            "created_at": "2026-03-05T14:00:00+00:00",
            "push_data": {},
        },
    ]

    # Act
    metrics, records, has_real_dates = ingester._build_non_zero_metrics(
        events,
        "https://example.com",
        "token",
    )

    # Assert
    assert has_real_dates is True
    assert list(metrics.keys()) == ["project-a"]
    assert metrics["project-a"]["commits"] == 2
    assert metrics["project-a"]["total_contributions"] == 2
    assert len(records) == 1
    assert records[0]["event_type"] == "commits"
    assert records[0]["count"] == 2
    assert records[0]["event_date"] == date(2026, 3, 5)


def test_fetch_metrics_from_api_returns_none_when_ingestion_fails(monkeypatch):
    """Wrapper should return None when fetch_with_time fails."""
    # Arrange

    def _fake_fetch_metrics_from_api_with_time(**_):
        """Return None to emulate an ingestion failure path."""
        return

    monkeypatch.setattr(
        ingester,
        "fetch_metrics_from_api_with_time",
        _fake_fetch_metrics_from_api_with_time,
    )

    # Act
    result = ingester.fetch_metrics_from_api()

    # Assert
    assert result is None


def test_fetch_metrics_from_api_returns_metrics_tuple(monkeypatch):
    """Wrapper should project the first two values from the timed result tuple."""
    # Arrange
    mock_metrics = {"project-a": {"total_contributions": 4}}
    mock_totals = {"total_contributions": 4}

    def _fake_fetch_metrics_from_api_with_time(**_):
        """Return a complete tuple matching the API wrapper contract."""
        return mock_metrics, mock_totals, object(), {"source": "api"}

    monkeypatch.setattr(
        ingester,
        "fetch_metrics_from_api_with_time",
        _fake_fetch_metrics_from_api_with_time,
    )

    # Act
    metrics, totals = ingester.fetch_metrics_from_api() or ({}, {})

    # Assert
    assert metrics == mock_metrics
    assert totals == mock_totals


class _FakeApiResponse:  # pylint: disable=too-few-public-methods
    """Minimal context-managed HTTP response for API request helper tests."""

    def __init__(self, payload: str, headers: dict[str, str] | None = None):
        self._payload = payload
        self.headers = headers or {}

    def __enter__(self):
        """Return the fake response object in a context manager."""
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """Allow exiting context manager without suppressing exceptions."""
        return False

    def read(self):
        """Return encoded payload bytes."""
        return self._payload.encode("utf-8")


def test_request_json_with_headers_rejects_non_http_schemes():
    """Header-aware request helper should reject unsupported URL schemes."""
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        ingester._request_json_with_headers("ftp://example.com/events", "token")


def test_request_json_with_headers_returns_payload_and_headers(monkeypatch):
    """Header-aware helper should return decoded payload and normalized headers."""
    # Arrange

    def _fake_urlopen(*_, **__):
        """Return deterministic API payload and response headers."""
        return _FakeApiResponse(
            '[{"event":"x"}]',
            headers={"X-Next-Page": "2", "Content-Type": "application/json"},
        )

    monkeypatch.setattr(ingester, "urlopen", _fake_urlopen)

    # Act
    payload, headers = ingester._request_json_with_headers(
        "https://example.com/events",
        "token",
    )

    # Assert
    assert payload == [{"event": "x"}]
    assert headers["X-Next-Page"] == "2"
    assert headers["Content-Type"] == "application/json"


def test_fetch_authenticated_user_requires_dict_payload(monkeypatch):
    """Authenticated user helper should enforce object payload shape."""
    # Arrange
    monkeypatch.setattr(ingester, "_request_json", lambda *_: [{"id": 1}])

    # Act / Assert
    with pytest.raises(TypeError, match="Expected JSON object"):
        ingester._fetch_authenticated_user("https://example.com", "token")


def test_fetch_events_supports_next_page_header_with_zero_stop(monkeypatch):
    """Pagination should stop when X-Next-Page resolves to a non-positive value."""
    # Arrange
    monkeypatch.setattr(ingester.config, "API_EVENTS_PER_PAGE", 100)
    monkeypatch.setattr(ingester.config, "API_MAX_EVENT_PAGES", 3)

    def _fake_request_json_with_headers(*_):
        """Return one payload page and a terminating next-page header."""
        return [{"id": 1}], {"X-Next-Page": "0"}

    monkeypatch.setattr(
        ingester,
        "_request_json_with_headers",
        _fake_request_json_with_headers,
    )

    # Act
    events = ingester._fetch_events(
        "https://example.com",
        "token",
        42,
        "2026-03-01",
        "2026-03-10",
    )

    # Assert
    assert events == [{"id": 1}]


def test_fetch_metrics_from_api_with_time_returns_expected_tuple(monkeypatch):
    """API-with-time should return normalized metrics, totals, timeline, and meta."""
    # Arrange
    period_start = date(2026, 3, 1)
    period_end = date(2026, 3, 7)

    def _fake_read_setting(name: str):
        """Return deterministic API credentials."""
        if name == "GITLAB_API_TOKEN":
            return "token"
        if name == "GITLAB_API_BASE_URL":
            return "https://example.com"
        return ""

    captured: dict[str, str] = {}

    def _fake_fetch_events(**kwargs):
        """Capture query dates and return one API event placeholder."""
        captured["after_date"] = kwargs["after_date"]
        captured["before_date"] = kwargs["before_date"]
        return [{"event": "placeholder"}]

    monkeypatch.setattr(ingester, "_read_setting", _fake_read_setting)
    monkeypatch.setattr(ingester, "_resolve_user_id", lambda *_: 7)
    monkeypatch.setattr(ingester, "_api_window", lambda *_: (period_start, period_end))
    monkeypatch.setattr(ingester, "_fetch_events", _fake_fetch_events)
    monkeypatch.setattr(
        ingester,
        "_build_non_zero_metrics",
        lambda *_: ({"proj-a": {"total_contributions": 3}}, [{"count": 3}], True),
    )
    monkeypatch.setattr(
        ingester,
        "_aggregate_totals",
        lambda *_: {"total_contributions": 3},
    )
    monkeypatch.setattr(
        ingester,
        "build_timeline",
        lambda *_args, **_kwargs: ("timeline-df", {"window_label": "Last week"}),
    )

    # Act
    result = ingester.fetch_metrics_from_api_with_time()

    # Assert
    assert result is not None
    metrics, totals, timeline_df, timeline_meta = result
    assert metrics == {"proj-a": {"total_contributions": 3}}
    assert totals == {"total_contributions": 3}
    assert timeline_df == "timeline-df"
    assert timeline_meta == {"window_label": "Last week"}
    assert captured["after_date"] == "2026-03-01"
    assert captured["before_date"] == "2026-03-07"


def test_fetch_metrics_from_api_with_time_returns_none_without_credentials(monkeypatch):
    """API-with-time should short-circuit when credentials are missing."""
    # Arrange
    monkeypatch.setattr(ingester, "_read_setting", lambda *_: "")

    # Act
    result = ingester.fetch_metrics_from_api_with_time()

    # Assert
    assert result is None


def test_fetch_event_records_from_api_normalizes_and_filters_dates(monkeypatch):
    """Event-record fetch should stringify valid dates and drop missing-date rows."""
    # Arrange
    period_start = date(2026, 3, 1)
    period_end = date(2026, 3, 7)

    def _fake_read_setting(name: str):
        """Return deterministic API credentials."""
        if name == "GITLAB_API_TOKEN":
            return "token"
        if name == "GITLAB_API_BASE_URL":
            return "https://example.com"
        return ""

    monkeypatch.setattr(ingester, "_read_setting", _fake_read_setting)
    monkeypatch.setattr(ingester, "_resolve_user_id", lambda *_: 1)
    monkeypatch.setattr(ingester, "_api_window", lambda *_: (period_start, period_end))
    monkeypatch.setattr(
        ingester,
        "_fetch_events",
        lambda **_: [{"event": "placeholder"}],
    )
    monkeypatch.setattr(
        ingester,
        "_build_non_zero_metrics",
        lambda *_: (
            {"proj-a": {"total_contributions": 1}},
            [
                {
                    "event_date": date(2026, 3, 4),
                    "project": " proj-a ",
                    "event_type": " commits ",
                    "count": "2",
                },
                {
                    "event_date": None,
                    "project": "proj-b",
                    "event_type": "mr_opened",
                    "count": 1,
                },
            ],
            True,
        ),
    )

    # Act
    records = ingester.fetch_event_records_from_api()

    # Assert
    assert records == [
        {
            "event_date": "2026-03-04",
            "project": "proj-a",
            "event_type": "commits",
            "count": 2,
        },
    ]


def test_fetch_supabase_date_bounds_returns_none_on_request_error(monkeypatch):
    """Supabase bounds wrapper should return None when client request fails."""
    # Arrange

    def _fake_fetch_bounds():
        """Raise request error to cover wrapper exception branch."""
        raise ingester.SupabaseRequestError.network_failure("GET", "events", "timeout")

    monkeypatch.setattr(
        ingester,
        "fetch_event_date_bounds_from_supabase",
        _fake_fetch_bounds,
    )

    # Act
    bounds = ingester.fetch_supabase_date_bounds()

    # Assert
    assert bounds is None


def test_fetch_metrics_from_supabase_with_time_builds_timeline_and_source(monkeypatch):
    """Supabase-with-time should build normalized metrics and tag timeline source."""
    # Arrange
    query_start = date(2026, 3, 1)
    query_end = date(2026, 3, 7)
    monkeypatch.setattr(ingester.config, "SUPABASE_LOOKBACK_DAYS", "30")
    monkeypatch.setattr(ingester, "_api_window", lambda *_: (query_start, query_end))
    monkeypatch.setattr(
        ingester,
        "fetch_events_from_supabase",
        lambda **_: [
            {
                "event_date": "2026-03-03",
                "project": "proj-a",
                "event_type": "commits",
                "count": 2,
            },
            {
                "event_date": "2026-03-05",
                "project": "proj-a",
                "event_type": "mr_opened",
                "count": 1,
            },
            {
                "event_date": "not-a-date",
                "project": "proj-a",
                "event_type": "issue_opened",
                "count": 1,
            },
        ],
    )
    monkeypatch.setattr(
        ingester,
        "build_timeline",
        lambda *_args, **_kwargs: ("supabase-timeline", {"window_label": "Custom"}),
    )

    # Act
    result = ingester.fetch_metrics_from_supabase_with_time()

    # Assert
    assert result is not None
    metrics, totals, timeline_df, timeline_meta = result
    assert metrics["proj-a"]["total_contributions"] == 4
    assert totals["total_contributions"] == 4
    assert timeline_df == "supabase-timeline"
    assert timeline_meta["window_label"] == "Custom"
    assert timeline_meta["source"] == "supabase"
