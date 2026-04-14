"""Unit tests for Supabase sync CLI flow."""

from __future__ import annotations

import pytest

from gitlab_stats.database import supabase_sync


def test_run_sync_returns_one_when_api_fetch_fails(monkeypatch):
    """Return non-zero exit code when API event fetch fails."""
    # Arrange
    monkeypatch.setattr(supabase_sync, "fetch_event_records_from_api", lambda: None)
    monkeypatch.setattr(supabase_sync, "fetch_event_records_from_jira", list)

    # Act
    result = supabase_sync.run_sync()

    # Assert
    assert result == 1


def test_sync_sources_defaults_to_both_when_flags_enabled(monkeypatch):
    """Default sync mode should include both sources when Jira is enabled."""
    # Arrange
    monkeypatch.setattr(
        supabase_sync,
        "read_setting",
        lambda name: "" if name == "SYNC_SOURCES" else "true",
    )

    # Act
    sources = supabase_sync._sync_sources()

    # Assert
    assert sources == {"gitlab", "jira"}


def test_sync_sources_respects_gitlab_only_explicit_selection(monkeypatch):
    """SYNC_SOURCES=gitlab should disable Jira for a GitLab-only dev sync."""
    # Arrange
    monkeypatch.setattr(
        supabase_sync,
        "read_setting",
        lambda name: "gitlab" if name == "SYNC_SOURCES" else "true",
    )

    # Act
    sources = supabase_sync._sync_sources()

    # Assert
    assert sources == {"gitlab"}


def test_run_sync_returns_zero_when_no_event_records(monkeypatch):
    """Return success when both API sources return empty event lists."""
    # Arrange
    monkeypatch.setattr(supabase_sync, "fetch_event_records_from_api", list)
    monkeypatch.setattr(supabase_sync, "fetch_event_records_from_jira", list)

    # Act
    result = supabase_sync.run_sync()

    # Assert
    assert result == 0


def test_run_sync_gitlab_only_skips_jira(monkeypatch):
    """GitLab-only mode should skip Jira fetch and Jira upsert."""
    # Arrange
    captured = {"gitlab": None, "jira": None}
    monkeypatch.setattr(
        supabase_sync,
        "read_setting",
        lambda name: "gitlab" if name == "SYNC_SOURCES" else "",
    )
    monkeypatch.setattr(
        supabase_sync,
        "fetch_event_records_from_api",
        lambda: [
            {
                "event_date": "2026-03-20",
                "project": "project-a",
                "event_type": "commits",
                "count": 1,
            },
        ],
    )
    monkeypatch.setattr(
        supabase_sync,
        "upsert_events_to_supabase",
        lambda records: captured.__setitem__("gitlab", records) or len(records),
    )
    monkeypatch.setattr(
        supabase_sync,
        "upsert_jira_events_to_supabase",
        lambda records: captured.__setitem__("jira", records) or len(records),
    )

    # Act
    result = supabase_sync.run_sync()

    # Assert
    assert result == 0
    assert captured["gitlab"] is not None
    assert captured["jira"] is None


def test_run_sync_upserts_records_and_returns_zero(monkeypatch):
    """Upsert GitLab and Jira records to their own tables and return success."""
    # Arrange
    gitlab_records = [
        {
            "event_date": "2026-03-20",
            "project": "project-a",
            "event_type": "commits",
            "count": 3,
        },
    ]
    jira_records = [
        {
            "event_date": "2026-03-20",
            "project": "PROJ",
            "event_type": "jira_issues_closed",
            "count": 1,
        },
    ]
    captured = {"gitlab": None, "jira": None}

    def _fake_gitlab_fetch():
        return gitlab_records

    def _fake_jira_fetch():
        return jira_records

    def _fake_gitlab_upsert(records):
        captured["gitlab"] = records
        return len(records)

    def _fake_jira_upsert(records):
        captured["jira"] = records
        return len(records)

    monkeypatch.setattr(
        supabase_sync,
        "fetch_event_records_from_api",
        _fake_gitlab_fetch,
    )
    monkeypatch.setattr(
        supabase_sync,
        "fetch_event_records_from_jira",
        _fake_jira_fetch,
    )
    monkeypatch.setattr(
        supabase_sync,
        "upsert_events_to_supabase",
        _fake_gitlab_upsert,
    )
    monkeypatch.setattr(
        supabase_sync,
        "upsert_jira_events_to_supabase",
        _fake_jira_upsert,
    )

    # Act
    result = supabase_sync.run_sync()

    # Assert
    assert result == 0
    assert captured["gitlab"] == gitlab_records
    assert captured["jira"] == jira_records


