"""Section renderers for the Streamlit dashboard."""

import streamlit as st

from gitlab_stats.dashboard_utils.charts import build_activity_heatmap
from gitlab_stats.dashboard_utils.charts import build_code_collab_pie
from gitlab_stats.dashboard_utils.charts import build_commit_velocity_chart
from gitlab_stats.dashboard_utils.charts import build_commits_vs_mrs_scatter
from gitlab_stats.dashboard_utils.charts import build_comparison_chart
from gitlab_stats.dashboard_utils.charts import build_contribution_style_chart
from gitlab_stats.dashboard_utils.charts import build_distribution_box
from gitlab_stats.dashboard_utils.charts import build_mr_activity_chart
from gitlab_stats.dashboard_utils.charts import build_pareto_chart
from gitlab_stats.dashboard_utils.charts import build_project_activity_bar
from gitlab_stats.dashboard_utils.charts import build_project_pie
from gitlab_stats.dashboard_utils.charts import build_top_projects_chart
from gitlab_stats.dashboard_utils.charts import build_type_distribution_pie
from gitlab_stats.dashboard_utils.helpers import SECONDARY
from gitlab_stats.dashboard_utils.helpers import compute_profile_summary
from gitlab_stats.dashboard_utils.helpers import format_project_metrics_table


def render_executive_summary(metric_df, total_metrics):
    """Render top-level KPI summary cards and averages."""
    st.header("📈 Executive Summary")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Contributions", int(total_metrics["total_contributions"]))
    col2.metric("Code Contributions", int(total_metrics["code_contributions"]))
    col3.metric(
        "Collaboration Contributions",
        int(total_metrics["collab_contributions"]),
    )
    col4.metric("Projects Contributed", len(metric_df))

    st.markdown("---")

    summary_col1, summary_col2, summary_col3 = st.columns(3)
    with summary_col1:
        st.metric("Avg Commits/Project", f"{metric_df['commits'].mean():.1f}")

    with summary_col2:
        avg_mrs = (metric_df["mr_opened"] + metric_df["mr_merged"]).mean()
        st.metric("Avg MRs/Project", f"{avg_mrs:.1f}")

    with summary_col3:
        code_pct = total_metrics.get("code_pct", 0)
        st.metric("Code vs Collab", f"{code_pct:.1f}% Code")


def render_profile(metric_df, total_metrics):
    """Render contributor profile narrative callout."""
    st.markdown("---")

    dominant_style, top_project_name, signal = compute_profile_summary(
        metric_df,
        total_metrics,
    )

    st.markdown("### 🧠 Developer Profile")
    st.info(
        f"""
You are a **{dominant_style} Contributor** across **{len(metric_df)} projects**.

- Most active project: **{top_project_name}**
- Strongest signal: {signal}
""",
    )


def render_key_insights(metric_df, total_metrics):
    """Render key insight cards for top project, velocity, and collaboration."""
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


def render_contribution_distribution(metric_df):
    """Render top-project list and Pareto concentration line chart."""
    st.markdown("---")
    st.header("📈 Contribution Distribution")

    top3 = metric_df.head(3)
    st.subheader("🥇 Top 3 Projects by Total Contributions")
    for rank, (project_name, row) in enumerate(top3.iterrows(), 1):
        st.write(
            f"{rank}. **{project_name}** — {int(row['total_contributions'])} contributions",
        )

    fig_pareto = build_pareto_chart(metric_df)
    st.plotly_chart(fig_pareto, width="stretch")


def render_breakdown_tabs(metric_df, total_metrics):
    """Render overview, detailed table, and distribution analysis tabs."""
    st.markdown("---")
    st.header("📊 Contribution Breakdown")

    breakdown_tabs = st.tabs(["Overview", "Detailed Table", "All Charts"])

    with breakdown_tabs[0]:
        pie_col1, pie_col2 = st.columns(2)

        with pie_col1:
            st.subheader("💡 Code vs Collaboration")
            fig1 = build_code_collab_pie(total_metrics)
            st.plotly_chart(fig1, width="stretch")

        with pie_col2:
            st.subheader("📈 Contribution Type Distribution")
            fig2 = build_type_distribution_pie(total_metrics)
            st.plotly_chart(fig2, width="stretch")

    with breakdown_tabs[1]:
        st.subheader("📋 Per Project Detailed Breakdown")
        st.dataframe(
            metric_df.style.highlight_max(axis=0, color=SECONDARY),
            width="stretch",
            height=500,
        )
        st.markdown(
            "Note: The table is sorted by total contributions. "
            "Highlighted values indicate the maximum for each metric across all projects.",
        )

    with breakdown_tabs[2]:
        st.subheader("Distribution by Project")
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            fig_dist = build_distribution_box(metric_df)
            st.plotly_chart(fig_dist, width="stretch")

        with chart_col2:
            fig_scatter = build_commits_vs_mrs_scatter(metric_df)
            st.plotly_chart(fig_scatter, width="stretch")


