"""Unit tests for Jira API ingester helpers."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

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
