"""Unit tests for dashboard chart builders."""

from __future__ import annotations

from datetime import date
from typing import Any
from typing import cast

import numpy as np
import pandas as pd

from gitlab_stats.dashboard_utils import charts


def _metric_df() -> pd.DataFrame:
    """Create a representative metric dataframe for chart tests."""
    return pd.DataFrame(
        {
            "commits": [10, 5, 0],
            "mr_opened": [3, 1, 0],
            "mr_merged": [2, 0, 0],
            "mr_approved": [1, 0, 0],
            "mr_commented": [4, 2, 0],
            "issue_opened": [1, 0, 0],
            "branch_created": [2, 1, 0],
            "branch_deleted": [1, 0, 0],
            "code_contributions": [12, 6, 0],
            "collab_contributions": [4, 2, 0],
            "total_contributions": [16, 8, 0],
            "code_pct": [75.0, 60.0, 0.0],
        },
        index=["project-a", "project-b", "project-c"],
    )


def _timeline_df() -> pd.DataFrame:
    """Create a representative timeline dataframe for chart tests."""
    return pd.DataFrame(
        {
            "event_date": ["2026-03-03", "2026-03-01", "2026-03-02"],
            "total_contributions": [3, 1, 2],
            "code_contributions": [2, 1, 1],
            "collab_contributions": [1, 0, 1],
        },
    )


def _figure(fig: Any) -> Any:
    """Return a loosely typed Plotly figure for assertions."""
    return cast("Any", fig)


def _trace(fig: Any, index: int) -> Any:
    """Return a trace from a loosely typed Plotly figure."""
    return _figure(fig).data[index]


def test_build_pareto_chart_returns_baseline_for_zero_total():
    """Zero totals should return a zeroed Pareto line chart."""
    # Arrange
    metric_df = pd.DataFrame({"total_contributions": [0, 0]}, index=["a", "b"])

    # Act
    fig = charts.build_pareto_chart(metric_df)

    # Assert
    trace = _trace(fig, 0)
    assert list(trace.x) == [0]
    assert list(trace.y) == [0]
    assert _figure(fig).layout.title.text == "Contribution Concentration (Pareto)"


def test_build_pareto_chart_includes_cumulative_baseline():
    """Positive totals should include an origin point and cumulative percentages."""
    # Arrange
    metric_df = pd.DataFrame(
        {"total_contributions": [4, 6]},
        index=["project-a", "project-b"],
    )

    # Act
    fig = charts.build_pareto_chart(metric_df)

    # Assert
    trace = _trace(fig, 0)
    assert list(trace.x) == [0, 1, 2]
    assert list(trace.y) == [0.0, 40.0, 100.0]


def test_build_code_collab_pie_uses_expected_labels_and_values():
    """Code-vs-collaboration pie chart should reflect the totals."""
    # Arrange
    total_metrics = {"code_contributions": 12, "collab_contributions": 8}

    # Act
    fig = charts.build_code_collab_pie(total_metrics)

    # Assert
    trace = _trace(fig, 0)
    assert list(trace.labels) == ["Code Contributions", "Collaboration"]
    assert list(trace.values) == [12, 8]
    assert _figure(fig).layout.height == 400


def test_build_type_distribution_pie_omits_zero_value_buckets():
    """Zero-count type buckets should be filtered out before plotting."""
    # Arrange
    total_metrics = {
        "commits": 7,
        "mr_opened": 0,
        "mr_merged": 2,
        "mr_approved": 0,
        "mr_commented": 3,
        "issue_opened": 0,
        "branch_created": 1,
        "branch_deleted": 2,
    }

    # Act

    fig = charts.build_type_distribution_pie(total_metrics)

    # Assert
    trace = _trace(fig, 0)
    assert set(trace.labels) == {
        "Commits",
        "MRs Merged",
        "MR Comments",
        "Branches",
    }
    assert sorted(trace.values) == [2, 3, 3, 7]
    assert _figure(fig).layout.height == 400


def test_build_distribution_box_uses_expected_traces():
    """Box plot should compare commits, total MRs, and issues."""
    # Arrange
    metric_df = _metric_df()

    # Act
    fig = charts.build_distribution_box(metric_df)

    # Assert
    traces = [_trace(fig, index) for index in range(3)]
    assert [trace.name for trace in traces] == ["Commits", "Total MRs", "Issues"]
    assert list(traces[0].y) == [10, 5, 0]
    assert list(traces[1].y) == [5, 1, 0]
    assert list(traces[2].y) == [1, 0, 0]


def test_build_commits_vs_mrs_scatter_uses_expected_axes():
    """Scatter chart should map commits to x and MRs opened to y."""
    # Arrange
    metric_df = _metric_df()

    # Act
    fig = charts.build_commits_vs_mrs_scatter(metric_df)

    # Assert
    trace = _trace(fig, 0)
    assert _figure(fig).layout.title.text == "Commits vs MRs by Project"
    assert list(trace.x) == [10, 5, 0]
    assert list(trace.y) == [3, 1, 0]


