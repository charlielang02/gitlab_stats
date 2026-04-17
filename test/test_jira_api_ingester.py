"""Unit tests for Jira API ingester helpers."""

from __future__ import annotations

from datetime import UTC
from datetime import date
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from gitlab_stats import jira_api_ingester as jira_ingester

# pylint: disable=protected-access


def test_fetch_event_records_from_jira_returns_empty_when_credentials_missing(
    monkeypatch,
):
    """Missing Jira credentials should skip sync gracefully."""
    # Arrange
    monkeypatch.setattr(jira_ingester, "_read_jira_credentials", lambda: None)

    # Act
    records = jira_ingester.fetch_event_records_from_jira()

    # Assert
    assert records == []


def test_jira_api_path_uses_v2(monkeypatch):  # pylint: disable=unused-argument
    """Jira API path should always use v2 endpoint."""
    # Arrange/Act
    path = jira_ingester._jira_api_path("myself")

    # Assert
    assert path == "rest/api/2/myself"


def test_fetch_authenticated_user_uses_v2_api_path(monkeypatch):
    """Authenticated-user call should use v2 API path and handle key format."""
    # Arrange
    captured = {"path": None}

    def _fake_request_json(_base_url, path, _api_token, query_params=None):
        captured["path"] = path
        assert query_params is None
        # v2 returns key instead of accountId
        return {"key": "JIRAUSER28502", "name": "user@example.com"}

    monkeypatch.setattr(jira_ingester, "_request_json", _fake_request_json)

    # Act
    user_id = jira_ingester._fetch_authenticated_user(
        "https://jira.example.com",
        "token",
    )

    # Assert
    assert user_id == "JIRAUSER28502"
    assert captured["path"] == "rest/api/2/myself"


def test_fetch_issues_uses_v2_api_path(monkeypatch):
    """Issue search should use v2 API path."""
    # Arrange
    captured = {"path": None}

    def _fake_request_json(_base_url, path, _api_token, query_params=None):
        captured["path"] = path
        assert query_params is not None
        return {"issues": [], "total": 0}

    monkeypatch.setattr(jira_ingester, "_request_json", _fake_request_json)

    # Act
    issues = jira_ingester._fetch_issues(
        "https://jira.example.com",
        "token",
        "assignee=currentUser()",
        "customfield_10016",
    )

    # Assert
    assert not issues
    assert captured["path"] == "rest/api/2/search"


def test_fetch_event_records_from_jira_aggregates_project_event_records(monkeypatch):
    """Jira issues should be normalized into per-day per-project event records."""
    # Arrange
    monkeypatch.setattr(
        jira_ingester,
        "_read_jira_credentials",
        lambda: ("https://jira.example.com", "user@example.com", "token"),
    )
    monkeypatch.setattr(
        jira_ingester,
        "_fetch_authenticated_user",
        lambda *_: "JIRAUSER28502",
    )
    monkeypatch.setattr(
        jira_ingester,
        "_fetch_issues",
        lambda *_: [
            {
                "fields": {
                    "project": {"key": "PROJ"},
                    "created": "2026-04-10T12:00:00+00:00",
                    "resolutiondate": "2026-04-11T15:30:00+00:00",
                    "customfield_10016": 5,
                    "comment": {
                        "comments": [
                            {
                                "author": {"key": "JIRAUSER28502"},
                                "created": "2026-04-11T16:00:00+00:00",
                            },
                            {
                                "author": {"key": "JIRAUSER99999"},
                                "created": "2026-04-11T16:05:00+00:00",
                            },
                        ],
                    },
                },
            },
        ],
    )

    def _fake_read_setting(name: str) -> str:
        if name == "JIRA_STORY_POINTS_FIELD":
            return "customfield_10016"
        return ""

    monkeypatch.setattr(jira_ingester, "read_setting", _fake_read_setting)

    # Act
    records = jira_ingester.fetch_event_records_from_jira(
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
    )

    # Assert
    assert records is not None
    normalized = {
        (record["event_date"], record["project"], record["event_type"]): record["count"]
        for record in records
    }
    assert normalized[("2026-04-10", "PROJ", "jira_issues_assigned")] == 1
    assert normalized[("2026-04-11", "PROJ", "jira_issues_closed")] == 1
    assert normalized[("2026-04-11", "PROJ", "jira_comments")] == 1
    assert normalized[("2026-04-11", "PROJ", "jira_story_points_closed")] == 5


