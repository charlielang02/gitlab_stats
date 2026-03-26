"""Generate a Streamlit dashboard to visualize GitLab contributions metrics."""

from pathlib import Path

import streamlit as st

from gitlab_stats.dashboard_utils.helpers import inject_dashboard_styles
from gitlab_stats.dashboard_utils.helpers import prepare_metric_df
from gitlab_stats.dashboard_utils.helpers import render_main_header
from gitlab_stats.dashboard_utils.helpers import resolve_selected_path
from gitlab_stats.dashboard_utils.sections import render_breakdown_tabs
from gitlab_stats.dashboard_utils.sections import render_contribution_distribution
from gitlab_stats.dashboard_utils.sections import render_executive_summary
from gitlab_stats.dashboard_utils.sections import render_export
from gitlab_stats.dashboard_utils.sections import render_key_insights
from gitlab_stats.dashboard_utils.sections import render_performance_tabs
from gitlab_stats.dashboard_utils.sections import render_profile
from gitlab_stats.dashboard_utils.sections import render_project_deep_dive
from gitlab_stats.dashboard_utils.sections import render_top_projects
from gitlab_stats.gitlab_stats_parser import _parse_gitlab_log

DEFAULT_FILE_PATH = "gitlab_contributions.txt"
PLACEHOLDER_FILE_PATH = "doc/gitlab_contributions_placeholder.txt"


def configure_page():
    """Configure Streamlit page and shared visual styles."""
    st.set_page_config(
        layout="wide",
        page_title="GitLab Contributions Dashboard",
        initial_sidebar_state="expanded",
    )
    inject_dashboard_styles()
    render_main_header()


def select_data_source():
    """Resolve source file path from user input with placeholder fallback."""
    file_path = st.text_input(
        "📁 Path to contributions file",
        value=DEFAULT_FILE_PATH,
    )
    if not file_path:
        st.stop()

    selected_path, using_placeholder = resolve_selected_path(
        file_path,
        PLACEHOLDER_FILE_PATH,
    )
    if selected_path is None:
        st.error(
            "No contributions file was found, and the placeholder file is missing.",
        )
        st.stop()

    if using_placeholder:
        st.warning(
            "Placeholder data is currently shown. Numbers and projects are fake demo data.",
        )

    return selected_path


def main():
    """Run the dashboard app."""
    configure_page()

    selected_path = select_data_source()
    metrics, total_metrics = _parse_gitlab_log(str(Path(selected_path)))
    metric_df, ordered_columns = prepare_metric_df(metrics)

    render_executive_summary(metric_df, total_metrics)
    render_profile(metric_df, total_metrics)
    render_key_insights(metric_df, total_metrics)
    render_contribution_distribution(metric_df)
    render_breakdown_tabs(metric_df, total_metrics)
    render_performance_tabs(metric_df)
    render_top_projects(metric_df)
    render_project_deep_dive(metric_df, ordered_columns)
    render_export(metric_df)


if __name__ == "__main__":
    main()
