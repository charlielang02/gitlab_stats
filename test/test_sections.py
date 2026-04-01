"""Unit tests for dashboard section renderers."""

from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd

from gitlab_stats.dashboard_utils import sections


class _FakeColumn:
    """Minimal Streamlit column stand-in for tests."""

    def __init__(self, calls: dict[str, list[Any]], index: int):
        self._calls = calls
        self._index = index

    def __enter__(self):
        """Return the fake column when used as a context manager."""
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """Allow the context manager to exit without suppressing errors."""
        return False

    def metric(self, label: str, value: Any):
        """Record a metric call for later assertions."""
        self._calls["metrics"].append((self._index, label, value))


def _install_streamlit_spy(monkeypatch):
    """Record Streamlit calls made by the section renderer under test."""
    calls: dict[str, list[Any]] = {
        "captions": [],
        "download_button": [],
        "headers": [],
        "infos": [],
        "markdown": [],
        "metrics": [],
        "plotly_chart": [],
        "subheaders": [],
        "warnings": [],
        "columns": [],
    }

    def _record(name: str):
        """Build a recorder for a specific Streamlit function name."""

        def _inner(*args, **kwargs):
            """Store a Streamlit call with positional and keyword arguments."""
            calls[name].append((args, kwargs))

        return _inner

    def _columns(count: int):
        """Return fake columns that can collect metric calls."""
        calls["columns"].append(count)
        return tuple(_FakeColumn(calls, index) for index in range(count))

    monkeypatch.setattr(sections.st, "caption", _record("captions"))
    monkeypatch.setattr(sections.st, "download_button", _record("download_button"))
    monkeypatch.setattr(sections.st, "header", _record("headers"))
    monkeypatch.setattr(sections.st, "info", _record("infos"))
    monkeypatch.setattr(sections.st, "markdown", _record("markdown"))
    monkeypatch.setattr(sections.st, "plotly_chart", _record("plotly_chart"))
    monkeypatch.setattr(sections.st, "subheader", _record("subheaders"))
    monkeypatch.setattr(sections.st, "warning", _record("warnings"))
    monkeypatch.setattr(sections.st, "columns", _columns)

    return calls


def _install_behavior_chart_spies(monkeypatch):
    """Record chart builder inputs and return sentinel figures."""
    calls: dict[str, list[pd.DataFrame]] = {
        "daily": [],
        "weekly": [],
        "monthly": [],
    }

    def _builder(name: str, figure: str):
        """Return a fake chart builder that records the timeline input."""

        def _inner(timeline: pd.DataFrame):
            """Capture the timeline and return the sentinel figure name."""
            calls[name].append(timeline.copy())
            return figure

        return _inner

    monkeypatch.setattr(
        sections,
        "build_daily_activity_trend",
        _builder("daily", "daily-figure"),
    )
    monkeypatch.setattr(
        sections,
        "build_weekly_mix_chart",
        _builder("weekly", "weekly-figure"),
    )
    monkeypatch.setattr(
        sections,
        "build_monthly_volume_chart",
        _builder("monthly", "monthly-figure"),
    )

    return calls


def _timeline_df() -> pd.DataFrame:
    """Create a representative timeline dataframe for section tests."""
    return pd.DataFrame(
        {
            "event_date": [
                "2026-03-01",
                "2026-03-02",
                "2026-03-03",
                "2026-03-04",
                "2026-03-05",
            ],
            "total_contributions": [0, 0, 0, 2, 3],
            "code_contributions": [0, 0, 0, 1, 2],
            "collab_contributions": [0, 0, 0, 1, 1],
        },
    )


def _metric_df() -> pd.DataFrame:
    """Create a representative project dataframe for export tests."""
    return pd.DataFrame(
        {
            "commits": [10, 5],
            "total_contributions": [16, 8],
            "code_contributions": [12, 6],
            "collab_contributions": [4, 2],
        },
        index=["project-a", "project-b"],
    )