def test_fetch_event_records_from_jira_returns_none_when_user_resolution_fails(
    monkeypatch,
):
    """Failure to resolve current Jira user should fail sync for visibility."""
    # Arrange
    monkeypatch.setattr(
        jira_ingester,
        "_read_jira_credentials",
        lambda: ("https://jira.example.com", "user@example.com", "token"),
    )
    monkeypatch.setattr(jira_ingester, "_fetch_authenticated_user", lambda *_: None)

    # Act
    records = jira_ingester.fetch_event_records_from_jira(
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
    )

    # Assert
    assert records is None


def test_request_json_uses_bearer_auth(monkeypatch):
    """Request should always use Bearer token authentication."""
    # Arrange
    captured_headers = {}

    def _fake_urlopen(request, timeout=None):  # pylint: disable=unused-argument
        captured_headers["auth"] = request.headers.get("Authorization", "")
        # Mock response
        response = MagicMock()
        response.read.return_value = b'{"result": "ok"}'
        response.__enter__.return_value = response
        response.__exit__.return_value = None
        return response

    monkeypatch.setattr(jira_ingester, "urlopen", _fake_urlopen)

    # Act
    result = jira_ingester._request_json(
        "https://jira.example.com",
        "rest/api/2/myself",
        "my-bearer-token",
    )

    # Assert
    assert result == {"result": "ok"}
    assert captured_headers["auth"] == "Bearer my-bearer-token"


def test_jira_window_swaps_when_period_bounds_are_reversed():
    """Window helper should normalize reversed explicit period bounds."""
    # Arrange
    start = date(2026, 4, 30)
    end = date(2026, 4, 1)

    # Act
    window_start, window_end = jira_ingester._jira_window(start, end)

    # Assert
    assert window_start == date(2026, 4, 1)
    assert window_end == date(2026, 4, 30)


def test_jira_window_uses_configured_lookback_when_bounds_missing(monkeypatch):
    """Window helper should fall back to lookback days when bounds are omitted."""
    # Arrange
    monkeypatch.setattr(jira_ingester.config, "API_LOOKBACK_DAYS", 7)
    frozen_now = datetime(2026, 4, 17, tzinfo=UTC)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen_now if tz else frozen_now.replace(tzinfo=None)

    monkeypatch.setattr(jira_ingester, "datetime", _FrozenDatetime)

    # Act
    window_start, window_end = jira_ingester._jira_window()

    # Assert
    assert window_end == date(2026, 4, 17)
    assert window_start == date(2026, 4, 11)


def test_parse_iso_datetime_handles_invalid_values():
    """Datetime parser should return None for empty and malformed timestamps."""
    assert jira_ingester._parse_iso_datetime("") is None
    assert jira_ingester._parse_iso_datetime("not-a-date") is None


def test_parse_iso_datetime_adds_utc_for_naive_values():
    """Datetime parser should normalize naive datetimes into UTC."""
    parsed = jira_ingester._parse_iso_datetime("2026-04-17T12:34:56")
    assert parsed is not None
    assert parsed.tzinfo == UTC


def test_build_jql_quotes_project_keys():
    """JQL builder should include sanitized project list when provided."""
    jql = jira_ingester._build_jql(
        date(2026, 4, 1),
        date(2026, 4, 30),
        "PROJ, PROJ-2, name with space",
    )

    assert "assignee = currentUser()" in jql
    assert 'updated >= "2026-04-01"' in jql
    assert 'updated <= "2026-04-30"' in jql
    assert 'project in ("PROJ", "PROJ-2", "name%20with%20space")' in jql


def test_fetch_issues_raises_type_error_when_payload_is_not_mapping(monkeypatch):
    """Issue fetch should fail fast when Jira search payload shape is invalid."""
    monkeypatch.setattr(jira_ingester, "_request_json", lambda *_args, **_kwargs: [])

    with pytest.raises(TypeError, match="Expected object payload"):
        jira_ingester._fetch_issues(
            "https://jira.example.com",
            "token",
            "assignee=currentUser()",
            "customfield_10016",
        )


