"""Unit tests for timeline utility helpers."""

from __future__ import annotations

from datetime import date

from gitlab_stats.dashboard_utils.timeline_utils import _empty_timeline_frame
from gitlab_stats.dashboard_utils.timeline_utils import build_timeline


def test_empty_timeline_frame_has_expected_columns_and_no_rows():
    """Empty frame should expose stable schema for downstream renderers."""
    # Arrange / Act
    frame = _empty_timeline_frame()

    # Assert
    assert frame.empty
    assert list(frame.columns) == [
        "event_date",
        "commits",
        "branch_created",
        "branch_deleted",
        "mr_opened",
        "mr_merged",
        "mr_approved",
        "mr_commented",
        "issue_opened",
        "code_contributions",
        "collab_contributions",
        "total_contributions",
    ]


def test_build_timeline_returns_empty_when_no_event_records():
    """No input records should return empty timeline with baseline metadata."""
    # Arrange / Act
    timeline, meta = build_timeline([], has_real_dates=True)

    # Assert
    assert timeline.empty
    assert meta == {"has_real_dates": False, "using_synthetic_timeline": False}


def test_build_timeline_includes_period_metadata_for_valid_boundaries():
    """When period bounds are valid, expected window metadata is emitted."""
    # Arrange
    start = date(2026, 3, 1)
    end = date(2026, 3, 3)

    # Act
    timeline, meta = build_timeline(
        [],
        has_real_dates=False,
        period_start=start,
        period_end=end,
    )

    # Assert
    assert timeline.empty
    assert meta["period_start"] == "2026-03-01"
    assert meta["period_end"] == "2026-03-03"
    assert meta["expected_days"] == 3
    assert meta["has_real_dates"] is False


def test_build_timeline_ignores_invalid_period_boundaries():
    """Invalid period bounds should not produce period metadata."""
    # Arrange
    start = date(2026, 3, 10)
    end = date(2026, 3, 1)

    # Act
    timeline, meta = build_timeline(
        [],
        has_real_dates=False,
        period_start=start,
        period_end=end,
    )

    # Assert
    assert timeline.empty
    assert "period_start" not in meta
    assert "period_end" not in meta
    assert "expected_days" not in meta


def test_build_timeline_returns_empty_when_has_real_dates_is_false():
    """Records with has_real_dates=False should not generate timeline output."""
    # Arrange
    event_records: list[dict[str, object]] = [
        {
            "event_date": "2026-03-10",
            "event_type": "commits",
            "count": 2,
        },
    ]

    # Act
    timeline, meta = build_timeline(event_records, has_real_dates=False)

    # Assert
    assert timeline.empty
    assert meta["has_real_dates"] is False


def test_build_timeline_drops_invalid_dates_and_reports_empty_when_none_remain():
    """Invalid date records should be discarded safely."""
    # Arrange
    event_records: list[dict[str, object]] = [
        {"event_date": "not-a-date", "event_type": "commits", "count": 3},
        {"event_date": None, "event_type": "mr_opened", "count": 1},
    ]

    # Act
    timeline, meta = build_timeline(event_records, has_real_dates=True)

    # Assert
    assert timeline.empty
    assert meta["has_real_dates"] is False


def test_build_timeline_aggregates_metrics_and_totals_for_same_day_events():
    """Multiple records on same day should be aggregated per metric and totals."""
    # Arrange
    event_records: list[dict[str, object]] = [
        {"event_date": "2026-03-10", "event_type": "commits", "count": 2},
        {"event_date": "2026-03-10", "event_type": "commits", "count": 3},
        {"event_date": "2026-03-10", "event_type": "mr_opened", "count": 1},
    ]

    # Act
    timeline, meta = build_timeline(event_records, has_real_dates=True)

    # Assert
    assert len(timeline) == 1
    row = timeline.iloc[0]
    assert int(row["commits"]) == 5
    assert int(row["mr_opened"]) == 1
    assert int(row["code_contributions"]) == 5
    assert int(row["collab_contributions"]) == 1
    assert int(row["total_contributions"]) == 6
    assert meta["has_real_dates"] is True
    assert meta["timeline_days"] == 1
    assert meta["active_days"] == 1


def test_build_timeline_reindexes_full_period_and_fills_missing_days_with_zeros():
    """Period reindex should include inactive days between boundaries."""
    # Arrange
    start = date(2026, 3, 1)
    end = date(2026, 3, 3)
    event_records: list[dict[str, object]] = [
        {"event_date": "2026-03-02", "event_type": "commits", "count": 4},
    ]

    # Act
    timeline, meta = build_timeline(
        event_records,
        has_real_dates=True,
        period_start=start,
        period_end=end,
    )

    # Assert
    assert len(timeline) == 3
    assert timeline.iloc[0]["event_date"].isoformat() == "2026-03-01"
    assert timeline.iloc[1]["event_date"].isoformat() == "2026-03-02"
    assert timeline.iloc[2]["event_date"].isoformat() == "2026-03-03"
    assert int(timeline.iloc[0]["total_contributions"]) == 0
    assert int(timeline.iloc[1]["total_contributions"]) == 4
    assert int(timeline.iloc[2]["total_contributions"]) == 0
    assert meta["expected_days"] == 3
    assert meta["timeline_days"] == 3
    assert meta["active_days"] == 1


def test_build_timeline_coerces_non_numeric_counts_to_zero():
    """Non-numeric count values should coerce to zero instead of crashing."""
    # Arrange
    event_records: list[dict[str, object]] = [
        {"event_date": "2026-03-10", "event_type": "commits", "count": "abc"},
    ]

    # Act
    timeline, meta = build_timeline(event_records, has_real_dates=True)

    # Assert
    assert len(timeline) == 1
    assert int(timeline.iloc[0]["commits"]) == 0
    assert int(timeline.iloc[0]["total_contributions"]) == 0
    assert meta["active_days"] == 0
