"""Jira API ingester for normalized per-project contribution events."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC
from datetime import date
from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING
from typing import Any
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import quote
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.request import Request
from urllib.request import urlopen

from gitlab_stats import config
from gitlab_stats.dashboard_utils.metrics_schema import JIRA_METRIC_KEYS
from gitlab_stats.dashboard_utils.timeline_utils import build_event_type_timeline
from gitlab_stats.database.supabase_client import SupabaseConfigError
from gitlab_stats.database.supabase_client import SupabaseRequestError
from gitlab_stats.database.supabase_client import fetch_jira_events_from_supabase
from gitlab_stats.settings import read_setting

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _jira_api_path(endpoint: str) -> str:
    """Build a Jira REST API v2 path."""
    return f"rest/api/2/{endpoint.lstrip('/')}"


def _jira_window(
    period_start: date | None = None,
    period_end: date | None = None,
) -> tuple[date, date]:
    if period_start is not None and period_end is not None:
        if period_start > period_end:
            period_start, period_end = period_end, period_start
        return period_start, period_end

    lookback_days = max(1, _to_int(getattr(config, "API_LOOKBACK_DAYS", 365)))
    window_end = datetime.now(tz=UTC).date()
    window_start = window_end - timedelta(days=lookback_days - 1)
    return window_start, window_end


def _request_json(
    base_url: str,
    path: str,
    api_token: str,
    query_params: dict[str, Any] | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        msg = f"Unsupported URL scheme for Jira API request: {parsed.scheme}"
        raise ValueError(msg)

    query = ""
    if query_params:
        query = f"?{urlencode(query_params)}"

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}{query}"

    request = Request(url)  # noqa: S310
    request.add_header("Authorization", f"Bearer {api_token}")
    request.add_header("Accept", "application/json")

    with urlopen(request, timeout=30) as response:  # noqa: S310
        payload = response.read().decode("utf-8")
        return json.loads(payload)


def _read_jira_credentials() -> tuple[str, str, str] | None:
    base_url = read_setting("JIRA_BASE_URL")
    email = read_setting("JIRA_USER_EMAIL")
    token = read_setting("JIRA_API_TOKEN")

    if not base_url or not email or not token:
        logger.info(
            "Jira credentials are incomplete. Set JIRA_BASE_URL, "
            "JIRA_USER_EMAIL, and JIRA_API_TOKEN to enable Jira sync.",
        )
        return None

    return base_url, email, token


def _parse_iso_datetime(raw_value: Any) -> datetime | None:
    if not raw_value:
        return None

    normalized = str(raw_value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)

    return parsed.astimezone(UTC)


def _build_jql(window_start: date, window_end: date, project_keys: str) -> str:
    clauses = [
        "assignee = currentUser()",
        f'updated >= "{window_start.isoformat()}"',
        f'updated <= "{window_end.isoformat()}"',
    ]
    parsed_keys = [key.strip() for key in project_keys.split(",") if key.strip()]
    if parsed_keys:
        escaped = ", ".join(f'"{quote(key, safe="_-.")}"' for key in parsed_keys)
        clauses.append(f"project in ({escaped})")

    return " AND ".join(clauses)


def _fetch_authenticated_user(
    base_url: str,
    api_token: str,
) -> str | None:
    payload = _request_json(
        base_url,
        _jira_api_path("myself"),
        api_token,
    )
    if not isinstance(payload, dict):
        return None

    user_id = str(payload.get("key", "")).strip()
    return user_id or None


def _fetch_issues(
    base_url: str,
    api_token: str,
    jql: str,
    story_points_field: str,
) -> list[dict[str, Any]]:
    start_at = 0
    max_results = 100
    issues: list[dict[str, Any]] = []

    fields = [
        "project",
        "assignee",
        "status",
        "resolutiondate",
        "created",
        "comment",
        story_points_field,
    ]

    while True:
        payload = _request_json(
            base_url,
            _jira_api_path("search"),
            api_token,
            query_params={
                "jql": jql,
                "startAt": start_at,
                "maxResults": max_results,
                "fields": ",".join(fields),
            },
        )
        if not isinstance(payload, dict):
            msg = "Expected object payload from Jira search endpoint"
            raise TypeError(msg)

        page_issues = payload.get("issues", [])
        if not isinstance(page_issues, list):
            msg = "Expected issue list in Jira search response"
            raise TypeError(msg)

        issues.extend(page_issues)

        total = _to_int(payload.get("total", 0))
        start_at += len(page_issues)
        if not page_issues or start_at >= total:
            break

    return issues


def _in_window(raw_timestamp: Any, window_start: date, window_end: date) -> date | None:
    parsed = _parse_iso_datetime(raw_timestamp)
    if parsed is None:
        return None

    parsed_date = parsed.date()
    if window_start <= parsed_date <= window_end:
        return parsed_date

    return None


def _append_count(
    counters: dict[tuple[date, str, str], int],
    event_date: date | None,
    project: str,
    event_type: str,
    count: int,
) -> None:
    if event_date is None or not project or count <= 0:
        return

    key = (event_date, project, event_type)
    counters[key] += count


def _build_jira_metrics_from_rows(  # pylint: disable=too-many-locals
    rows: list[dict[str, Any]],
    period_start: date | None = None,
    period_end: date | None = None,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, Any],
    pd.DataFrame,
    dict[str, bool | int | str],
]:
    metrics: dict[str, dict[str, Any]] = defaultdict(lambda: defaultdict(int))
    event_records: list[dict[str, Any]] = []

    for row in rows:
        project_name = str(row.get("project", "")).strip()
        event_type = str(row.get("event_type", "")).strip()
        count = _to_int(row.get("count", 0))
        if not project_name or event_type not in JIRA_METRIC_KEYS or count <= 0:
            continue

        project_data = metrics[project_name]
        project_data[event_type] += count

        raw_date = row.get("event_date")
        event_date = None
        if raw_date:
            try:
                event_date = date.fromisoformat(str(raw_date))
            except ValueError:
                event_date = None

        event_records.append(
            {
                "event_date": event_date,
                "project": project_name,
                "event_type": event_type,
                "count": count,
            },
        )

    non_zero_metrics: dict[str, dict[str, Any]] = {}
    total_metrics: dict[str, Any] = defaultdict(int)
    for project_name, project_data in metrics.items():
        project_total = sum(
            _to_int(project_data.get(key, 0)) for key in JIRA_METRIC_KEYS
        )
        project_data["total_jira_activity"] = project_total
        if project_total > 0:
            non_zero_metrics[project_name] = project_data
            for key in JIRA_METRIC_KEYS:
                total_metrics[key] += _to_int(project_data.get(key, 0))

    total_metrics["total_jira_activity"] = sum(
        _to_int(total_metrics.get(key, 0)) for key in JIRA_METRIC_KEYS
    )
    total_metrics["projects_touched"] = len(non_zero_metrics)

    timeline_df, timeline_meta = build_event_type_timeline(
        event_records,
        list(JIRA_METRIC_KEYS),
        period_start=period_start,
        period_end=period_end,
    )
    if not timeline_df.empty:
        timeline_df["total_jira_activity"] = timeline_df[list(JIRA_METRIC_KEYS)].sum(
            axis=1,
        )

    return (
        {project: dict(data) for project, data in non_zero_metrics.items()},
        dict(total_metrics),
        timeline_df,
        timeline_meta,
    )


def _extract_project_key(fields: dict[str, Any]) -> str:
    """Extract project key from Jira issue fields."""
    project_obj = fields.get("project", {})
    if not isinstance(project_obj, dict):
        return ""
    return str(
        project_obj.get("key") or project_obj.get("name") or "",
    ).strip()


def _process_issue_dates(  # pylint: disable=too-many-arguments, too-many-positional-arguments
    counters: dict[tuple[date, str, str], int],
    fields: dict[str, Any],
    project_key: str,
    window_start: date,
    window_end: date,
    story_points_field: str,
) -> None:
    """Process created and resolved dates for an issue."""
    created_date = _in_window(fields.get("created"), window_start, window_end)
    _append_count(
        counters,
        created_date,
        project_key,
        "jira_issues_assigned",
        1,
    )

    resolution_date = _in_window(
        fields.get("resolutiondate"),
        window_start,
        window_end,
    )
    if resolution_date is not None:
        _append_count(
            counters,
            resolution_date,
            project_key,
            "jira_issues_closed",
            1,
        )

        story_points = _to_float(fields.get(story_points_field, 0))
        _append_count(
            counters,
            resolution_date,
            project_key,
            "jira_story_points_closed",
            round(story_points),
        )


def _process_issue_comments(  # pylint: disable=too-many-arguments, too-many-positional-arguments
    counters: dict[tuple[date, str, str], int],
    fields: dict[str, Any],
    project_key: str,
    account_id: str,
    window_start: date,
    window_end: date,
) -> None:
    """Process comments for an issue if authored by current user."""
    comment_block = fields.get("comment", {})
    comments = []
    if isinstance(comment_block, dict):
        comments = comment_block.get("comments", [])

    if not isinstance(comments, list):
        return

    for comment in comments:
        if not isinstance(comment, dict):
            continue
        author = comment.get("author", {})
        author_id = ""
        if isinstance(author, dict):
            author_id = str(author.get("key", "")).strip()
        if author_id != account_id:
            continue

        comment_date = _in_window(
            comment.get("created"),
            window_start,
            window_end,
        )
        _append_count(
            counters,
            comment_date,
            project_key,
            "jira_comments",
            1,
        )


def fetch_event_records_from_jira(  # pylint: disable=too-many-locals
    period_start: date | None = None,
    period_end: date | None = None,
) -> list[dict[str, Any]] | None:
    """Fetch normalized Jira event records for Supabase sync."""
    credentials = _read_jira_credentials()
    if credentials is None:
        return []

    base_url, _, api_token = credentials
    window_start, window_end = _jira_window(period_start, period_end)
    project_keys = read_setting("JIRA_PROJECT_KEYS")
    story_points_field = read_setting("JIRA_STORY_POINTS_FIELD") or "customfield_10412"

    try:
        account_id = _fetch_authenticated_user(base_url, api_token)
        if not account_id:
            logger.error("Unable to resolve authenticated Jira account id")
            return None

        issues = _fetch_issues(
            base_url,
            api_token,
            _build_jql(window_start, window_end, project_keys),
            story_points_field,
        )

        counters: dict[tuple[date, str, str], int] = defaultdict(int)
        for issue in issues:
            fields = issue.get("fields", {})
            if not isinstance(fields, dict):
                continue

            project_key = _extract_project_key(fields)
            if not project_key:
                continue

            _process_issue_dates(
                counters,
                fields,
                project_key,
                window_start,
                window_end,
                story_points_field,
            )

            _process_issue_comments(
                counters,
                fields,
                project_key,
                account_id,
                window_start,
                window_end,
            )
        records = [
            {
                "event_date": event_date.isoformat(),
                "project": project,
                "event_type": event_type,
                "count": count,
            }
            for (event_date, project, event_type), count in counters.items()
            if count > 0
        ]

        logger.info("Loaded %s normalized Jira event records", len(records))

    except (HTTPError, URLError):
        logger.exception("Jira API connectivity failure")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, TimeoutError):
        logger.exception("Failed to parse Jira API response")
    else:
        return records

    return None


def fetch_jira_metrics_from_supabase_with_time(
    period_start: date | None = None,
    period_end: date | None = None,
) -> (
    tuple[dict[str, Any], dict[str, Any], pd.DataFrame, dict[str, bool | int | str]]
    | None
):
    """Fetch Jira metrics from Supabase event rows and rebuild a Jira timeline."""
    try:
        lookback_days = max(1, _to_int(getattr(config, "SUPABASE_LOOKBACK_DAYS", 365)))
        query_end = datetime.now(tz=UTC).date() if period_end is None else period_end
        query_start = (
            query_end - timedelta(days=lookback_days - 1)
            if period_start is None
            else period_start
        )
        if query_start > query_end:
            query_start, query_end = query_end, query_start

        rows = fetch_jira_events_from_supabase(
            lookback_days=lookback_days,
            period_start=query_start,
            period_end=query_end,
        )
        if not rows:
            logger.warning("No Supabase Jira event rows found for configured window")
            return None

        metrics, total_metrics, timeline_df, timeline_meta = (
            _build_jira_metrics_from_rows(
                rows,
                period_start=query_start,
                period_end=query_end,
            )
        )
        if not metrics:
            return None

        timeline_meta["source"] = "supabase"
        logger.info(
            "Loaded Jira metrics for %s project(s) across %s event row(s)",
            len(metrics),
            len(rows),
        )

    except (SupabaseConfigError, SupabaseRequestError, ValueError, TypeError, KeyError):
        logger.exception("Failed to parse Supabase Jira event response")
        return None

    return metrics, total_metrics, timeline_df, timeline_meta