def test_fetch_issues_supports_pagination(monkeypatch):
    """Issue fetch should continue paging until the total issue count is consumed."""
    calls: list[int] = []

    def _fake_request(_base_url, _path, _token, query_params=None):
        assert query_params is not None
        calls.append(query_params["startAt"])
        if query_params["startAt"] == 0:
            return {
                "issues": [{"id": 1}, {"id": 2}],
                "total": 3,
            }
        return {
            "issues": [{"id": 3}],
            "total": 3,
        }

    monkeypatch.setattr(jira_ingester, "_request_json", _fake_request)

    issues = jira_ingester._fetch_issues(
        "https://jira.example.com",
        "token",
        "assignee=currentUser()",
        "customfield_10016",
    )

    assert calls == [0, 2]
    assert [item["id"] for item in issues] == [1, 2, 3]


def test_build_jira_metrics_from_rows_skips_invalid_rows_and_builds_totals():
    """Metrics rebuilder should aggregate valid rows and ignore malformed records."""
    rows = [
        {
            "event_date": "2026-04-10",
            "project": "PROJ",
            "event_type": "jira_issues_assigned",
            "count": 2,
        },
        {
            "event_date": "2026-04-11",
            "project": "PROJ",
            "event_type": "jira_issues_closed",
            "count": 1,
        },
        {
            "event_date": "2026-04-11",
            "project": "PROJ",
            "event_type": "jira_comments",
            "count": 3,
        },
        {
            "event_date": "2026-04-11",
            "project": "PROJ",
            "event_type": "jira_story_points_closed",
            "count": 5,
        },
        {
            "event_date": "bad-date",
            "project": "PROJ",
            "event_type": "jira_comments",
            "count": 1,
        },
        {
            "event_date": "2026-04-11",
            "project": "",
            "event_type": "jira_comments",
            "count": 2,
        },
        {
            "event_date": "2026-04-11",
            "project": "PROJ",
            "event_type": "unsupported",
            "count": 2,
        },
    ]

    metrics, totals, timeline_df, timeline_meta = (
        jira_ingester._build_jira_metrics_from_rows(
            rows,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
        )
    )

    assert set(metrics.keys()) == {"PROJ"}
    assert metrics["PROJ"]["jira_issues_assigned"] == 2
    assert metrics["PROJ"]["jira_issues_closed"] == 1
    assert metrics["PROJ"]["jira_comments"] == 4
    assert metrics["PROJ"]["jira_story_points_closed"] == 5
    assert metrics["PROJ"]["total_jira_activity"] == 12
    assert totals["total_jira_activity"] == 12
    assert totals["projects_touched"] == 1
    assert timeline_meta["has_real_dates"] is True
    assert "total_jira_activity" in timeline_df.columns


def test_extract_project_key_handles_non_mapping_fields():
    """Project extractor should return an empty key for malformed project blocks."""
    assert jira_ingester._extract_project_key({"project": "not-a-dict"}) == ""


def test_process_issue_dates_counts_assignment_resolution_and_story_points():
    """Issue-date processor should increment assignment and resolution counters."""
    counters = {}
    fields = {
        "created": "2026-04-10T12:00:00+00:00",
        "resolutiondate": "2026-04-12T08:30:00+00:00",
        "customfield_10016": 4.6,
    }
    defaulted = jira_ingester.defaultdict(int, counters)

    jira_ingester._process_issue_dates(
        defaulted,
        fields,
        "PROJ",
        date(2026, 4, 1),
        date(2026, 4, 30),
        "customfield_10016",
    )

    assert defaulted[(date(2026, 4, 10), "PROJ", "jira_issues_assigned")] == 1
    assert defaulted[(date(2026, 4, 12), "PROJ", "jira_issues_closed")] == 1
    assert defaulted[(date(2026, 4, 12), "PROJ", "jira_story_points_closed")] == 5