def test_build_commit_velocity_chart_orders_projects_by_commit_count():
    """Velocity chart should show the top projects ordered by commit count."""
    # Arrange
    metric_df = _metric_df()

    # Act
    fig = charts.build_commit_velocity_chart(metric_df)

    # Assert
    trace = _trace(fig, 0)
    assert list(trace.y) == ["project-c", "project-b", "project-a"]
    assert list(trace.x) == [0, 5, 10]


def test_build_mr_activity_chart_splits_mr_traces():
    """MR activity chart should stack the four MR-related metrics."""
    # Arrange
    metric_df = _metric_df()

    # Act
    fig = charts.build_mr_activity_chart(metric_df)

    # Assert
    traces = [_trace(fig, index) for index in range(4)]
    assert [trace.name for trace in traces] == [
        "mr_opened",
        "mr_merged",
        "mr_approved",
        "mr_commented",
    ]
    assert len(traces) == 4


def test_build_comparison_chart_splits_code_and_collaboration_traces():
    """Comparison chart should stack code and collaboration traces."""
    # Arrange
    metric_df = _metric_df()

    # Act
    fig = charts.build_comparison_chart(metric_df)

    # Assert
    traces = [_trace(fig, index) for index in range(2)]
    assert [trace.name for trace in traces] == [
        "code_contributions",
        "collab_contributions",
    ]
    assert len(traces) == 2


def test_build_activity_heatmap_applies_log_scale_when_requested():
    """Log-scaled heatmap should transform values with log1p and update label."""
    # Arrange
    metric_df = _metric_df()

    # Act
    fig = charts.build_activity_heatmap(metric_df, use_log_scale=True)

    # Assert
    trace = _trace(fig, 0)
    expected_first_cell = float(np.log1p(10))
    assert trace.z.shape == (6, 3)
    assert round(float(trace.z[0][0]), 6) == round(expected_first_cell, 6)
    assert _figure(fig).layout.height == 500
    assert _figure(fig).layout.coloraxis.colorbar.title.text == "log(1 + count)"


def test_build_activity_heatmap_keeps_raw_values_without_log_scale():
    """Linear heatmap should preserve the original numeric values."""
    # Arrange
    metric_df = _metric_df()

    # Act
    fig = charts.build_activity_heatmap(metric_df, use_log_scale=False)

    # Assert
    trace = _trace(fig, 0)
    assert trace.z.shape == (6, 3)
    assert _figure(fig).layout.height == 500


def test_build_top_projects_chart_shows_top_n_projects():
    """Top projects chart should keep the largest projects only."""
    # Arrange
    metric_df = _metric_df()

    # Act
    fig = charts.build_top_projects_chart(metric_df, top_n=2)

    # Assert
    trace = _trace(fig, 0)
    assert list(trace.y) == ["project-b", "project-a"]
    assert list(trace.x) == [8, 16]
    assert list(trace.text) == [8, 16]
    assert _figure(fig).layout.height == 400


def test_build_contribution_style_chart_shows_top_projects_by_code_pct():
    """Contribution style chart should rank projects by code percentage."""
    # Arrange
    metric_df = _metric_df()

    # Act
    fig = charts.build_contribution_style_chart(metric_df, top_n=2)

    # Assert
    trace = _trace(fig, 0)
    assert list(trace.y) == ["project-a", "project-b"]
    assert list(trace.x) == [75.0, 60.0]
    assert list(trace.text) == [75.0, 60.0]
    assert _figure(fig).layout.height == 400


def test_build_project_pie_uses_selected_project_totals():
    """Selected project pie should reflect the project contribution split."""
    # Arrange
    project_data = {"code_contributions": 9, "collab_contributions": 3}

    # Act
    fig = charts.build_project_pie(project_data)

    # Assert
    trace = _trace(fig, 0)
    assert list(trace.labels) == ["Code Contributions", "Collaboration"]
    assert list(trace.values) == [9, 3]


def test_build_project_activity_bar_uses_project_breakdown():
    """Project activity bar should plot the expected activity categories."""
    # Arrange
    project_data = {
        "commits": 7,
        "mr_opened": 4,
        "mr_merged": 2,
        "mr_approved": 1,
        "mr_commented": 5,
        "branch_created": 3,
        "branch_deleted": 1,
        "issue_opened": 6,
    }

    # Act
    fig = charts.build_project_activity_bar(project_data)

    # Assert
    trace = _trace(fig, 0)
    assert list(trace.x) == [
        "Commits",
        "MR Opened",
        "MR Merged",
        "MR Approved",
        "MR Commented",
        "Branch Created",
        "Branch Deleted",
        "Issues",
    ]
    assert list(trace.y) == [7, 4, 2, 1, 5, 3, 1, 6]
    assert _figure(fig).layout.height == 400