def test_render_behavior_analysis_hides_weekly_and_monthly_charts_for_short_windows(
    monkeypatch,
):
    """Short windows should keep the daily chart and hide slower charts."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)
    chart_calls = _install_behavior_chart_spies(monkeypatch)
    timeline_df = _timeline_df()
    timeline_meta = {
        "requested_days": 21,
        "window_label": "Last 3 weeks",
        "period_start": "2026-03-01",
        "period_end": "2026-03-21",
        "expected_days": 21,
        "has_real_dates": True,
    }

    # Act
    sections.render_behavior_analysis(timeline_df, timeline_meta)

    # Assert
    assert [call[0][0] for call in calls["headers"]] == ["🧭 Behavior Analysis"]
    assert any(
        "Selected timeframe: Last 3 weeks" in call[0][0] for call in calls["captions"]
    )
    assert any(
        "Data coverage: 2026-03-01 to 2026-03-21 (21 days)" in call[0][0]
        for call in calls["captions"]
    )
    assert any(
        "Hidden for windows shorter than 4 weeks." in call[0][0]
        for call in calls["captions"]
    )
    assert any(
        "Hidden for windows shorter than 2 months." in call[0][0]
        for call in calls["captions"]
    )
    assert len(chart_calls["daily"]) == 1
    assert len(chart_calls["weekly"]) == 0
    assert len(chart_calls["monthly"]) == 0
    assert len(calls["plotly_chart"]) == 1
    assert calls["plotly_chart"][0][0][0] == "daily-figure"
    assert chart_calls["daily"][0]["event_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-03-04",
        "2026-03-05",
    ]


def test_render_behavior_analysis_shows_weekly_and_monthly_charts_for_long_windows(
    monkeypatch,
):
    """Long windows should render every behavior chart."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)
    chart_calls = _install_behavior_chart_spies(monkeypatch)
    timeline_df = _timeline_df()
    timeline_meta = {
        "requested_days": 90,
        "window_label": "Last 3 months",
        "period_start": "2026-01-01",
        "period_end": "2026-03-31",
        "expected_days": 90,
        "has_real_dates": True,
    }

    # Act
    sections.render_behavior_analysis(timeline_df, timeline_meta)

    # Assert
    assert any(
        "Selected timeframe: Last 3 months" in call[0][0] for call in calls["captions"]
    )
    assert not any(
        "Hidden for windows shorter than 4 weeks." in call[0][0]
        for call in calls["captions"]
    )
    assert not any(
        "Hidden for windows shorter than 2 months." in call[0][0]
        for call in calls["captions"]
    )
    assert len(chart_calls["daily"]) == 1
    assert len(chart_calls["weekly"]) == 1
    assert len(chart_calls["monthly"]) == 1
    assert len(calls["plotly_chart"]) == 3
    assert [call[0][0] for call in calls["plotly_chart"]] == [
        "daily-figure",
        "weekly-figure",
        "monthly-figure",
    ]


def test_render_behavior_analysis_reports_parser_fallback_for_empty_timeline(
    monkeypatch,
):
    """Parser fallback should show the API-only message instead of charts."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)
    empty_timeline = pd.DataFrame(columns=["event_date", "total_contributions"])

    # Act
    sections.render_behavior_analysis(empty_timeline, {"source": "parser"})

    # Assert
    assert len(calls["infos"]) == 1
    assert (
        calls["infos"][0][0][0]
        == "Behavior analysis is API-only and is not computed from parser fallback."
    )
    assert len(calls["plotly_chart"]) == 0


def test_render_export_with_timeline_combines_metrics_and_timeline_rows(monkeypatch):
    """Timeline exports should append normalized timeline rows to the metrics CSV."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)
    metric_df = _metric_df()
    timeline_df = pd.DataFrame(
        {
            "event_date": ["2026-03-10", "2026-03-11"],
            "total_contributions": [1, 2],
            "code_contributions": [1, 1],
            "collab_contributions": [0, 1],
        },
    )

    # Act
    sections.render_export_with_timeline(metric_df, timeline_df)

    # Assert
    assert len(calls["download_button"]) == 1
    download_kwargs = calls["download_button"][0][1]
    exported = pd.read_csv(StringIO(download_kwargs["data"]))

    assert list(exported["row_type"]) == [
        "project_metric",
        "project_metric",
        "timeline_day",
        "timeline_day",
    ]
    assert list(exported["project"][:2]) == ["project-a", "project-b"]
    assert exported.loc[2:, "project"].isna().all()
    assert list(exported.loc[2:, "event_date"]) == ["2026-03-10", "2026-03-11"]
    assert download_kwargs["file_name"] == "gitlab_contributions_export.csv"
    assert download_kwargs["mime"] == "text/csv"
