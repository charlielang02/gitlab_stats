"""Chart builder functions for dashboard visualizations."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from gitlab_stats.dashboard_utils.helpers import ACCENT
from gitlab_stats.dashboard_utils.helpers import CONTINUOUS_SCALE
from gitlab_stats.dashboard_utils.helpers import HEATMAP_SCALE
from gitlab_stats.dashboard_utils.helpers import HIGHLIGHT
from gitlab_stats.dashboard_utils.helpers import PALETTE
from gitlab_stats.dashboard_utils.helpers import PRIMARY
from gitlab_stats.dashboard_utils.helpers import SECONDARY


def build_pareto_chart(metric_df):
    """Build cumulative contribution Pareto line chart."""
    total = metric_df["total_contributions"].sum()
    if total <= 0:
        return px.line(
            x=[0],
            y=[0],
            labels={"x": "Projects", "y": "Cumulative Contribution %"},
            title="Contribution Concentration (Pareto)",
        )

    cumulative = metric_df["total_contributions"].cumsum() / total
    x_values = np.arange(1, len(cumulative) + 1)
    y_values = (100 * cumulative).to_numpy()

    x_with_baseline = np.insert(x_values, 0, 0)
    y_with_baseline = np.insert(y_values, 0, 0.0)
    return px.line(
        x=x_with_baseline,
        y=y_with_baseline,
        labels={"x": "Projects", "y": "Cumulative Contribution %"},
        title="Contribution Concentration (Pareto)",
    )


def build_code_collab_pie(total_metrics):
    """Build overall code-vs-collaboration donut chart."""
    code_collab_data = {
        "Code Contributions": int(total_metrics["code_contributions"]),
        "Collaboration": int(total_metrics["collab_contributions"]),
    }
    fig = px.pie(
        names=list(code_collab_data.keys()),
        values=list(code_collab_data.values()),
        color_discrete_sequence=[PRIMARY, SECONDARY],
        hole=0.35,
    )
    fig.update_layout(height=400)
    return fig


def build_type_distribution_pie(total_metrics):
    """Build contribution type distribution pie chart."""
    type_dist = {
        "Commits": int(total_metrics.get("commits", 0)),
        "MRs Opened": int(total_metrics.get("mr_opened", 0)),
        "MRs Merged": int(total_metrics.get("mr_merged", 0)),
        "MRs Approved": int(total_metrics.get("mr_approved", 0)),
        "MR Comments": int(total_metrics.get("mr_commented", 0)),
        "Issues": int(total_metrics.get("issue_opened", 0)),
        "Branches": int(
            total_metrics.get("branch_created", 0)
            + total_metrics.get("branch_deleted", 0),
        ),
    }
    type_dist = {label: value for label, value in type_dist.items() if value > 0}
    fig = px.pie(
        names=list(type_dist.keys()),
        values=list(type_dist.values()),
        color_discrete_sequence=PALETTE,
    )
    fig.update_layout(height=400)
    return fig


def build_distribution_box(metric_df):
    """Build boxplot distribution for key activity families."""
    fig = go.Figure()
    fig.add_trace(
        go.Box(y=metric_df["commits"], name="Commits", marker_color=PRIMARY),
    )
    fig.add_trace(
        go.Box(
            y=metric_df["mr_opened"] + metric_df["mr_merged"],
            name="Total MRs",
            marker_color=SECONDARY,
        ),
    )
    fig.add_trace(
        go.Box(
            y=metric_df["issue_opened"],
            name="Issues",
            marker_color=ACCENT,
        ),
    )
    fig.update_layout(
        height=400,
        title="Distribution of Metrics Across Projects",
    )
    return fig


def build_commits_vs_mrs_scatter(metric_df):
    """Build commits-vs-MR scatter chart."""
    fig = px.scatter(
        metric_df,
        x="commits",
        y="mr_opened",
        size="total_contributions",
        hover_name=metric_df.index,
        color="code_pct",
        color_continuous_scale=CONTINUOUS_SCALE,
        labels={
            "commits": "Commits",
            "mr_opened": "MRs Opened",
            "code_pct": "Code %",
        },
    )
    fig.update_layout(height=400, title="Commits vs MRs by Project")
    return fig


def build_commit_velocity_chart(metric_df):
    """Build horizontal commit velocity bar chart."""
    commit_df = metric_df[["commits"]].sort_values("commits", ascending=True).tail(20)
    commit_plot_df = commit_df.reset_index().rename(columns={"index": "project"})
    fig = px.bar(
        commit_plot_df,
        x="commits",
        y="project",
        color="commits",
        orientation="h",
        color_continuous_scale=CONTINUOUS_SCALE,
        labels={"commits": "Commit Count", "project": "Project"},
    )
    fig.update_layout(showlegend=False, height=500)
    return fig


def build_mr_activity_chart(metric_df):
    """Build stacked MR activity chart."""
    mr_activity = (
        metric_df[["mr_opened", "mr_merged", "mr_approved", "mr_commented"]]
        .sort_values("mr_opened", ascending=False)
        .head(20)
    )
    fig = px.bar(
        mr_activity,
        x=mr_activity.index,
        y=["mr_opened", "mr_merged", "mr_approved", "mr_commented"],
        labels={"value": "Count", "index": "Project", "variable": "MR Type"},
        color_discrete_map={
            "mr_opened": PRIMARY,
            "mr_merged": SECONDARY,
            "mr_approved": ACCENT,
            "mr_commented": HIGHLIGHT,
        },
    )
    fig.update_layout(height=500, barmode="stack", xaxis_tickangle=-45)
    return fig


def build_comparison_chart(metric_df):
    """Build grouped code-vs-collaboration comparison chart."""
    comparison_df = (
        metric_df[["code_contributions", "collab_contributions"]]
        .sort_values("code_contributions", ascending=False)
        .head(20)
    )
    fig = px.bar(
        comparison_df,
        x=comparison_df.index,
        y=["code_contributions", "collab_contributions"],
        labels={"value": "Contributions", "index": "Project", "variable": "Type"},
        color_discrete_map={
            "code_contributions": PRIMARY,
            "collab_contributions": SECONDARY,
        },
    )
    fig.update_layout(height=500, barmode="group", xaxis_tickangle=-45)
    return fig


def build_activity_heatmap(metric_df, use_log_scale):
    """Build activity heatmap with optional log scaling."""
    heatmap_data = metric_df[
        [
            "commits",
            "mr_opened",
            "mr_merged",
            "mr_approved",
            "issue_opened",
            "branch_created",
        ]
    ].head(20)
    heatmap_plot_data = np.log1p(heatmap_data) if use_log_scale else heatmap_data

    fig = px.imshow(
        heatmap_plot_data.T,
        labels={"x": "Project", "y": "Activity Type", "color": "Count"},
        x=heatmap_data.index,
        y=heatmap_data.columns,
        color_continuous_scale=HEATMAP_SCALE,
        aspect="auto",
    )
    if use_log_scale:
        fig.update_coloraxes(colorbar_title="log(1 + count)")
    fig.update_layout(height=500)
    return fig


def build_top_projects_chart(metric_df, top_n):
    """Build top projects by total contributions chart."""
    top_projects = (
        metric_df[["total_contributions"]]
        .sort_values("total_contributions", ascending=True)
        .tail(top_n)
    )
    top_projects_plot = top_projects.reset_index().rename(columns={"index": "project"})
    fig = px.bar(
        top_projects_plot,
        x="total_contributions",
        y="project",
        color="total_contributions",
        orientation="h",
        color_continuous_scale=CONTINUOUS_SCALE,
        labels={"total_contributions": "Total Contributions", "project": "Project"},
        text="total_contributions",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False, height=400)
    return fig


def build_contribution_style_chart(metric_df, top_n):
    """Build chart for project code-percentage contribution style."""
    style_df = (
        metric_df[["code_pct"]].sort_values("code_pct", ascending=False).head(top_n)
    )
    style_df_plot = style_df.reset_index().rename(columns={"index": "project"})
    fig = px.bar(
        style_df_plot,
        x="code_pct",
        y="project",
        orientation="h",
        color="code_pct",
        color_continuous_scale=CONTINUOUS_SCALE,
        labels={"code_pct": "Code Contribution %", "project": "Project"},
        text=style_df_plot["code_pct"].round(1),
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(height=400)
    return fig


def build_project_pie(project_data):
    """Build code-vs-collaboration pie chart for selected project."""
    fig = px.pie(
        names=["Code Contributions", "Collaboration"],
        values=[
            project_data["code_contributions"],
            project_data["collab_contributions"],
        ],
        color_discrete_sequence=[PRIMARY, SECONDARY],
        hole=0.35,
    )
    fig.update_layout(height=400)
    return fig


def build_project_activity_bar(project_data):
    """Build selected project activity breakdown bar chart."""
    fig = px.bar(
        x=[
            "Commits",
            "MR Opened",
            "MR Merged",
            "MR Approved",
            "MR Commented",
            "Branch Created",
            "Branch Deleted",
            "Issues",
        ],
        y=[
            project_data["commits"],
            project_data["mr_opened"],
            project_data["mr_merged"],
            project_data["mr_approved"],
            project_data["mr_commented"],
            project_data["branch_created"],
            project_data["branch_deleted"],
            project_data["issue_opened"],
        ],
        color=[
            project_data["commits"],
            project_data["mr_opened"],
            project_data["mr_merged"],
            project_data["mr_approved"],
            project_data["mr_commented"],
            project_data["branch_created"],
            project_data["branch_deleted"],
            project_data["issue_opened"],
        ],
        color_continuous_scale=CONTINUOUS_SCALE,
        labels={"x": "Activity Type", "y": "Count"},
    )
    fig.update_layout(
        showlegend=False,
        height=400,
        xaxis_tickangle=-45,
    )
    return fig


def build_daily_activity_trend(timeline_df):
    """Build daily activity line chart with 7-day moving average."""
    return _build_daily_trend_chart(
        timeline_df,
        metric_key="total_contributions",
        metric_label="Daily Total",
        metric_color=PRIMARY,
        y_axis_title="Contributions",
        height=380,
    )


def _build_daily_trend_chart(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    timeline_df,
    metric_key,
    metric_label,
    metric_color,
    y_axis_title,
    height=340,
):
    """Build daily metric trend chart with a 7-day rolling average."""
    timeline = timeline_df.copy()
    timeline["event_date"] = pd.to_datetime(timeline["event_date"])
    timeline = timeline.sort_values("event_date")
    timeline["rolling_7d"] = timeline[metric_key].rolling(7, min_periods=1).mean()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=timeline["event_date"],
            y=timeline[metric_key],
            mode="lines",
            name=metric_label,
            line={"color": metric_color, "width": 2},
        ),
    )
    fig.add_trace(
        go.Scatter(
            x=timeline["event_date"],
            y=timeline["rolling_7d"],
            mode="lines",
            name="7-Day Average",
            line={"color": SECONDARY, "width": 2, "dash": "dash"},
        ),
    )
    fig.update_layout(height=height, xaxis_title="Date", yaxis_title=y_axis_title)
    return fig


def build_weekly_mix_chart(timeline_df):
    """Build weekly stacked bar chart for code vs collaboration mix."""
    timeline = timeline_df.copy()
    timeline["event_date"] = pd.to_datetime(timeline["event_date"])
    weekly = (
        timeline.set_index("event_date")[["code_contributions", "collab_contributions"]]
        .resample("W-MON")
        .sum()
        .reset_index()
    )

    fig = px.bar(
        weekly,
        x="event_date",
        y=["code_contributions", "collab_contributions"],
        labels={"event_date": "Week", "value": "Contributions", "variable": "Type"},
        color_discrete_map={
            "code_contributions": PRIMARY,
            "collab_contributions": SECONDARY,
        },
    )
    fig.update_layout(height=380, barmode="stack")
    return fig


def build_monthly_volume_chart(timeline_df):
    """Build monthly contribution volume bar chart."""
    timeline = timeline_df.copy()
    timeline["event_date"] = pd.to_datetime(timeline["event_date"])
    monthly = (
        timeline.set_index("event_date")[["total_contributions"]]
        .resample("MS")
        .sum()
        .reset_index()
    )

    fig = px.bar(
        monthly,
        x="event_date",
        y="total_contributions",
        labels={"event_date": "Month", "total_contributions": "Contributions"},
        color_discrete_sequence=[ACCENT],
    )
    fig.update_xaxes(
        tickmode="array",
        tickvals=monthly["event_date"],
        tickformat="%b %Y",
    )
    fig.update_layout(height=360)
    return fig


def build_jira_top_projects_chart(metric_df, top_n, metric_key, title, label):
    """Build a horizontal bar chart for Jira project rankings."""
    top_projects = (
        metric_df[[metric_key]].sort_values(metric_key, ascending=True).tail(top_n)
    )
    top_projects_plot = top_projects.reset_index().rename(columns={"index": "project"})
    fig = px.bar(
        top_projects_plot,
        x=metric_key,
        y="project",
        color=metric_key,
        orientation="h",
        color_continuous_scale=CONTINUOUS_SCALE,
        labels={metric_key: label, "project": "Project"},
        text=metric_key,
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False, height=420, title=title)
    return fig


def build_jira_activity_chart(metric_df):
    """Build stacked Jira activity chart by project."""
    jira_activity = (
        metric_df[["jira_issues_assigned", "jira_issues_closed", "jira_comments"]]
        .sort_values("jira_issues_closed", ascending=False)
        .head(20)
    )
    fig = px.bar(
        jira_activity,
        x=jira_activity.index,
        y=["jira_issues_assigned", "jira_issues_closed", "jira_comments"],
        labels={"value": "Count", "index": "Project", "variable": "Metric"},
        color_discrete_map={
            "jira_issues_assigned": PRIMARY,
            "jira_issues_closed": SECONDARY,
            "jira_comments": ACCENT,
        },
    )
    fig.update_layout(height=480, barmode="stack", xaxis_tickangle=-45)
    return fig


def build_jira_project_details_bar(project_data):
    """Build per-project Jira activity bar chart."""
    fig = px.bar(
        x=["Issues Assigned", "Issues Closed", "Comments", "Story Points Closed"],
        y=[
            project_data["jira_issues_assigned"],
            project_data["jira_issues_closed"],
            project_data["jira_comments"],
            project_data["jira_story_points_closed"],
        ],
        color=[
            project_data["jira_issues_assigned"],
            project_data["jira_issues_closed"],
            project_data["jira_comments"],
            project_data["jira_story_points_closed"],
        ],
        color_continuous_scale=CONTINUOUS_SCALE,
        labels={"x": "Jira Metric", "y": "Count"},
    )
    fig.update_layout(showlegend=False, height=400, xaxis_tickangle=-45)
    return fig


def build_jira_daily_closed_chart(timeline_df):
    """Build Jira daily closed issues time series chart."""
    return _build_jira_daily_trend_chart(
        timeline_df,
        metric_key="jira_issues_closed",
        metric_label="Issues Closed",
        metric_color=PRIMARY,
        y_axis_title="Closed Issues",
    )


def build_jira_daily_comments_chart(timeline_df):
    """Build Jira daily comment activity time series chart."""
    return _build_jira_daily_trend_chart(
        timeline_df,
        metric_key="jira_comments",
        metric_label="Comments",
        metric_color=ACCENT,
        y_axis_title="Comments",
    )


def build_jira_daily_story_points_chart(timeline_df):
    """Build Jira daily story points closed time series chart."""
    return _build_jira_daily_trend_chart(
        timeline_df,
        metric_key="jira_story_points_closed",
        metric_label="Story Points Closed",
        metric_color=HIGHLIGHT,
        y_axis_title="Story Points",
    )


def _build_jira_daily_trend_chart(
    timeline_df,
    metric_key,
    metric_label,
    metric_color,
    y_axis_title,
):
    """Build Jira daily metric chart with 7-day rolling average."""
    return _build_daily_trend_chart(
        timeline_df,
        metric_key=metric_key,
        metric_label=metric_label,
        metric_color=metric_color,
        y_axis_title=y_axis_title,
    )
