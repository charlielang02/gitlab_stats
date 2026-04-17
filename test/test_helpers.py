"""Unit tests for dashboard helper utilities."""

from __future__ import annotations

import pandas as pd

from gitlab_stats.dashboard_utils import helpers


def test_resolve_selected_path_returns_selected_when_exists(tmp_path):
    """Return the selected file when it exists."""
    # Arrange
    selected = tmp_path / "selected.csv"
    selected.write_text("data", encoding="utf-8")
    placeholder = tmp_path / "placeholder.csv"

    # Act
    resolved_path, using_placeholder = helpers.resolve_selected_path(
        selected,
        placeholder,
    )

    # Assert
    assert resolved_path == selected
    assert using_placeholder is False


def test_resolve_selected_path_uses_placeholder_when_selected_missing(tmp_path):
    """Fallback to placeholder when the selected file is absent."""
    # Arrange
    selected = tmp_path / "missing.csv"
    placeholder = tmp_path / "placeholder.csv"
    placeholder.write_text("placeholder", encoding="utf-8")

    # Act
    resolved_path, using_placeholder = helpers.resolve_selected_path(
        selected,
        placeholder,
    )

    # Assert
    assert resolved_path == placeholder
    assert using_placeholder is True


def test_resolve_selected_path_returns_none_when_both_paths_missing(tmp_path):
    """Return no path when neither selected nor placeholder exists."""
    # Arrange
    selected = tmp_path / "missing.csv"
    placeholder = tmp_path / "also-missing.csv"

    # Act
    resolved_path, using_placeholder = helpers.resolve_selected_path(
        selected,
        placeholder,
    )

    # Assert
    assert resolved_path is None
    assert using_placeholder is False


def test_prepare_metric_df_orders_columns_and_sorts_by_total_contributions():
    """Build a normalized metric frame with preferred column ordering."""
    # Arrange
    metrics = {
        "project-b": {
            "commits": 1,
            "mr_opened": 3,
            "total_contributions": 4,
            "custom_metric": 99,
        },
        "project-a": {
            "commits": 5,
            "mr_opened": 1,
            "total_contributions": 6,
            "collab_pct": 40,
        },
    }

    # Act
    metric_df, ordered_columns = helpers.prepare_metric_df(metrics)

    # Assert
    assert list(metric_df.index) == ["project-a", "project-b"]
    assert ordered_columns[:3] == ["commits", "mr_opened", "total_contributions"]
    assert metric_df.loc["project-a", "collab_pct"] == 40
    assert metric_df.loc["project-b", "custom_metric"] == 99
    assert list(metric_df.columns[: len(ordered_columns)]) == ordered_columns


def test_prepare_jira_metric_df_orders_columns_and_sorts_by_closed_issues():
    """Jira metric frame should follow Jira key order and sort by closed issues."""
    # Arrange
    metrics = {
        "project-b": {
            "jira_issues_assigned": 5,
            "jira_issues_closed": 2,
            "jira_comments": 4,
            "jira_story_points_closed": 7,
            "total_jira_activity": 18,
            "custom_metric": 1,
        },
        "project-a": {
            "jira_issues_assigned": 8,
            "jira_issues_closed": 6,
            "jira_comments": 3,
            "jira_story_points_closed": 9,
            "total_jira_activity": 26,
        },
    }

    # Act
    metric_df, ordered_columns = helpers.prepare_jira_metric_df(metrics)

    # Assert
    assert list(metric_df.index) == ["project-a", "project-b"]
    assert ordered_columns == [
        "jira_issues_assigned",
        "jira_issues_closed",
        "jira_comments",
        "jira_story_points_closed",
    ]
    assert metric_df.loc["project-a", "jira_issues_closed"] == 6
    assert metric_df.loc["project-b", "custom_metric"] == 1


def test_prepare_jira_metric_df_handles_missing_closed_column_without_sort_error():
    """Jira metric prep should still return a frame if closed-issues column is absent."""
    # Arrange
    metrics = {
        "project-a": {
            "jira_issues_assigned": 3,
            "jira_comments": 1,
        },
        "project-b": {
            "jira_issues_assigned": 5,
            "jira_comments": 2,
        },
    }

    # Act
    metric_df, ordered_columns = helpers.prepare_jira_metric_df(metrics)

    # Assert
    assert list(metric_df.index) == ["project-a", "project-b"]
    assert ordered_columns == ["jira_issues_assigned", "jira_comments"]


