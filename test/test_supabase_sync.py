"""Unit tests for Supabase sync CLI flow."""

from __future__ import annotations

import pytest

from gitlab_stats.database import supabase_sync


def test_run_sync_returns_one_when_api_fetch_fails(monkeypatch):
    """Return non-zero exit code when API event fetch fails."""
    # Arrange
    monkeypatch.setattr(supabase_sync, "fetch_event_records_from_api", lambda: None)

    # Act
    result = supabase_sync.run_sync()

    # Assert
    assert result == 1


def test_run_sync_returns_zero_when_no_event_records(monkeypatch):
    """Return success when API returns an empty event list."""
    # Arrange
    monkeypatch.setattr(supabase_sync, "fetch_event_records_from_api", list)

    # Act
    result = supabase_sync.run_sync()

    # Assert
    assert result == 0


def test_run_sync_upserts_records_and_returns_zero(monkeypatch):
    """Upsert records and return success when API returns data."""
    # Arrange
    event_records = [
        {
            "event_date": "2026-03-20",
            "project": "project-a",
            "event_type": "commits",
            "count": 3,
        },
    ]
    captured = {}

    def _fake_fetch():
        return event_records

    def _fake_upsert(records):
        captured["records"] = records
        return 1

    monkeypatch.setattr(supabase_sync, "fetch_event_records_from_api", _fake_fetch)
    monkeypatch.setattr(supabase_sync, "upsert_events_to_supabase", _fake_upsert)

    # Act
    result = supabase_sync.run_sync()

    # Assert
    assert result == 0
    assert captured["records"] == event_records


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

    def _raise_upsert(_records):
        raise RuntimeError("upsert failed")

    monkeypatch.setattr(supabase_sync, "upsert_events_to_supabase", _raise_upsert)

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