def test_build_daily_activity_trend_sorts_dates_and_adds_rolling_average():
    """Daily trend chart should sort dates and compute the 7-day average."""
    # Arrange
    timeline_df = _timeline_df()

    # Act
    fig = charts.build_daily_activity_trend(timeline_df)

    # Assert
    traces = [_trace(fig, index) for index in range(2)]
    assert list(pd.to_datetime(traces[0].x).date) == [
        date(2026, 3, 1),
        date(2026, 3, 2),
        date(2026, 3, 3),
    ]
    assert list(traces[0].y) == [1, 2, 3]
    assert list(traces[1].y) == [1.0, 1.5, 2.0]


def test_build_weekly_mix_chart_groups_by_monday_week_start():
    """Weekly mix chart should resample timeline data into weekly buckets."""
    # Arrange
    timeline_df = _timeline_df()

    # Act
    fig = charts.build_weekly_mix_chart(timeline_df)

    # Assert
    trace = _trace(fig, 0)
    assert len([_trace(fig, index) for index in range(2)]) == 2
    assert list(pd.to_datetime(trace.x).date) == [date(2026, 3, 2), date(2026, 3, 9)]


def test_build_monthly_volume_chart_groups_by_month_start():
    """Monthly chart should aggregate into month-start buckets."""
    # Arrange
    timeline_df = _timeline_df()

    # Act
    fig = charts.build_monthly_volume_chart(timeline_df)

    # Assert
    trace = _trace(fig, 0)
    assert list(pd.to_datetime(trace.x).date) == [date(2026, 3, 1)]
    assert list(trace.y) == [6]


def test_build_monthly_volume_chart_formats_monthly_axis():
    """Monthly chart should always label the x-axis by whole months."""
    # Arrange
    timeline_df = pd.DataFrame(
        {
            "event_date": [
                "2026-01-15",
                "2026-02-10",
                "2026-03-20",
            ],
            "total_contributions": [5, 7, 9],
            "code_contributions": [3, 4, 5],
            "collab_contributions": [2, 3, 4],
        },
    )

    # Act
    fig = charts.build_monthly_volume_chart(timeline_df)

    # Assert
    xaxis = _figure(fig).layout.xaxis
    assert list(pd.to_datetime(xaxis.tickvals).date) == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]
    assert xaxis.tickformat == "%b %Y"
    assert xaxis.tickmode == "array"


def _jira_timeline_df() -> pd.DataFrame:
    """Create Jira timeline dataframe for chart tests."""
    return pd.DataFrame(
        {
            "event_date": ["2026-03-03", "2026-03-01", "2026-03-02"],
            "jira_issues_closed": [3, 1, 2],
            "jira_comments": [6, 2, 4],
            "jira_story_points_closed": [9, 3, 6],
        },
    )


def test_build_jira_daily_closed_chart_adds_rolling_average():
    """Closed-issues chart should sort dates and add a 7-day average trace."""
    # Arrange
    timeline_df = _jira_timeline_df()

    # Act
    fig = charts.build_jira_daily_closed_chart(timeline_df)

    # Assert
    traces = [_trace(fig, index) for index in range(2)]
    assert list(pd.to_datetime(traces[0].x).date) == [
        date(2026, 3, 1),
        date(2026, 3, 2),
        date(2026, 3, 3),
    ]
    assert list(traces[0].y) == [1, 2, 3]
    assert list(traces[1].y) == [1.0, 1.5, 2.0]
    assert traces[1].name == "7-Day Average"


def test_build_jira_daily_comments_chart_adds_rolling_average():
    """Comments chart should include daily values and a 7-day average trace."""
    # Arrange
    timeline_df = _jira_timeline_df()

    # Act
    fig = charts.build_jira_daily_comments_chart(timeline_df)

    # Assert
    traces = [_trace(fig, index) for index in range(2)]
    assert list(traces[0].y) == [2, 4, 6]
    assert list(traces[1].y) == [2.0, 3.0, 4.0]
    assert traces[1].name == "7-Day Average"


def test_build_jira_daily_story_points_chart_adds_rolling_average():
    """Story points chart should include daily values and a 7-day average trace."""
    # Arrange
    timeline_df = _jira_timeline_df()

    # Act
    fig = charts.build_jira_daily_story_points_chart(timeline_df)

    # Assert
    traces = [_trace(fig, index) for index in range(2)]
    assert list(traces[0].y) == [3, 6, 9]
    assert list(traces[1].y) == [3.0, 4.5, 6.0]
    assert traces[1].name == "7-Day Average"
