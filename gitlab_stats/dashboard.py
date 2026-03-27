"""Generate a Streamlit dashboard to visualize GitLab contributions metrics."""

import os
from pathlib import Path
from time import perf_counter

import streamlit as st
from dotenv import load_dotenv

from gitlab_stats import config
from gitlab_stats.dashboard_utils.helpers import inject_dashboard_styles
from gitlab_stats.dashboard_utils.helpers import prepare_metric_df
from gitlab_stats.dashboard_utils.helpers import render_main_header
from gitlab_stats.dashboard_utils.helpers import resolve_selected_path
from gitlab_stats.dashboard_utils.sections import render_behavior_analysis
from gitlab_stats.dashboard_utils.sections import render_breakdown_tabs
from gitlab_stats.dashboard_utils.sections import render_contribution_distribution
from gitlab_stats.dashboard_utils.sections import render_executive_summary
from gitlab_stats.dashboard_utils.sections import render_export
from gitlab_stats.dashboard_utils.sections import render_key_insights
from gitlab_stats.dashboard_utils.sections import render_performance_tabs
from gitlab_stats.dashboard_utils.sections import render_profile
from gitlab_stats.dashboard_utils.sections import render_project_deep_dive
from gitlab_stats.dashboard_utils.sections import render_top_projects
from gitlab_stats.gitlab_stats_api_ingester import fetch_metrics_from_api_with_time
from gitlab_stats.gitlab_stats_parser import _parse_gitlab_log

# Load environment variables from .env file if it exists
load_dotenv()

DEFAULT_FILE_PATH = "gitlab_contributions.txt"
PLACEHOLDER_FILE_PATH = "doc/gitlab_contributions_placeholder.txt"
CACHE_TTL_SECONDS = int(getattr(config, "DATA_CACHE_TTL_SECONDS", 1800))


def _normalize_metrics_for_cache(metrics, total_metrics):
    """Convert mapping outputs to plain dicts for cache serialization."""
    normalized_metrics = {
        str(project): {str(key): value for key, value in dict(data).items()}
        for project, data in dict(metrics).items()
    }
    normalized_totals = {str(key): value for key, value in dict(total_metrics).items()}
    return normalized_metrics, normalized_totals


@st.cache_data(show_spinner=False, ttl=CACHE_TTL_SECONDS)
def _load_metrics_cached(
    request: dict[str, object],
):
    """Load metrics with cache key driven by source config and inputs."""
    use_api = bool(request.get("use_api", False))
    selected_path = str(request.get("selected_path", ""))
    api_base_url = str(request.get("api_base_url", ""))
    api_token = str(request.get("api_token", ""))

    if use_api and api_base_url and api_token:
        result = fetch_metrics_from_api_with_time()
        if result is not None:
            metrics, total_metrics, timeline_df, timeline_meta = result
            timeline_meta["source"] = "api"
            normalized_metrics, normalized_totals = _normalize_metrics_for_cache(
                metrics,
                total_metrics,
            )
            return normalized_metrics, normalized_totals, timeline_df, timeline_meta

    if not selected_path:
        return None

    metrics, total_metrics = _parse_gitlab_log(selected_path)
    normalized_metrics, normalized_totals = _normalize_metrics_for_cache(
        metrics,
        total_metrics,
    )
    timeline_meta = {
        "source": "parser",
        "has_real_dates": False,
        "using_synthetic_timeline": False,
    }
    timeline_df = None
    return normalized_metrics, normalized_totals, timeline_df, timeline_meta


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


def get_metrics():
    """Fetch metrics from configured source (API with fallback to parser).

    Returns:
        Tuple of metrics, totals, timeline dataframe, and timeline metadata.
    """
    api_base_url = os.getenv("GITLAB_API_BASE_URL", "")
    api_token = os.getenv("GITLAB_API_TOKEN", "")

    if config.USE_API:
        api_start = perf_counter()
        with st.spinner("Fetching metrics from GitLab API..."):
            result = _load_metrics_cached(
                {
                    "use_api": True,
                    "selected_path": "",
                    "parser_file_mtime_ns": 0,
                    "api_base_url": api_base_url,
                    "api_token": api_token,
                    "api_lookback_days": config.API_LOOKBACK_DAYS,
                    "api_events_per_page": config.API_EVENTS_PER_PAGE,
                    "api_max_event_pages": config.API_MAX_EVENT_PAGES,
                },
            )
        api_elapsed = perf_counter() - api_start

        if result is not None:
            if config.SHOW_DATA_SOURCE_INFO:
                st.info(f"📊 Metrics loaded from GitLab API in {api_elapsed:.2f}s")
            if st.button("Refresh Data Cache", key="refresh_cache_api"):
                st.cache_data.clear()
                st.rerun()
            return result

        st.warning("API data unavailable. Falling back to local parser data.")

    selected_path = select_data_source()
    parser_path = Path(selected_path)
    parser_mtime_ns = parser_path.stat().st_mtime_ns if parser_path.exists() else 0
    parser_start = perf_counter()
    with st.spinner("Parsing local contributions file..."):
        result = _load_metrics_cached(
            {
                "use_api": False,
                "selected_path": str(parser_path),
                "parser_file_mtime_ns": parser_mtime_ns,
                "api_base_url": api_base_url,
                "api_token": api_token,
                "api_lookback_days": config.API_LOOKBACK_DAYS,
                "api_events_per_page": config.API_EVENTS_PER_PAGE,
                "api_max_event_pages": config.API_MAX_EVENT_PAGES,
            },
        )
    parser_elapsed = perf_counter() - parser_start

    if config.SHOW_DATA_SOURCE_INFO:
        st.info(f"📄 Metrics loaded from local file parser in {parser_elapsed:.2f}s")
        if st.button("Refresh Data Cache", key="refresh_cache_parser"):
            st.cache_data.clear()
            st.rerun()
    return result


def main():
    """Run the dashboard app."""
    configure_page()

    metrics, total_metrics, timeline_df, timeline_meta = get_metrics()
    metric_df, ordered_columns = prepare_metric_df(metrics)

    render_executive_summary(metric_df, total_metrics)
    render_profile(metric_df, total_metrics)
    render_behavior_analysis(timeline_df, timeline_meta)
    render_key_insights(metric_df, total_metrics)
    render_contribution_distribution(metric_df)
    render_breakdown_tabs(metric_df, total_metrics)
    render_performance_tabs(metric_df)
    render_top_projects(metric_df)
    render_project_deep_dive(metric_df, ordered_columns)
    render_export(metric_df)


if __name__ == "__main__":
    main()