def test_compute_profile_summary_handles_empty_metric_df():
    """Empty inputs should produce the no-activity summary."""
    # Arrange
    metric_df = pd.DataFrame()

    # Act
    dominant_style, top_project, signal = helpers.compute_profile_summary(
        metric_df,
        {},
    )

    # Assert
    assert dominant_style == "No Activity"
    assert top_project == "N/A"
    assert signal == "No Activity Detected"


def test_compute_profile_summary_handles_zero_total_activity():
    """Zero totals should produce the no-activity summary."""
    # Arrange
    metric_df = pd.DataFrame(
        {"total_contributions": [0]},
        index=["project-a"],
    )
    total_metrics = {"code_contributions": 0, "collab_contributions": 0}

    # Act
    dominant_style, top_project, signal = helpers.compute_profile_summary(
        metric_df,
        total_metrics,
    )

    # Assert
    assert dominant_style == "No Activity"
    assert top_project == "project-a"
    assert signal == "No Activity Detected"


def test_compute_profile_summary_identifies_balanced_mix():
    """Similar code and collaboration totals should be labeled balanced."""
    # Arrange
    metric_df = pd.DataFrame(
        {"total_contributions": [10]},
        index=["project-a"],
    )
    total_metrics = {"code_contributions": 55, "collab_contributions": 50}

    # Act
    dominant_style, top_project, signal = helpers.compute_profile_summary(
        metric_df,
        total_metrics,
    )

    # Assert
    assert dominant_style == "Balanced"
    assert top_project == "project-a"
    assert signal == "Balanced Activity Mix"


def test_compute_profile_summary_identifies_code_heavy_activity():
    """Code-heavy mixes should be labeled accordingly."""
    # Arrange
    metric_df = pd.DataFrame(
        {"total_contributions": [10]},
        index=["project-a"],
    )
    total_metrics = {"code_contributions": 80, "collab_contributions": 10}

    # Act
    dominant_style, top_project, signal = helpers.compute_profile_summary(
        metric_df,
        total_metrics,
    )

    # Assert
    assert dominant_style == "Code-Heavy"
    assert top_project == "project-a"
    assert signal == "High Commit Velocity"


def test_compute_profile_summary_identifies_collaboration_heavy_activity():
    """Collaboration-heavy mixes should be labeled accordingly."""
    # Arrange
    metric_df = pd.DataFrame(
        {"total_contributions": [10]},
        index=["project-a"],
    )
    total_metrics = {"code_contributions": 10, "collab_contributions": 80}

    # Act
    dominant_style, top_project, signal = helpers.compute_profile_summary(
        metric_df,
        total_metrics,
    )

    # Assert
    assert dominant_style == "Collaboration-Heavy"
    assert top_project == "project-a"
    assert signal == "High Collaboration Activity"


def test_format_project_metrics_table_formats_counts_and_percentages():
    """Render numeric values with the expected formatting for the HTML table."""
    # Arrange
    project_data = pd.Series(
        {
            "commits": 7,
            "collab_pct": 32.125,
            "total_contributions": 10,
        },
    )
    ordered_columns = ["commits", "collab_pct", "total_contributions"]

    # Act
    html = helpers.format_project_metrics_table(project_data, ordered_columns)

    # Assert
    assert "project-metrics-table" in html
    assert "commits" in html
    assert "7" in html
    assert "32.1" in html
    assert "10" in html


def test_inject_dashboard_styles_calls_markdown_with_html(monkeypatch):
    """Injecting styles should write one HTML block to Streamlit."""
    # Arrange
    calls: list[tuple[str, bool]] = []

    def fake_markdown(body: str, unsafe_allow_html: bool):
        calls.append((body, unsafe_allow_html))

    monkeypatch.setattr(helpers.st, "markdown", fake_markdown)

    # Act
    helpers.inject_dashboard_styles()

    # Assert
    assert len(calls) == 1
    assert "<style>" in calls[0][0]
    assert calls[0][1] is True


def test_render_main_header_calls_markdown_with_branded_header(monkeypatch):
    """Rendering the main header should emit the branded title HTML."""
    # Arrange
    calls: list[tuple[str, bool]] = []

    def fake_markdown(body: str, unsafe_allow_html: bool):
        calls.append((body, unsafe_allow_html))

    monkeypatch.setattr(helpers.st, "markdown", fake_markdown)

    # Act
    helpers.render_main_header()

    # Assert
    assert len(calls) == 1
    assert "GitLab Contributions Dashboard" in calls[0][0]
    assert calls[0][1] is True
