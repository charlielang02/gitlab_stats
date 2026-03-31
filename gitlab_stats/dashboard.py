"""Generate a Streamlit dashboard to visualize GitLab contributions metrics."""

import io
import os
from datetime import UTC
from datetime import date
from datetime import datetime
from datetime import timedelta
from time import perf_counter

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from gitlab_stats import config
from gitlab_stats.dashboard_utils.helpers import ORDERED_CATEGORIES
from gitlab_stats.dashboard_utils.helpers import inject_dashboard_styles
from gitlab_stats.dashboard_utils.helpers import prepare_metric_df
from gitlab_stats.dashboard_utils.helpers import render_main_header
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
from gitlab_stats.gitlab_stats_api_ingester import fetch_metrics_from_supabase_with_time
from gitlab_stats.gitlab_stats_api_ingester import fetch_supabase_date_bounds

# Load environment variables from .env file if it exists
load_dotenv()

CACHE_TTL_SECONDS = int(getattr(config, "DATA_CACHE_TTL_SECONDS", 1800))
MIN_WINDOW_DAYS = 7
DEFAULT_WINDOW_DAYS = 90
PRESET_WINDOW_DAYS = {
    "Last 7 days": 7,
    "Last 30 days": 30,
    "Last 90 days": 90,
    "Last 6 months": 182,
    "Last 1 year": 365,
}


def _normalize_metrics_for_cache(metrics, total_metrics):
    """Convert mapping outputs to plain dicts for cache serialization."""
    normalized_metrics = {
        str(project): {str(key): value for key, value in dict(data).items()}
        for project, data in dict(metrics).items()
    }
    normalized_totals = {str(key): value for key, value in dict(total_metrics).items()}
    return normalized_metrics, normalized_totals


def _today_utc() -> date:
    """Return the current UTC date for consistent date windows."""
    return datetime.now(tz=UTC).date()


def _parse_iso_date(value: object) -> date | None:
    """Parse ISO date strings from request payload values."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _safe_int(value: str | float | None, default: int) -> int:
    """Convert values to int with a stable fallback."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _fallback_date_bounds() -> tuple[date, date]:
    """Fallback bounds when source-derived bounds are unavailable."""
    end_date = _today_utc()
    start_date = end_date - timedelta(days=max(MIN_WINDOW_DAYS - 1, 364))
    return start_date, end_date


@st.cache_data(show_spinner=False, ttl=CACHE_TTL_SECONDS)
def _load_date_bounds_cached(
    request: dict[str, object],
) -> dict[str, str] | None:
    """Load available date bounds from live sources for timeframe controls."""
    use_supabase = bool(request.get("use_supabase", False))
    use_api = bool(request.get("use_api", False))
    supabase_url = str(request.get("supabase_url", "")).strip()
    supabase_key = str(request.get("supabase_key", "")).strip()

    if use_supabase and supabase_url and supabase_key:
        bounds = fetch_supabase_date_bounds()
        if bounds is not None:
            start_date, end_date = bounds
            return {
                "source": "supabase",
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            }

    if use_api:
        end_date = _today_utc()
        lookback_days = max(
            1,
            _safe_int(getattr(config, "API_LOOKBACK_DAYS", 365), 365),
        )
        start_date = end_date - timedelta(days=lookback_days - 1)
        return {
            "source": "api_config",
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        }

    return None


def _resolve_effective_bounds(
    bound_payload: dict[str, str] | None,
) -> tuple[date, date, str]:
    """Resolve effective timeframe bounds and source label."""
    fallback_start, fallback_end = _fallback_date_bounds()
    if not bound_payload:
        return fallback_start, fallback_end, "fallback"

    start_date = _parse_iso_date(bound_payload.get("start"))
    end_date = _parse_iso_date(bound_payload.get("end"))
    source = str(bound_payload.get("source", "fallback"))
    if start_date is None or end_date is None:
        return fallback_start, fallback_end, "fallback"

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    return start_date, end_date, source


def _render_custom_window_inputs(
    absolute_start: date,
    absolute_end: date,
) -> tuple[date, date]:
    """Render custom date inputs and return selected start/end dates."""
    default_start = max(
        absolute_start,
        absolute_end - timedelta(days=DEFAULT_WINDOW_DAYS - 1),
    )
    custom_col1, custom_col2 = st.columns(2)
    start_date = custom_col1.date_input(
        "Start date",
        value=default_start,
        min_value=absolute_start,
        max_value=absolute_end,
        key="timeframe_start_date",
    )
    end_date = custom_col2.date_input(
        "End date",
        value=absolute_end,
        min_value=start_date,
        max_value=absolute_end,
        key="timeframe_end_date",
    )
    return start_date, end_date


