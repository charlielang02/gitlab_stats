"""Generate a Streamlit dashboard to visualize GitLab contributions metrics."""

import io
import os
from pathlib import Path
from time import perf_counter

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from gitlab_stats import config
from gitlab_stats.dashboard_utils.helpers import ORDERED_CATEGORIES
from gitlab_stats.dashboard_utils.helpers import inject_dashboard_styles
from gitlab_stats.dashboard_utils.helpers import prepare_metric_df
from gitlab_stats.dashboard_utils.helpers import render_main_header
from gitlab_stats.dashboard_utils.helpers import resolve_selected_path
from gitlab_stats.dashboard_utils.metrics_schema import BASE_METRIC_KEYS
from gitlab_stats.dashboard_utils.metrics_schema import TOTAL_COUNT_METRIC_KEYS
from gitlab_stats.dashboard_utils.sections import render_behavior_analysis
from gitlab_stats.dashboard_utils.sections import render_breakdown_tabs
from gitlab_stats.dashboard_utils.sections import render_contribution_distribution
from gitlab_stats.dashboard_utils.sections import render_executive_summary
from gitlab_stats.dashboard_utils.sections import render_export_with_timeline
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


def _totals_from_metric_df(metric_df):
    """Compute aggregated totals from a per-project metrics dataframe."""
    total_metrics = {}
    for key in TOTAL_COUNT_METRIC_KEYS:
        if key in metric_df.columns:
            total_metrics[key] = float(metric_df[key].fillna(0).sum())
        else:
            total_metrics[key] = 0.0

    total = float(total_metrics.get("total_contributions", 0.0))
    if total > 0:
        total_metrics["code_pct"] = round(
            100.0 * float(total_metrics.get("code_contributions", 0.0)) / total,
            1,
        )
        total_metrics["collab_pct"] = round(
            100.0 * float(total_metrics.get("collab_contributions", 0.0)) / total,
            1,
        )
    else:
        total_metrics["code_pct"] = 0.0
        total_metrics["collab_pct"] = 0.0

    return total_metrics


def _normalize_uploaded_metric_df(metric_df):
    """Normalize uploaded metric dataframe to required dashboard fields."""
    if "project" in metric_df.columns:
        metric_df = metric_df.set_index("project")
    elif "Unnamed: 0" in metric_df.columns:
        metric_df = metric_df.set_index("Unnamed: 0")
    elif metric_df.columns[0] not in set(BASE_METRIC_KEYS):
        metric_df = metric_df.set_index(metric_df.columns[0])

    numeric_columns = list(ORDERED_CATEGORIES)
    for column in numeric_columns:
        if column in metric_df.columns:
            metric_df[column] = pd.to_numeric(
                metric_df[column],
                errors="coerce",
            ).fillna(0)

    if "code_contributions" not in metric_df.columns:
        metric_df["code_contributions"] = (
            metric_df.get("commits", 0)
            + metric_df.get("branch_created", 0)
            + metric_df.get("branch_deleted", 0)
        )
    if "collab_contributions" not in metric_df.columns:
        metric_df["collab_contributions"] = (
            metric_df.get("mr_opened", 0)
            + metric_df.get("mr_merged", 0)
            + metric_df.get("mr_approved", 0)
            + metric_df.get("mr_commented", 0)
            + metric_df.get("issue_opened", 0)
        )
    if "total_contributions" not in metric_df.columns:
        metric_df["total_contributions"] = (
            metric_df["code_contributions"] + metric_df["collab_contributions"]
        )

    non_zero = metric_df["total_contributions"] > 0
    metric_df = metric_df[non_zero].copy()
    total = metric_df["total_contributions"].replace(0, pd.NA)
    metric_df["code_pct"] = (
        (100.0 * metric_df["code_contributions"] / total).fillna(0).round(1)
    )
    metric_df["collab_pct"] = (
        (100.0 * metric_df["collab_contributions"] / total).fillna(0).round(1)
    )

    metric_df.index = metric_df.index.astype(str)
    return metric_df


