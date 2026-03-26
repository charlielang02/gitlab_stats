"""Generate a Streamlit dashboard to visualize GitLab contributions metrics."""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from gitlab_stats.gitlab_stats_parser import _parse_gitlab_log

st.set_page_config(
    layout="wide",
    page_title="GitLab Contributions Dashboard",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .main-header {
            font-size: 2.5em;
            font-weight: bold;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 1rem;
        }
        .insight-box {
            background-color: #e7f3ff;
            color: #0f172a;
            padding: 1rem;
            border-radius: 0.5rem;
            border-left: 4px solid #0066cc;
        }
        .insight-box strong {
            color: #0f172a;
        }
        .project-metrics-table {
            width: 100%;
            border-collapse: collapse;
        }
        .project-metrics-table th {
            background-color: #f0f2f6;
            color: #262730;
            text-align: left;
            padding: 0.55rem;
            border: 1px solid #e6e9ef;
        }
        .project-metrics-table td {
            padding: 0.55rem;
            border: 1px solid #e6e9ef;
        }
        @media (prefers-color-scheme: dark) {
            .insight-box {
                background-color: #1f2937;
                color: #e5e7eb;
                border-left: 4px solid #60a5fa;
            }
            .insight-box strong {
                color: #f3f4f6;
            }
            .project-metrics-table th {
                background-color: #262730;
                color: #fafafa;
                border: 1px solid #3a3f4b;
            }
            .project-metrics-table td {
                border: 1px solid #3a3f4b;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="main-header">📊 GitLab Contributions Dashboard</div>',
    unsafe_allow_html=True,
)

DEFAULT_FILE_PATH = "gitlab_contributions.txt"
PLACEHOLDER_FILE_PATH = "doc/gitlab_contributions_placeholder.txt"

file_path = st.text_input(
    "📁 Path to contributions file",
    value=DEFAULT_FILE_PATH,
)

if not file_path:
    st.stop()

selected_path = Path(file_path)
placeholder_path = Path(PLACEHOLDER_FILE_PATH)
using_placeholder = False  # pylint: disable=invalid-name

if not selected_path.exists():
    if placeholder_path.exists():
        using_placeholder = True  # pylint: disable=invalid-name
        selected_path = placeholder_path
    else:
        st.error(
            "No contributions file was found, and the placeholder file is missing.",
        )
        st.stop()

if using_placeholder:
    st.warning(
        "Placeholder data is currently shown. Numbers and projects are fake demo data.",
    )

metrics, total_metrics = _parse_gitlab_log(str(selected_path))

metric_df = pd.DataFrame.from_dict(metrics, orient="index").fillna(0)

ordered_categories = [
    "commits",
    "mr_opened",
    "mr_merged",
    "mr_approved",
    "mr_commented",
    "branch_created",
    "branch_deleted",
    "issue_opened",
    "code_contributions",
    "collab_contributions",
    "total_contributions",
    "code_pct",
    "collab_pct",
]
ordered_columns = [col for col in ordered_categories if col in metric_df.columns]
remaining_columns = [col for col in metric_df.columns if col not in ordered_columns]
metric_df = metric_df[ordered_columns + remaining_columns]

metric_df = metric_df.sort_values(by="total_contributions", ascending=False)

st.header("📈 Executive Summary")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Contributions", int(total_metrics["total_contributions"]))
col2.metric("Code Contributions", int(total_metrics["code_contributions"]))
col3.metric("Collaboration Contributions", int(total_metrics["collab_contributions"]))
col4.metric("Projects Contributed", len(metric_df))

summary_col1, summary_col2, summary_col3 = st.columns(3)
with summary_col1:
    avg_commits = metric_df["commits"].mean()
    st.metric("Avg Commits/Project", f"{avg_commits:.1f}")

with summary_col2:
    avg_mrs = (metric_df["mr_opened"] + metric_df["mr_merged"]).mean()
    st.metric("Avg MRs/Project", f"{avg_mrs:.1f}")

with summary_col3:
    code_pct = total_metrics.get("code_pct", 0)
    st.metric("Code vs Collab", f"{code_pct:.1f}% Code")

st.markdown("---")

st.header("🎯 Key Insights")

insight_col1, insight_col2, insight_col3 = st.columns(3)

with insight_col1:
    top_project = metric_df.iloc[0]
    st.markdown(
        f"""
    <div class="insight-box">
    <strong>🏆 Top Contributor Project</strong><br>
    {metric_df.index[0]}<br>
    {int(top_project['total_contributions'])} contributions
    </div>
    """,
        unsafe_allow_html=True,
    )

with insight_col2:
    commit_velocity = (
        metric_df["commits"].sum() / len(metric_df) if len(metric_df) > 0 else 0
    )
    st.markdown(
        f"""
    <div class="insight-box">
    <strong>⚡ Commit Velocity</strong><br>
    {commit_velocity:.1f} commits/project<br>
    {int(metric_df["commits"].sum())} total commits
    </div>
    """,
        unsafe_allow_html=True,
    )

with insight_col3:
    collaboration_ratio = (
        total_metrics["collab_contributions"] / total_metrics["total_contributions"]
        if total_metrics["total_contributions"] > 0
        else 0
    )
    st.markdown(
        f"""
    <div class="insight-box">
    <strong>🤝 Collaboration Index</strong><br>
    {collaboration_ratio * 100:.1f}% collaborative<br>
    {int(total_metrics['collab_contributions'])} collab contributions
    </div>
    """,
        unsafe_allow_html=True,
    )

st.markdown("---")

st.header("📊 Contribution Breakdown")

breakdown_tabs = st.tabs(["Overview", "Detailed Table", "All Charts"])

with breakdown_tabs[0]:
    pie_col1, pie_col2 = st.columns(2)

    with pie_col1:
        st.subheader("💡 Code vs Collaboration")
        code_collab_data = {
            "Code Contributions": int(total_metrics["code_contributions"]),
            "Collaboration": int(total_metrics["collab_contributions"]),
        }
        fig1 = px.pie(
            names=list(code_collab_data.keys()),
            values=list(code_collab_data.values()),
            color_discrete_sequence=["#667eea", "#764ba2"],
            hole=0.35,
        )
        fig1.update_layout(height=400)
        st.plotly_chart(fig1, width="stretch")

    with pie_col2:
        st.subheader("📈 Contribution Type Distribution")
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
        type_dist = {k: v for k, v in type_dist.items() if v > 0}
        fig2 = px.pie(
            names=list(type_dist.keys()),
            values=list(type_dist.values()),
            color_discrete_sequence=px.colors.qualitative.Set3,
        )
        fig2.update_layout(height=400)
        st.plotly_chart(fig2, width="stretch")

with breakdown_tabs[1]:
    st.subheader("📋 Per Project Detailed Breakdown")
    st.dataframe(metric_df, width="stretch", height=500)

with breakdown_tabs[2]:
    st.subheader("Distribution by Project")
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        fig_dist = go.Figure()
        fig_dist.add_trace(
            go.Box(y=metric_df["commits"], name="Commits", marker_color="indianred"),
        )
        fig_dist.add_trace(
            go.Box(
                y=metric_df["mr_opened"] + metric_df["mr_merged"],
                name="Total MRs",
                marker_color="lightsalmon",
            ),
        )
        fig_dist.add_trace(
            go.Box(
                y=metric_df["issue_opened"],
                name="Issues",
                marker_color="lightseagreen",
            ),
        )
        fig_dist.update_layout(
            height=400,
            title="Distribution of Metrics Across Projects",
        )
        st.plotly_chart(fig_dist, width="stretch")

    with chart_col2:
        fig_scatter = px.scatter(
            metric_df,
            x="commits",
            y="mr_opened",
            size="total_contributions",
            hover_name=metric_df.index,
            color="code_pct",
            color_continuous_scale="Viridis",
            labels={
                "commits": "Commits",
                "mr_opened": "MRs Opened",
                "code_pct": "Code %",
            },
        )
        fig_scatter.update_layout(height=400, title="Commits vs MRs by Project")
        st.plotly_chart(fig_scatter, width="stretch")

st.markdown("---")

st.header("⚡ Performance Metrics")

metric_tabs = st.tabs(
    [
        "Commit Velocity",
        "Collaboration Activity",
        "Project Comparison",
        "Activity Heatmap",
    ],
)

with metric_tabs[0]:
    st.subheader("🔥 Commit Velocity by Project")
    commit_df = metric_df[["commits"]].sort_values("commits", ascending=True).tail(20)
    commit_df_plot = commit_df.reset_index().rename(columns={"index": "project"})
    fig_commits = px.bar(
        commit_df_plot,
        x="commits",
        y="project",
        color="commits",
        orientation="h",
        color_continuous_scale="Viridis",
        labels={"commits": "Commit Count", "project": "Project"},
    )
    fig_commits.update_layout(showlegend=False, height=500)
    st.plotly_chart(fig_commits, width="stretch")

    velocity_col1, velocity_col2, velocity_col3, velocity_col4 = st.columns(4)
    with velocity_col1:
        st.metric("Total Commits", int(metric_df["commits"].sum()))
    with velocity_col2:
        st.metric("Max Commits/Project", int(metric_df["commits"].max()))
    with velocity_col3:
        st.metric("Median Commits", f"{metric_df['commits'].median():.0f}")
    with velocity_col4:
        st.metric("Std Dev", f"{metric_df['commits'].std():.1f}")

with metric_tabs[1]:
    st.subheader("🤝 Merge Request & Code Review Activity")
    mr_activity = (
        metric_df[["mr_opened", "mr_merged", "mr_approved", "mr_commented"]]
        .sort_values("mr_opened", ascending=False)
        .head(20)
    )
    fig_mr = px.bar(
        mr_activity,
        x=mr_activity.index,
        y=["mr_opened", "mr_merged", "mr_approved", "mr_commented"],
        labels={"value": "Count", "index": "Project", "variable": "MR Type"},
        color_discrete_map={
            "mr_opened": "#667eea",
            "mr_merged": "#764ba2",
            "mr_approved": "#f093fb",
            "mr_commented": "#4facfe",
        },
    )
    fig_mr.update_layout(height=500, barmode="stack", xaxis_tickangle=-45)
    st.plotly_chart(fig_mr, width="stretch")

    mr_col1, mr_col2, mr_col3 = st.columns(3)
    with mr_col1:
        st.metric("Total MRs Opened", int(metric_df["mr_opened"].sum()))
    with mr_col2:
        st.metric("Total MRs Merged", int(metric_df["mr_merged"].sum()))
    with mr_col3:
        merge_rate = (
            (metric_df["mr_merged"].sum() / metric_df["mr_opened"].sum() * 100)
            if metric_df["mr_opened"].sum() > 0
            else 0
        )
        st.metric("Merge Success Rate", f"{merge_rate:.1f}%")

with metric_tabs[2]:
    st.subheader("🎯 Project Comparison: Code vs Collaboration")
    comparison_df = (
        metric_df[["code_contributions", "collab_contributions"]]
        .sort_values("code_contributions", ascending=False)
        .head(20)
    )
    fig_comp = px.bar(
        comparison_df,
        x=comparison_df.index,
        y=["code_contributions", "collab_contributions"],
        labels={"value": "Contributions", "index": "Project", "variable": "Type"},
        color_discrete_map={
            "code_contributions": "#667eea",
            "collab_contributions": "#764ba2",
        },
    )
    fig_comp.update_layout(height=500, barmode="group", xaxis_tickangle=-45)
    st.plotly_chart(fig_comp, width="stretch")

with metric_tabs[3]:
    st.subheader("🔥 Activity Heatmap")

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

    use_log_scale = st.checkbox(
        "Use logarithmic color scale",
        value=True,
        help="Compresses outliers so lower-activity projects remain visible.",
    )
    heatmap_plot_data = np.log1p(heatmap_data) if use_log_scale else heatmap_data

    fig_heatmap = px.imshow(
        heatmap_plot_data.T,
        labels={"x": "Project", "y": "Activity Type", "color": "Count"},
        x=heatmap_data.index,
        y=heatmap_data.columns,
        color_continuous_scale="YlOrRd",
        aspect="auto",
    )
    if use_log_scale:
        fig_heatmap.update_coloraxes(colorbar_title="log(1 + count)")
    fig_heatmap.update_layout(height=500)
    st.plotly_chart(fig_heatmap, width="stretch")

st.markdown("---")

st.header("🏆 Top Projects Analysis")

top_n = st.slider(
    "Number of projects to display",
    3,
    len(metric_df),
    min(10, len(metric_df)),
)

col_bars_1, col_bars_2 = st.columns(2)

with col_bars_1:
    st.subheader("🥇 Top Projects by Total Contributions")
    top_projects = (
        metric_df[["total_contributions"]]
        .sort_values("total_contributions", ascending=True)
        .tail(top_n)
    )
    top_projects_plot = top_projects.reset_index().rename(columns={"index": "project"})
    fig_top = px.bar(
        top_projects_plot,
        x="total_contributions",
        y="project",
        color="total_contributions",
        orientation="h",
        color_continuous_scale="Blues",
        labels={"total_contributions": "Total Contributions", "project": "Project"},
        text="total_contributions",
    )
    fig_top.update_traces(textposition="outside")
    fig_top.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig_top, width="stretch")

with col_bars_2:
    st.subheader("📊 Contribution Style by Project")
    style_df = (
        metric_df[["code_pct"]].sort_values("code_pct", ascending=False).head(top_n)
    )
    style_df_plot = style_df.reset_index().rename(columns={"index": "project"})
    fig_style = px.bar(
        style_df_plot,
        x="code_pct",
        y="project",
        orientation="h",
        color="code_pct",
        color_continuous_scale=["#764ba2", "#667eea"],
        labels={"code_pct": "Code Contribution %", "project": "Project"},
        text=style_df_plot["code_pct"].round(1),
    )
    fig_style.update_traces(textposition="outside")
    fig_style.update_layout(height=400)
    st.plotly_chart(fig_style, width="stretch")

st.markdown("---")

st.header("🔍 Detailed Project Deep Dive")

selected_project = st.selectbox("Select Project", metric_df.index)

if selected_project:
    project_data = metric_df.loc[selected_project]

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader(f"📍 {selected_project}")

        project_col1, project_col2, project_col3 = st.columns(3)
        with project_col1:
            st.metric("Total Contributions", int(project_data["total_contributions"]))
        with project_col2:
            st.metric("Code Contributions", int(project_data["code_contributions"]))
        with project_col3:
            st.metric(
                "Collaboration Contributions",
                int(project_data["collab_contributions"]),
            )

    with col_right:
        project_meta_col1, project_meta_col2 = st.columns(2)
        with project_meta_col1:
            st.metric(
                "Code %",
                f"{project_data['code_pct']:.1f}%",
            )
        with project_meta_col2:
            st.metric(
                "Collab %",
                f"{project_data['collab_pct']:.1f}%",
            )

    st.subheader("📈 Project Metrics Breakdown")
    project_metrics_df = (
        project_data[ordered_columns]
        .rename_axis("Metric")
        .reset_index(
            name="Value",
        )
    )
    pct_metrics = {"code_pct", "collab_pct"}
    project_metrics_df["Value"] = [
        f"{value:.1f}" if metric in pct_metrics else f"{int(value)}"
        for metric, value in zip(
            project_metrics_df["Metric"],
            project_metrics_df["Value"],
            strict=False,
        )
    ]
    project_metrics_html = project_metrics_df.to_html(
        index=False,
        classes="project-metrics-table",
        border=0,
    )
    st.markdown(project_metrics_html, unsafe_allow_html=True)

    st.subheader("📊 Activity Details")
    activity_col1, activity_col2 = st.columns(2)

    with activity_col1:
        fig_project_pie = px.pie(
            names=["Code Contributions", "Collaboration"],
            values=[
                project_data["code_contributions"],
                project_data["collab_contributions"],
            ],
            color_discrete_sequence=["#667eea", "#764ba2"],
            hole=0.35,
        )
        fig_project_pie.update_layout(height=400)
        st.plotly_chart(fig_project_pie, width="stretch")

    with activity_col2:
        fig_project_bar = px.bar(
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
            color_continuous_scale="Viridis",
            labels={"x": "Activity Type", "y": "Count"},
        )
        fig_project_bar.update_layout(
            showlegend=False,
            height=400,
            xaxis_tickangle=-45,
        )
        st.plotly_chart(fig_project_bar, width="stretch")

st.markdown("---")

st.header("📥 Data Export")
csv = metric_df.to_csv(index=True)
st.download_button(
    label="Download Full Dataset as CSV",
    data=csv,
    file_name="gitlab_contributions_export.csv",
    mime="text/csv",
)