def test_run_sync_allows_only_gitlab_rows(monkeypatch):
    """Sync should upsert GitLab rows even when Jira returns no rows."""
    # Arrange
    captured = {"gitlab": None, "jira": None}
    monkeypatch.setattr(
        supabase_sync,
        "fetch_event_records_from_api",
        lambda: [
            {
                "event_date": "2026-03-20",
                "project": "project-a",
                "event_type": "commits",
                "count": 1,
            },
        ],
    )
    monkeypatch.setattr(supabase_sync, "fetch_event_records_from_jira", list)
    monkeypatch.setattr(
        supabase_sync,
        "upsert_events_to_supabase",
        lambda records: captured.__setitem__("gitlab", records) or len(records),
    )
    monkeypatch.setattr(
        supabase_sync,
        "upsert_jira_events_to_supabase",
        lambda records: captured.__setitem__("jira", records) or len(records),
    )

    # Act
    result = supabase_sync.run_sync()

    # Assert
    assert result == 0
    assert captured["gitlab"] is not None
    assert not captured["jira"]


def test_run_sync_allows_only_jira_rows(monkeypatch):
    """Sync should upsert Jira rows even when GitLab returns no rows."""
    # Arrange
    captured = {"gitlab": None, "jira": None}
    monkeypatch.setattr(supabase_sync, "fetch_event_records_from_api", list)
    monkeypatch.setattr(
        supabase_sync,
        "fetch_event_records_from_jira",
        lambda: [
            {
                "event_date": "2026-03-20",
                "project": "PROJ",
                "event_type": "jira_issues_closed",
                "count": 1,
            },
        ],
    )
    monkeypatch.setattr(
        supabase_sync,
        "upsert_events_to_supabase",
        lambda records: captured.__setitem__("gitlab", records) or len(records),
    )
    monkeypatch.setattr(
        supabase_sync,
        "upsert_jira_events_to_supabase",
        lambda records: captured.__setitem__("jira", records) or len(records),
    )

    # Act
    result = supabase_sync.run_sync()

    # Assert
    assert result == 0
    assert not captured["gitlab"]
    assert captured["jira"] is not None


def test_run_sync_returns_one_when_jira_fetch_fails(monkeypatch):
    """Return non-zero exit code when Jira event fetch fails."""
    # Arrange
    monkeypatch.setattr(supabase_sync, "fetch_event_records_from_api", list)
    monkeypatch.setattr(supabase_sync, "fetch_event_records_from_jira", lambda: None)

    # Act
    result = supabase_sync.run_sync()

    # Assert
    assert result == 1


def test_run_sync_propagates_upsert_exception(monkeypatch):
    """Surface upsert failures so callers can detect hard sync errors."""
    # Arrange
    monkeypatch.setattr(
        supabase_sync,
        "fetch_event_records_from_api",
        lambda: [
            {
                "event_date": "2026-03-20",
                "project": "p",
                "event_type": "commits",
                "count": 1,
            },
        ],
    )
    monkeypatch.setattr(supabase_sync, "fetch_event_records_from_jira", list)

    def _raise_upsert(_records):
        raise RuntimeError("upsert failed")

    monkeypatch.setattr(supabase_sync, "upsert_events_to_supabase", _raise_upsert)
    monkeypatch.setattr(supabase_sync, "upsert_jira_events_to_supabase", list)

    # Act / Assert
    with pytest.raises(RuntimeError, match="upsert failed"):
        supabase_sync.run_sync()


def test_main_loads_dotenv_configures_logging_and_exits_with_sync_code(monkeypatch):
    """Main entrypoint should set logging, load env, and exit with run_sync code."""
    # Arrange
    calls = {"basic_config": [], "load_dotenv": 0}

    def _fake_basic_config(**kwargs):
        calls["basic_config"].append(kwargs)

    def _fake_load_dotenv():
        calls["load_dotenv"] += 1

    monkeypatch.setattr(supabase_sync.logging, "basicConfig", _fake_basic_config)
    monkeypatch.setattr(supabase_sync, "load_dotenv", _fake_load_dotenv)
    monkeypatch.setattr(supabase_sync, "run_sync", lambda: 7)

    # Act / Assert
    with pytest.raises(SystemExit) as exited:
        supabase_sync.main()

    assert exited.value.code == 7
    assert calls["load_dotenv"] == 1
    assert calls["basic_config"] == [{"level": supabase_sync.logging.INFO}]