def _timeline_from_uploaded_df(uploaded_df):
    """Build timeline payload from uploaded CSV rows if present."""
    if "row_type" not in uploaded_df.columns:
        return None, {
            "source": "uploaded_csv",
            "has_real_dates": False,
            "using_synthetic_timeline": False,
        }

    timeline_rows = uploaded_df[uploaded_df["row_type"] == "timeline_day"].copy()
    if timeline_rows.empty:
        return None, {
            "source": "uploaded_csv",
            "has_real_dates": False,
            "using_synthetic_timeline": False,
        }

    drop_cols = [
        column for column in ("row_type", "project") if column in timeline_rows.columns
    ]
    timeline_rows = timeline_rows.drop(columns=drop_cols)
    if "event_date" not in timeline_rows.columns:
        return None, {
            "source": "uploaded_csv",
            "has_real_dates": False,
            "using_synthetic_timeline": False,
        }

    timeline_rows["event_date"] = pd.to_datetime(
        timeline_rows["event_date"],
        errors="coerce",
    )
    timeline_rows = timeline_rows.dropna(subset=["event_date"])
    if timeline_rows.empty:
        return None, {
            "source": "uploaded_csv",
            "has_real_dates": False,
            "using_synthetic_timeline": False,
        }

    numeric_columns = [
        *BASE_METRIC_KEYS,
        "code_contributions",
        "collab_contributions",
        "total_contributions",
    ]
    for column in numeric_columns:
        if column in timeline_rows.columns:
            timeline_rows[column] = pd.to_numeric(
                timeline_rows[column],
                errors="coerce",
            ).fillna(0)

    timeline_df = timeline_rows.sort_values("event_date").reset_index(drop=True)
    period_start = timeline_df["event_date"].min().date().isoformat()
    period_end = timeline_df["event_date"].max().date().isoformat()
    expected_days = (
        int(
            (timeline_df["event_date"].max() - timeline_df["event_date"].min()).days,
        )
        + 1
    )

    return timeline_df, {
        "source": "uploaded_csv",
        "has_real_dates": True,
        "using_synthetic_timeline": False,
        "period_start": period_start,
        "period_end": period_end,
        "expected_days": expected_days,
    }


@st.cache_data(show_spinner=False, ttl=CACHE_TTL_SECONDS)
def _load_uploaded_metrics_csv(csv_bytes):
    """Parse uploaded CSV bytes into dashboard metric payloads."""
    uploaded_df = pd.read_csv(io.BytesIO(csv_bytes))
    if uploaded_df.empty:
        return None

    if "row_type" in uploaded_df.columns:
        metric_rows = uploaded_df[uploaded_df["row_type"] == "project_metric"].copy()
        if metric_rows.empty:
            return None
        drop_cols = [
            column for column in ("row_type",) if column in metric_rows.columns
        ]
        metric_rows = metric_rows.drop(columns=drop_cols)
    else:
        metric_rows = uploaded_df

    normalized_df = _normalize_uploaded_metric_df(metric_rows)
    if normalized_df.empty:
        return None

    metrics = normalized_df.to_dict(orient="index")
    total_metrics = _totals_from_metric_df(normalized_df)
    timeline_df, timeline_meta = _timeline_from_uploaded_df(uploaded_df)
    return metrics, total_metrics, timeline_df, timeline_meta


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
    uploaded_metrics = st.file_uploader(
        "Upload metrics CSV (alternative data source)",
        type=["csv"],
        help="Use a previously exported dashboard CSV when API/network access is unavailable.",
    )

    if uploaded_metrics is not None:
        with st.spinner("Loading uploaded CSV metrics..."):
            uploaded_result = _load_uploaded_metrics_csv(uploaded_metrics.getvalue())
        if uploaded_result is None:
            st.error("Uploaded CSV is empty or does not contain usable metric columns.")
            st.stop()
        st.info("📄 Metrics loaded from uploaded CSV file")
        return uploaded_result

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

    result = get_metrics()
    if result is None:
        st.error("Unable to load metrics. Please check your data source.")
        st.stop()

    metrics, total_metrics, timeline_df, timeline_meta = result
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
    render_export_with_timeline(metric_df, timeline_df)


if __name__ == "__main__":
    main()
