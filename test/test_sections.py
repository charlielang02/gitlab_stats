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
        self._calls["column_metrics"].append((self._index, label, value))


class _FakeContext:
    """Generic context manager used for tabs and layout placeholders."""

    def __enter__(self):
        """Return the context object itself."""
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """Allow context manager exit without suppressing errors."""
        return False


def _install_streamlit_spy(monkeypatch):
    """Record Streamlit calls made by the section renderer under test."""
    calls: dict[str, list[Any]] = {
        "captions": [],
        "checkbox": [],
        "column_metrics": [],
        "dataframe": [],
        "download_button": [],
        "headers": [],
        "infos": [],
        "markdown": [],
        "metrics": [],
        "plotly_chart": [],
        "tabs": [],
        "subheaders": [],
        "writes": [],
        "warnings": [],
        "columns": [],
        "slider": [],
    }

    def _record(name: str):
        """Build a recorder for a specific Streamlit function name."""

        def _inner(*args, **kwargs):
            """Store a Streamlit call with positional and keyword arguments."""
            calls[name].append((args, kwargs))

        return _inner

    def _columns(count: int | list[int]):
        """Return fake columns that can collect metric calls."""
        resolved_count = count if isinstance(count, int) else len(count)
        calls["columns"].append(count)
        return tuple(_FakeColumn(calls, index) for index in range(resolved_count))

    def _tabs(names: list[str]):
        """Return fake tab contexts for tabbed section rendering."""
        calls["tabs"].append(names)
        return tuple(_FakeContext() for _ in names)

    def _checkbox(label: str, value: bool = False, **kwargs):
        """Record checkbox calls and return the provided default value."""
        calls["checkbox"].append((label, value, kwargs.get("help")))
        return value

    def _metric(label: str, value: Any):
        """Record global Streamlit metric calls."""
        calls["metrics"].append((label, value))

    def _slider(label: str, min_value: int, max_value: int, value: int, **kwargs):
        """Record slider calls and return the provided default value."""
        calls["slider"].append((label, min_value, max_value, value, kwargs))
        return value

    monkeypatch.setattr(sections.st, "caption", _record("captions"))
    monkeypatch.setattr(sections.st, "checkbox", _checkbox)
    monkeypatch.setattr(sections.st, "dataframe", _record("dataframe"))
    monkeypatch.setattr(sections.st, "download_button", _record("download_button"))
    monkeypatch.setattr(sections.st, "header", _record("headers"))
    monkeypatch.setattr(sections.st, "info", _record("infos"))
    monkeypatch.setattr(sections.st, "markdown", _record("markdown"))
    monkeypatch.setattr(sections.st, "metric", _metric)
    monkeypatch.setattr(sections.st, "plotly_chart", _record("plotly_chart"))
    monkeypatch.setattr(sections.st, "slider", _slider)
    monkeypatch.setattr(sections.st, "subheader", _record("subheaders"))
    monkeypatch.setattr(sections.st, "tabs", _tabs)
    monkeypatch.setattr(sections.st, "write", _record("writes"))
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


def test_render_behavior_analysis_warns_when_dates_are_unavailable(monkeypatch):
    """Empty timelines without real dates should produce a warning branch."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)

    # Act
    sections.render_behavior_analysis(
        pd.DataFrame(columns=["event_date", "total_contributions"]),
        {"has_real_dates": False},
    )

    # Assert
    assert len(calls["warnings"]) == 1
    assert "does not include usable event timestamps" in calls["warnings"][0][0][0]
    assert len(calls["infos"]) == 0


def test_render_behavior_analysis_reports_no_activity_when_all_totals_are_zero(
    monkeypatch,
):
    """Non-empty timelines with all-zero totals should show the no-activity info."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)
    timeline_df = pd.DataFrame(
        {
            "event_date": ["2026-03-01", "2026-03-02"],
            "total_contributions": [0, 0],
        },
    )

    # Act
    sections.render_behavior_analysis(timeline_df, {"has_real_dates": True})

    # Assert
    assert len(calls["infos"]) == 1
    assert (
        calls["infos"][0][0][0]
        == "No activity was found in the selected lookback period."
    )
    assert len(calls["plotly_chart"]) == 0