def _window_from_preset(
    preset: str,
    absolute_start: date,
    absolute_end: date,
) -> tuple[date, date]:
    """Translate a selected preset into a concrete date window."""
    if preset == "All time":
        return absolute_start, absolute_end
    if preset == "YTD":
        ytd_start = date(absolute_end.year, 1, 1)
        return max(absolute_start, ytd_start), absolute_end
    if preset == "Custom":
        return _render_custom_window_inputs(absolute_start, absolute_end)

    preset_days = PRESET_WINDOW_DAYS.get(preset, DEFAULT_WINDOW_DAYS)
    start_date = max(absolute_start, absolute_end - timedelta(days=preset_days - 1))
    return start_date, absolute_end


def _enforce_min_window(
    start_date: date,
    end_date: date,
    absolute_start: date,
) -> tuple[date, date, int]:
    """Ensure selected window satisfies minimum-day constraints."""
    selected_days = (end_date - start_date).days + 1
    if selected_days >= MIN_WINDOW_DAYS:
        return start_date, end_date, selected_days

    adjusted_start = max(absolute_start, end_date - timedelta(days=MIN_WINDOW_DAYS - 1))
    adjusted_days = (end_date - adjusted_start).days + 1
    st.warning("Minimum timeframe is 7 days. Window has been adjusted automatically.")
    return adjusted_start, end_date, adjusted_days


def _select_time_window(
    absolute_start: date,
    absolute_end: date,
) -> tuple[date, date, str]:
    """Render page controls and return selected timeframe."""
    total_days = (absolute_end - absolute_start).days + 1
    if total_days <= 0:
        absolute_start, absolute_end = _fallback_date_bounds()
        total_days = (absolute_end - absolute_start).days + 1

    st.markdown("### Timeframe")
    if total_days < MIN_WINDOW_DAYS:
        st.info(
            "Available data covers less than 7 days; using full available window.",
        )
        label = (
            f"All available data ({absolute_start.isoformat()} to "
            f"{absolute_end.isoformat()}, {total_days} days)"
        )
        return absolute_start, absolute_end, label

    preset = st.selectbox(
        "Window",
        [
            "Last 7 days",
            "Last 30 days",
            "Last 90 days",
            "Last 6 months",
            "Last 1 year",
            "YTD",
            "All time",
            "Custom",
        ],
        index=2,
    )
    start_date, end_date = _window_from_preset(preset, absolute_start, absolute_end)
    start_date, end_date, selected_days = _enforce_min_window(
        start_date,
        end_date,
        absolute_start,
    )

    label = f"{start_date.isoformat()} to {end_date.isoformat()} ({selected_days} days)"
    st.caption(f"Selected: {label}")
    return start_date, end_date, label


def _attach_window_metadata(
    result,
    selected_start: date,
    selected_end: date,
    window_label: str,
    bounds_source: str,
):
    """Attach user-selected window metadata to source result payloads."""
    metrics, total_metrics, timeline_df, timeline_meta = result
    enriched_timeline_meta = dict(timeline_meta or {})
    enriched_timeline_meta.update(
        {
            "requested_period_start": selected_start.isoformat(),
            "requested_period_end": selected_end.isoformat(),
            "requested_days": (selected_end - selected_start).days + 1,
            "window_label": window_label,
            "bounds_source": bounds_source,
        },
    )
    return metrics, total_metrics, timeline_df, enriched_timeline_meta


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


def _request_period(request: dict[str, object]) -> tuple[date | None, date | None]:
    """Extract optional date-window bounds from a request payload."""
    return _parse_iso_date(request.get("period_start")), _parse_iso_date(
        request.get("period_end"),
    )


def _has_source_credentials(
    request: dict[str, object],
    url_key: str,
    token_key: str,
) -> bool:
    """Return whether required URL/key fields are present for a data source."""
    return bool(str(request.get(url_key, "")).strip()) and bool(
        str(request.get(token_key, "")).strip(),
    )


def _normalize_source_result(result, source_name: str | None = None):
    """Normalize source fetch output into cache-friendly payload shape."""
    if result is None:
        return None

    metrics, total_metrics, timeline_df, timeline_meta = result
    if source_name:
        timeline_meta["source"] = source_name

    normalized_metrics, normalized_totals = _normalize_metrics_for_cache(
        metrics,
        total_metrics,
    )
    return normalized_metrics, normalized_totals, timeline_df, timeline_meta