def test_process_issue_comments_counts_only_current_user_in_window():
    """Comment processor should only count comments authored by the resolved account."""
    counters = jira_ingester.defaultdict(int)
    fields = {
        "comment": {
            "comments": [
                {
                    "author": {"key": "ME"},
                    "created": "2026-04-11T10:00:00+00:00",
                },
                {
                    "author": {"key": "OTHER"},
                    "created": "2026-04-11T11:00:00+00:00",
                },
                {
                    "author": {"key": "ME"},
                    "created": "2026-03-01T11:00:00+00:00",
                },
            ],
        },
    }

    jira_ingester._process_issue_comments(
        counters,
        fields,
        "PROJ",
        "ME",
        date(2026, 4, 1),
        date(2026, 4, 30),
    )

    assert counters[(date(2026, 4, 11), "PROJ", "jira_comments")] == 1


def test_fetch_event_records_from_jira_returns_empty_on_malformed_issue_fields(
    monkeypatch,
):
    """Malformed issue fields should be ignored and produce an empty record set."""
    monkeypatch.setattr(
        jira_ingester,
        "_read_jira_credentials",
        lambda: ("https://jira.example.com", "user@example.com", "token"),
    )
    monkeypatch.setattr(jira_ingester, "_fetch_authenticated_user", lambda *_: "ME")
    monkeypatch.setattr(
        jira_ingester,
        "_fetch_issues",
        lambda *_: [{"fields": "bad-shape"}],
    )
    monkeypatch.setattr(jira_ingester, "read_setting", lambda *_: "")

    records = jira_ingester.fetch_event_records_from_jira(
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
    )

    assert records == []


def test_fetch_jira_metrics_from_supabase_with_time_returns_none_when_no_rows(
    monkeypatch,
):
    """Supabase loader should return None when there are no Jira event rows."""
    monkeypatch.setattr(jira_ingester.config, "SUPABASE_LOOKBACK_DAYS", 30)
    monkeypatch.setattr(
        jira_ingester,
        "fetch_jira_events_from_supabase",
        lambda **_kwargs: [],
    )

    result = jira_ingester.fetch_jira_metrics_from_supabase_with_time()

    assert result is None


def test_fetch_jira_metrics_from_supabase_with_time_returns_none_when_metrics_empty(
    monkeypatch,
):
    """Supabase loader should return None when rows cannot produce project metrics."""
    monkeypatch.setattr(jira_ingester.config, "SUPABASE_LOOKBACK_DAYS", 30)
    monkeypatch.setattr(
        jira_ingester,
        "fetch_jira_events_from_supabase",
        lambda **_kwargs: [{"event_type": "unsupported", "count": 1}],
    )

    result = jira_ingester.fetch_jira_metrics_from_supabase_with_time()

    assert result is None


def test_fetch_jira_metrics_from_supabase_with_time_happy_path(monkeypatch):
    """Supabase loader should return metrics, totals, timeline, and metadata source."""
    monkeypatch.setattr(jira_ingester.config, "SUPABASE_LOOKBACK_DAYS", 30)
    rows = [
        {
            "event_date": "2026-04-10",
            "project": "PROJ",
            "event_type": "jira_issues_assigned",
            "count": 3,
        },
        {
            "event_date": "2026-04-11",
            "project": "PROJ",
            "event_type": "jira_issues_closed",
            "count": 2,
        },
    ]
    monkeypatch.setattr(
        jira_ingester,
        "fetch_jira_events_from_supabase",
        lambda **_kwargs: rows,
    )

    result = jira_ingester.fetch_jira_metrics_from_supabase_with_time(
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
    )
    assert result is not None
    metrics, totals, timeline_df, timeline_meta = result

    assert metrics["PROJ"]["jira_issues_assigned"] == 3
    assert metrics["PROJ"]["jira_issues_closed"] == 2
    assert totals["projects_touched"] == 1
    assert timeline_meta["source"] == "supabase"
    assert not timeline_df.empty


def test_fetch_jira_metrics_from_supabase_with_time_returns_none_on_supabase_error(
    monkeypatch,
):
    """Supabase loader should handle backend request/configuration exceptions."""
    monkeypatch.setattr(
        jira_ingester,
        "fetch_jira_events_from_supabase",
        lambda **_kwargs: (_ for _ in ()).throw(
            jira_ingester.SupabaseRequestError("x"),
        ),
    )

    result = jira_ingester.fetch_jira_metrics_from_supabase_with_time()

    assert result is None