def test_render_executive_summary_renders_expected_metrics(monkeypatch):
    """Executive summary should emit top-level and average metrics."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)
    metric_df = pd.DataFrame(
        {
            "commits": [10, 5],
            "mr_opened": [2, 1],
            "mr_merged": [1, 1],
        },
        index=["project-a", "project-b"],
    )
    total_metrics = {
        "total_contributions": 18,
        "code_contributions": 12,
        "collab_contributions": 6,
        "code_pct": 66.7,
    }

    # Act
    sections.render_executive_summary(metric_df, total_metrics)

    # Assert
    assert [call[0][0] for call in calls["headers"]] == ["📈 Executive Summary"]
    recorded = {(label, value) for _, label, value in calls["column_metrics"]}
    recorded |= set(calls["metrics"])
    assert ("Total Contributions", 18) in recorded
    assert ("Code Contributions", 12) in recorded
    assert ("Collaboration Contributions", 6) in recorded
    assert ("Projects Contributed", 2) in recorded
    assert ("Avg Commits/Project", "7.5") in recorded
    assert ("Avg MRs/Project", "2.5") in recorded
    assert ("Code vs Collab", "66.7% Code") in recorded


def test_render_profile_uses_profile_summary_outputs(monkeypatch):
    """Profile renderer should interpolate summary fields in the info callout."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)
    monkeypatch.setattr(
        sections,
        "compute_profile_summary",
        lambda *_: ("Balanced", "project-a", "Balanced Activity Mix"),
    )

    # Act
    sections.render_profile(pd.DataFrame(index=["project-a"]), {})

    # Assert
    assert any("### 🧠 Developer Profile" in call[0][0] for call in calls["markdown"])
    assert len(calls["infos"]) == 1
    assert "Balanced Contributor" in calls["infos"][0][0][0]
    assert "project-a" in calls["infos"][0][0][0]


def test_render_key_insights_handles_zero_total_contributions(monkeypatch):
    """Insights should render zero collaboration ratio when total is zero."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)
    metric_df = pd.DataFrame(
        {
            "total_contributions": [5, 3],
            "commits": [3, 1],
        },
        index=["project-a", "project-b"],
    )
    total_metrics = {"collab_contributions": 2, "total_contributions": 0}

    # Act
    sections.render_key_insights(metric_df, total_metrics)

    # Assert
    assert [call[0][0] for call in calls["headers"]][-1] == "🎯 Key Insights"
    insight_blocks = [
        call[0][0] for call in calls["markdown"] if "insight-box" in call[0][0]
    ]
    assert len(insight_blocks) == 3
    assert any("0.0% collaborative" in block for block in insight_blocks)


def test_render_contribution_distribution_writes_top_three_and_pareto_chart(
    monkeypatch,
):
    """Distribution renderer should list top projects and draw Pareto chart."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)
    metric_df = pd.DataFrame(
        {"total_contributions": [10, 7, 4, 2]},
        index=["project-a", "project-b", "project-c", "project-d"],
    )
    monkeypatch.setattr(sections, "build_pareto_chart", lambda *_: "pareto-figure")

    # Act
    sections.render_contribution_distribution(metric_df)

    # Assert
    assert len(calls["writes"]) == 3
    assert "1. **project-a**" in calls["writes"][0][0][0]
    assert calls["plotly_chart"][0][0][0] == "pareto-figure"


def test_render_breakdown_tabs_renders_all_three_tab_views(monkeypatch):
    """Breakdown tabs should render overview, table, and distribution charts."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)
    metric_df = pd.DataFrame(
        {
            "commits": [10, 5],
            "mr_opened": [2, 1],
            "mr_merged": [1, 1],
            "issue_opened": [0, 1],
            "total_contributions": [16, 8],
        },
        index=["project-a", "project-b"],
    )
    total_metrics = {"code_contributions": 12, "collab_contributions": 6}
    monkeypatch.setattr(
        sections,
        "build_code_collab_pie",
        lambda *_: "code-collab-figure",
    )
    monkeypatch.setattr(
        sections,
        "build_type_distribution_pie",
        lambda *_: "type-figure",
    )
    monkeypatch.setattr(sections, "build_distribution_box", lambda *_: "box-figure")
    monkeypatch.setattr(
        sections,
        "build_commits_vs_mrs_scatter",
        lambda *_: "scatter-figure",
    )

    # Act
    sections.render_breakdown_tabs(metric_df, total_metrics)

    # Assert
    assert calls["tabs"][0] == ["Overview", "Detailed Table", "All Charts"]
    assert len(calls["dataframe"]) == 1
    assert [call[0][0] for call in calls["plotly_chart"]] == [
        "code-collab-figure",
        "type-figure",
        "box-figure",
        "scatter-figure",
    ]


def test_render_top_projects_shows_all_projects_without_slider_for_small_sets(
    monkeypatch,
):
    """Top projects should avoid the slider when there are three or fewer projects."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)
    metric_df = pd.DataFrame(
        {
            "total_contributions": [16, 8, 4],
            "code_contributions": [12, 6, 2],
            "collab_contributions": [4, 2, 2],
        },
        index=["project-a", "project-b", "project-c"],
    )
    top_calls: list[int] = []

    def _top_chart(df: pd.DataFrame, top_n: int):  # pylint: disable=unused-argument
        top_calls.append(top_n)
        return "top-figure"

    def _style_chart(df: pd.DataFrame, top_n: int):  # pylint: disable=unused-argument
        top_calls.append(top_n)
        return "style-figure"

    monkeypatch.setattr(sections, "build_top_projects_chart", _top_chart)
    monkeypatch.setattr(sections, "build_contribution_style_chart", _style_chart)

    # Act
    sections.render_top_projects(metric_df)

    # Assert
    assert len(calls["slider"]) == 0
    assert any("Showing all 3 projects." in call[0][0] for call in calls["captions"])
    assert top_calls == [3, 3]
    assert [call[0][0] for call in calls["plotly_chart"]] == [
        "top-figure",
        "style-figure",
    ]