def render_performance_tabs(metric_df):
    """Render performance tabs: velocity, collaboration, comparison, and heatmap."""
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
        _render_commit_velocity_tab(metric_df)

    with metric_tabs[1]:
        _render_collaboration_activity_tab(metric_df)

    with metric_tabs[2]:
        _render_project_comparison_tab(metric_df)

    with metric_tabs[3]:
        _render_activity_heatmap_tab(metric_df)


def _render_commit_velocity_tab(metric_df):
    st.subheader("🔥 Commit Velocity by Project")
    fig_commits = build_commit_velocity_chart(metric_df)
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


def _render_collaboration_activity_tab(metric_df):
    st.subheader("🤝 Merge Request & Code Review Activity")
    fig_mr = build_mr_activity_chart(metric_df)
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


def _render_project_comparison_tab(metric_df):
    st.subheader("🎯 Project Comparison: Code vs Collaboration")
    fig_comp = build_comparison_chart(metric_df)
    st.plotly_chart(fig_comp, width="stretch")


def _render_activity_heatmap_tab(metric_df):
    st.subheader("🔥 Activity Heatmap")

    use_log_scale = st.checkbox(
        "Use logarithmic color scale",
        value=True,
        help="Compresses outliers so lower-activity projects remain visible.",
    )
    fig_heatmap = build_activity_heatmap(metric_df, use_log_scale)
    st.plotly_chart(fig_heatmap, width="stretch")


def render_top_projects(metric_df):
    """Render ranked top-project charts and style mix."""
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
        fig_top = build_top_projects_chart(metric_df, top_n)
        st.plotly_chart(fig_top, width="stretch")

    with col_bars_2:
        st.subheader("📊 Contribution Style by Project")
        fig_style = build_contribution_style_chart(metric_df, top_n)
        st.plotly_chart(fig_style, width="stretch")


def render_project_deep_dive(metric_df, ordered_columns):
    """Render project-level drill-down cards, metrics table, and charts."""
    st.markdown("---")
    st.header("🔍 Detailed Project Deep Dive")

    selected_project = st.selectbox("Select Project", metric_df.index)
    if not selected_project:
        return

    project_data = metric_df.loc[selected_project]
    _render_project_summary(selected_project, project_data)
    _render_project_metrics_table(project_data, ordered_columns)
    _render_project_activity_charts(project_data)


def _render_project_summary(selected_project, project_data):
    layout_col_left, layout_col_right = st.columns([2, 1])

    with layout_col_left:
        st.subheader(f"📍 {selected_project}")
        metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
        with metrics_col1:
            st.metric("Total Contributions", int(project_data["total_contributions"]))
        with metrics_col2:
            st.metric("Code Contributions", int(project_data["code_contributions"]))
        with metrics_col3:
            st.metric(
                "Collaboration Contributions",
                int(project_data["collab_contributions"]),
            )

    with layout_col_right:
        ratio_col1, ratio_col2 = st.columns(2)
        with ratio_col1:
            st.metric("Code %", f"{project_data['code_pct']:.1f}%")
        with ratio_col2:
            st.metric("Collab %", f"{project_data['collab_pct']:.1f}%")


def _render_project_metrics_table(project_data, ordered_columns):
    st.subheader("📈 Project Metrics Breakdown")
    metrics_html = format_project_metrics_table(project_data, ordered_columns)
    st.markdown(metrics_html, unsafe_allow_html=True)


def _render_project_activity_charts(project_data):
    st.subheader("📊 Activity Details")
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        fig_project_pie = build_project_pie(project_data)
        st.plotly_chart(fig_project_pie, width="stretch")

    with chart_col2:
        fig_project_bar = build_project_activity_bar(project_data)
        st.plotly_chart(fig_project_bar, width="stretch")


def render_export(metric_df):
    """Render one-click CSV export."""
    st.markdown("---")
    st.header("📥 Data Export")
    csv_data = metric_df.to_csv(index=True)
    st.download_button(
        label="Download Full Dataset as CSV",
        data=csv_data,
        file_name="gitlab_contributions_export.csv",
        mime="text/csv",
    )
