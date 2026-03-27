"""Timeline utilities for behavior analytics."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from gitlab_stats.dashboard_utils.metrics_schema import BASE_METRIC_KEYS

if TYPE_CHECKING:
    from datetime import date


def _empty_timeline_frame() -> pd.DataFrame:
    columns = [
        "event_date",
        *BASE_METRIC_KEYS,
        "code_contributions",
        "collab_contributions",
        "total_contributions",
    ]
    return pd.DataFrame(columns=columns)


def build_timeline(
    event_records: list[dict[str, object]],
    has_real_dates: bool,
    period_start: date | None = None,
    period_end: date | None = None,
) -> tuple[pd.DataFrame, dict[str, bool | int | str]]:
    """Build daily timeline aggregates from normalized event records."""
    meta: dict[str, bool | int | str] = {
        "has_real_dates": False,
        "using_synthetic_timeline": False,
    }
    if (
        period_start is not None
        and period_end is not None
        and period_start <= period_end
    ):
        meta["period_start"] = period_start.isoformat()
        meta["period_end"] = period_end.isoformat()
        meta["expected_days"] = (period_end - period_start).days + 1

    if not event_records:
        return _empty_timeline_frame(), meta

    records = pd.DataFrame(event_records)
    records["count"] = (
        pd.to_numeric(records["count"], errors="coerce").fillna(0).astype(int)
    )

    if has_real_dates:
        records["event_date"] = pd.to_datetime(
            records["event_date"],
            utc=True,
            errors="coerce",
        )
        records = records.dropna(subset=["event_date"])
        records["event_date"] = records["event_date"].dt.date
        has_real_dates = not records.empty

    if not has_real_dates:
        return _empty_timeline_frame(), meta

    timeline = records.pivot_table(
        index="event_date",
        columns="event_type",
        values="count",
        aggfunc="sum",
        fill_value=0,
    )

    for key in BASE_METRIC_KEYS:
        if key not in timeline.columns:
            timeline[key] = 0

    timeline = timeline[list(BASE_METRIC_KEYS)].reset_index().sort_values("event_date")
    timeline["code_contributions"] = (
        timeline["commits"] + timeline["branch_created"] + timeline["branch_deleted"]
    )
    timeline["collab_contributions"] = (
        timeline["mr_opened"]
        + timeline["mr_merged"]
        + timeline["mr_approved"]
        + timeline["mr_commented"]
        + timeline["issue_opened"]
    )
    timeline["total_contributions"] = (
        timeline["code_contributions"] + timeline["collab_contributions"]
    )

    if (
        period_start is not None
        and period_end is not None
        and period_start <= period_end
    ):
        full_dates = pd.date_range(start=period_start, end=period_end, freq="D")
        timeline = (
            timeline.set_index("event_date")
            .reindex([ts.date() for ts in full_dates], fill_value=0)
            .rename_axis("event_date")
            .reset_index()
        )

    meta["has_real_dates"] = True
    meta["timeline_days"] = len(timeline)
    meta["active_days"] = int((timeline["total_contributions"] > 0).sum())

    return timeline, meta