def test_render_top_projects_shows_info_and_returns_for_empty_dataset(monkeypatch):
    """Top projects should render an info message and return when no projects exist."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)
    metric_df = pd.DataFrame(
        {
            "total_contributions": [],
            "code_contributions": [],
            "collab_contributions": [],
        },
    )

    # Act
    sections.render_top_projects(metric_df)

    # Assert
    assert len(calls["infos"]) == 1
    assert (
        "No projects are available for top project analysis." in calls["infos"][0][0][0]
    )
    assert len(calls["slider"]) == 0
    assert len(calls["plotly_chart"]) == 0


def test_render_top_projects_uses_slider_for_more_than_three_projects(monkeypatch):
    """Top projects should use the slider when project count exceeds the threshold."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)
    metric_df = pd.DataFrame(
        {
            "total_contributions": [16, 12, 8, 4],
            "code_contributions": [12, 8, 6, 2],
            "collab_contributions": [4, 4, 2, 2],
        },
        index=["project-a", "project-b", "project-c", "project-d"],
    )
    top_calls: list[int] = []

    def _top_chart(df: pd.DataFrame, top_n: int):  # pylint: disable=unused-argument
        top_calls.append(top_n)
        return "top-figure"

    def _style_chart(df: pd.DataFrame, top_n: int):  # pylint: disable=unused-argument
        top_calls.append(top_n)
        return "style-figure"

    monkeypatch.setattr(sections, "build_top_projects_chart", _top_chart)
    monkeypatch.setattr(sections, "build_contribution_style_chart", _style_chart)

    # Act
    sections.render_top_projects(metric_df)

    # Assert
    assert len(calls["slider"]) == 1
    label, min_value, max_value, value, _ = calls["slider"][0]
    assert label == "Number of projects to display"
    assert min_value == 3
    assert max_value == 4
    assert value == 4
    assert not any("Showing all" in call[0][0] for call in calls["captions"])
    assert top_calls == [4, 4]
    assert [call[0][0] for call in calls["plotly_chart"]] == [
        "top-figure",
        "style-figure",
    ]


def test_render_performance_tabs_renders_all_tab_charts(monkeypatch):
    """Performance tabs should emit four charts and read the heatmap checkbox."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)
    metric_df = pd.DataFrame(
        {
            "commits": [10, 5],
            "mr_opened": [2, 1],
            "mr_merged": [1, 1],
            "mr_approved": [0, 0],
            "mr_commented": [1, 0],
            "code_contributions": [12, 6],
            "collab_contributions": [4, 2],
        },
        index=["project-a", "project-b"],
    )
    monkeypatch.setattr(
        sections,
        "build_commit_velocity_chart",
        lambda *_: "velocity-figure",
    )
    monkeypatch.setattr(sections, "build_mr_activity_chart", lambda *_: "mr-figure")
    monkeypatch.setattr(
        sections,
        "build_comparison_chart",
        lambda *_: "comparison-figure",
    )
    monkeypatch.setattr(sections, "build_activity_heatmap", lambda *_: "heatmap-figure")

    # Act
    sections.render_performance_tabs(metric_df)

    # Assert
    assert calls["tabs"][0] == [
        "Commit Velocity",
        "Collaboration Activity",
        "Project Comparison",
        "Activity Heatmap",
    ]
    assert len(calls["checkbox"]) == 1
    assert calls["checkbox"][0][0] == "Use logarithmic color scale"
    assert [call[0][0] for call in calls["plotly_chart"]] == [
        "velocity-figure",
        "mr-figure",
        "comparison-figure",
        "heatmap-figure",
    ]


def test_render_export_without_timeline_exports_metric_rows_only(monkeypatch):
    """Export renderer without timeline should emit metric rows only."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)

    # Act
    sections.render_export(_metric_df())

    # Assert
    assert len(calls["download_button"]) == 1
    exported = pd.read_csv(StringIO(calls["download_button"][0][1]["data"]))
    assert list(exported["row_type"]) == ["project_metric", "project_metric"]
    assert list(exported["project"]) == ["project-a", "project-b"]


def test_render_export_with_timeline_uses_metrics_only_when_timeline_empty(monkeypatch):
    """Timeline export should fall back to metric rows when timeline is empty."""
    # Arrange
    calls = _install_streamlit_spy(monkeypatch)

    # Act
    sections.render_export_with_timeline(_metric_df(), pd.DataFrame())

    # Assert
    exported = pd.read_csv(StringIO(calls["download_button"][0][1]["data"]))
    assert list(exported["row_type"]) == ["project_metric", "project_metric"]