@st.cache_data(show_spinner=False, ttl=CACHE_TTL_SECONDS)
def _load_metrics_cached(
    request: dict[str, object],
):
    """Load metrics with cache key driven by source config and inputs."""
    period_start, period_end = _request_period(request)

    if bool(request.get("use_supabase", False)) and _has_source_credentials(
        request,
        "supabase_url",
        "supabase_key",
    ):
        normalized_result = _normalize_source_result(
            fetch_metrics_from_supabase_with_time(
                period_start=period_start,
                period_end=period_end,
            ),
        )
        if normalized_result is not None:
            return normalized_result

    if bool(request.get("use_api", False)) and _has_source_credentials(
        request,
        "api_base_url",
        "api_token",
    ):
        normalized_result = _normalize_source_result(
            fetch_metrics_from_api_with_time(
                period_start=period_start,
                period_end=period_end,
            ),
            source_name="api",
        )
        if normalized_result is not None:
            return normalized_result

    return None


def configure_page():
    """Configure Streamlit page and shared visual styles."""
    st.set_page_config(
        layout="wide",
        page_title="GitLab Contributions Dashboard",
        initial_sidebar_state="expanded",
    )
    inject_dashboard_styles()
    render_main_header()


def get_metrics():  # pylint: disable=too-many-locals
    """Fetch metrics from configured live sources with CSV fallback.

    Returns:
        Tuple of metrics, totals, timeline dataframe, and timeline metadata.
    """
    source_attempt_failed = not (config.USE_SUPABASE or config.USE_API)

    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    api_base_url = os.getenv("GITLAB_API_BASE_URL", "")
    api_token = os.getenv("GITLAB_API_TOKEN", "")

    bounds_payload = _load_date_bounds_cached(
        {
            "use_supabase": bool(config.USE_SUPABASE),
            "use_api": bool(config.USE_API),
            "supabase_url": supabase_url,
            "supabase_key": supabase_key,
        },
    )
    absolute_start, absolute_end, bounds_source = _resolve_effective_bounds(
        bounds_payload,
    )
    selected_start, selected_end, window_label = _select_time_window(
        absolute_start,
        absolute_end,
    )

    if config.USE_SUPABASE:
        supabase_start = perf_counter()
        with st.spinner("Loading metrics from Supabase..."):
            result = _load_metrics_cached(
                {
                    "use_supabase": True,
                    "use_api": False,
                    "supabase_url": supabase_url,
                    "supabase_key": supabase_key,
                    "api_base_url": "",
                    "api_token": "",
                    "period_start": selected_start.isoformat(),
                    "period_end": selected_end.isoformat(),
                    "supabase_lookback_days": config.SUPABASE_LOOKBACK_DAYS,
                },
            )
        supabase_elapsed = perf_counter() - supabase_start

        if result is not None:
            if config.SHOW_DATA_SOURCE_INFO:
                st.info(f"🗄️ Metrics loaded from Supabase in {supabase_elapsed:.2f}s")
            if st.button("Refresh Data Cache", key="refresh_cache_supabase"):
                st.cache_data.clear()
                st.rerun()
            return _attach_window_metadata(
                result,
                selected_start,
                selected_end,
                window_label,
                bounds_source,
            )

        source_attempt_failed = True
        st.warning("Supabase data unavailable. Falling back to API/CSV sources.")

    if config.USE_API:
        api_start = perf_counter()
        with st.spinner("Fetching metrics from GitLab API..."):
            result = _load_metrics_cached(
                {
                    "use_api": True,
                    "use_supabase": False,
                    "supabase_url": "",
                    "supabase_key": "",
                    "api_base_url": api_base_url,
                    "api_token": api_token,
                    "period_start": selected_start.isoformat(),
                    "period_end": selected_end.isoformat(),
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
            return _attach_window_metadata(
                result,
                selected_start,
                selected_end,
                window_label,
                bounds_source,
            )

        source_attempt_failed = True
        st.warning("API data unavailable. Falling back to CSV upload.")

    if source_attempt_failed:
        uploaded_metrics = st.file_uploader(
            "Upload metrics CSV (fallback option)",
            type=["csv"],
            help="Use a previously exported dashboard CSV when live sources are unavailable.",
        )

        if uploaded_metrics is not None:
            with st.spinner("Loading uploaded CSV metrics..."):
                uploaded_result = _load_uploaded_metrics_csv(
                    uploaded_metrics.getvalue(),
                )
            if uploaded_result is None:
                st.error(
                    "Uploaded CSV is empty or does not contain usable metric columns.",
                )
                st.stop()
            st.info("📄 Metrics loaded from uploaded CSV file")
            return uploaded_result

    return None


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
