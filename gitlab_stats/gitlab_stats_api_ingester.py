"""GitLab API data ingester for fetching metrics from live GitLab instances.

This module provides an alternative to the file-based parser, pulling metrics
directly from GitLab API. Returns the same metric dict structure as the parser
for compatibility with the dashboard.

Credentials are loaded from environment variables (typically via .env file).
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import UTC
from datetime import date
from datetime import datetime
from datetime import timedelta
from typing import Any
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.request import Request
from urllib.request import urlopen

from gitlab_stats import config
from gitlab_stats.dashboard_utils.activity_rules import HISTORY_PUSH_THRESHOLD
from gitlab_stats.dashboard_utils.activity_rules import INTEGRATION_BRANCH_RE
from gitlab_stats.dashboard_utils.activity_rules import MERGE_COMMIT_TITLE_RE
from gitlab_stats.dashboard_utils.metrics_schema import BASE_METRIC_KEYS
from gitlab_stats.dashboard_utils.metrics_schema import TOTAL_COUNT_METRIC_KEYS
from gitlab_stats.dashboard_utils.timeline_utils import build_timeline

logger = logging.getLogger(__name__)


def _api_window() -> tuple[date, date]:
    lookback_days = max(1, _to_int(config.API_LOOKBACK_DAYS))
    period_end = datetime.now(tz=UTC).date()
    period_start = period_end - timedelta(days=lookback_days - 1)
    return period_start, period_end


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _request_json(url: str, token: str) -> list[dict[str, Any]] | dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        msg = f"Unsupported URL scheme for GitLab API request: {parsed.scheme}"
        raise ValueError(msg)

    request = Request(url)  # noqa: S310
    request.add_header("PRIVATE-TOKEN", token)
    request.add_header("Accept", "application/json")

    with urlopen(request, timeout=30) as response:  # noqa: S310
        payload = response.read().decode("utf-8")
        return json.loads(payload)


def _request_json_with_headers(
    url: str,
    token: str,
) -> tuple[list[dict[str, Any]] | dict[str, Any], dict[str, str]]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        msg = f"Unsupported URL scheme for GitLab API request: {parsed.scheme}"
        raise ValueError(msg)

    request = Request(url)  # noqa: S310
    request.add_header("PRIVATE-TOKEN", token)
    request.add_header("Accept", "application/json")

    with urlopen(request, timeout=30) as response:  # noqa: S310
        payload = response.read().decode("utf-8")
        headers = {str(k): str(v) for k, v in response.headers.items()}
        return json.loads(payload), headers


def _fetch_authenticated_user(base_url: str, token: str) -> dict[str, Any]:
    payload = _request_json(f"{base_url.rstrip('/')}/user", token)
    if not isinstance(payload, dict):
        msg = "Expected JSON object from /user endpoint"
        raise TypeError(msg)
    return payload


def _fetch_events(
    base_url: str,
    token: str,
    user_id: int,
    after_date: str,
    before_date: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    per_page = max(1, min(config.API_EVENTS_PER_PAGE, 100))
    max_pages = max(1, config.API_MAX_EVENT_PAGES)

    page = 1
    hit_pagination_limit = False
    while page <= max_pages:
        url = (
            f"{base_url.rstrip('/')}/users/{user_id}/events?"
            f"{urlencode({
                'after': after_date,
                'before': before_date,
                'page': page,
                'per_page': per_page,
            })}"
        )
        payload, headers = _request_json_with_headers(url, token)

        if not isinstance(payload, list):
            msg = "Expected JSON list from /users/:id/events endpoint"
            raise TypeError(msg)

        if not payload:
            break

        events.extend(payload)

        next_page_raw = (headers.get("X-Next-Page") or "").strip()
        if next_page_raw:
            if page == max_pages:
                hit_pagination_limit = True
            page = _to_int(next_page_raw)
            if page <= 0:
                break
            continue

        if len(payload) < per_page:
            break

        if page == max_pages:
            hit_pagination_limit = True
        page += 1

    if hit_pagination_limit:
        logger.warning(
            "Reached API_MAX_EVENT_PAGES=%s while fetching events; older data may "
            "be truncated. Increase API_MAX_EVENT_PAGES to cover the full window.",
            max_pages,
        )

    return events


def _fetch_project_name(
    base_url: str,
    token: str,
    project_id: int,
    project_name_cache: dict[int, str | None],
) -> str | None:
    if project_id in project_name_cache:
        return project_name_cache[project_id]

    payload = _request_json(f"{base_url.rstrip('/')}/projects/{project_id}", token)
    project_name: str | None = None
    if isinstance(payload, dict):
        raw_name = payload.get("name") or payload.get("path_with_namespace")
        if raw_name:
            project_name = str(raw_name).rsplit("/", maxsplit=1)[-1]

    project_name_cache[project_id] = project_name
    return project_name


def _derive_project_totals(project_data: dict[str, Any]) -> None:
    for key in BASE_METRIC_KEYS:
        project_data.setdefault(key, 0)

    code_total = (
        _to_int(project_data.get("commits", 0))
        + _to_int(project_data.get("branch_created", 0))
        + _to_int(project_data.get("branch_deleted", 0))
    )
    collab_total = (
        _to_int(project_data.get("mr_opened", 0))
        + _to_int(project_data.get("mr_merged", 0))
        + _to_int(project_data.get("mr_approved", 0))
        + _to_int(project_data.get("mr_commented", 0))
        + _to_int(project_data.get("issue_opened", 0))
    )
    total = code_total + collab_total

    project_data["code_contributions"] = code_total
    project_data["collab_contributions"] = collab_total
    project_data["total_contributions"] = total
    project_data["code_pct"] = round((100.0 * code_total / total), 1) if total else 0.0
    project_data["collab_pct"] = (
        round((100.0 * collab_total / total), 1) if total else 0.0
    )


def _event_project_name(
    event: dict[str, Any],
    base_url: str,
    token: str,
    project_name_cache: dict[int, str | None],
) -> str | None:
    project = event.get("project") or {}
    project_id = event.get("project_id") or project.get("id")
    if project_id is not None:
        resolved_project_id = _to_int(project_id)
        if resolved_project_id > 0:
            project_name = _fetch_project_name(
                base_url,
                token,
                resolved_project_id,
                project_name_cache,
            )
            if project_name:
                return project_name

    project = event.get("project") or {}
    if isinstance(project, dict):
        path = project.get("name") or project.get("path_with_namespace")
        if path:
            return str(path).rsplit("/", maxsplit=1)[-1]

    return None


def _event_date_from_api_event(event: dict[str, Any]):
    created_at = event.get("created_at")
    if not created_at:
        return None

    created_at_dt = datetime.fromisoformat(str(created_at))
    return created_at_dt.date()


def _event_counts_from_event(event: dict[str, Any]) -> dict[str, int]:
    """Map one API event to base metric counts."""
    action = str(event.get("action_name", "")).strip().lower()
    target = str(event.get("target_type", "")).strip().lower()
    push_data = event.get("push_data") or {}
    ref_type = str(push_data.get("ref_type", "")).lower()
    push_action = str(push_data.get("action", "")).lower()
    branch_ref = str(push_data.get("ref", "")).strip()
    counts = dict.fromkeys(BASE_METRIC_KEYS, 0)
    is_branch_creation_push = action.startswith("pushed new") or (
        action.startswith("pushed")
        and ref_type == "branch"
        and push_action == "created"
    )

    if action.startswith("pushed") and not is_branch_creation_push:
        commit_count = _to_int(push_data.get("commit_count", 0))
        commit_title = str(push_data.get("commit_title", "")).strip()

        if commit_count > 0 and MERGE_COMMIT_TITLE_RE.search(commit_title):
            commit_count = 1

        # Large push counts on integration branches are commonly branch-history
        # sync events and should be treated as one contribution.
        if commit_count >= HISTORY_PUSH_THRESHOLD and INTEGRATION_BRANCH_RE.search(
            branch_ref,
        ):
            commit_count = 1

        counts["commits"] += commit_count

    if is_branch_creation_push:
        counts["branch_created"] += 1

    if action == "deleted" and (ref_type == "branch" or push_action == "deleted"):
        counts["branch_deleted"] += 1

    if action == "opened" and target == "mergerequest":
        counts["mr_opened"] += 1

    if action == "accepted" and target == "mergerequest":
        counts["mr_merged"] += 1

    if action == "approved" and target == "mergerequest":
        counts["mr_approved"] += 1

    if action == "commented on" and target in {"diffnote", "discussionnote", "note"}:
        counts["mr_commented"] += 1

    if action == "opened" and target in {"issue", "workitem"}:
        counts["issue_opened"] += 1

    return counts


def _map_event_to_project_metrics(
    project_data: dict[str, Any],
    event: dict[str, Any],
) -> bool:
    """Backward-compatible helper for tests and quick diagnostics."""
    event_counts = _event_counts_from_event(event)
    for metric_key, count in event_counts.items():
        project_data[metric_key] += count
    return any(count > 0 for count in event_counts.values())


def _aggregate_totals(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total_metrics: dict[str, Any] = defaultdict(int)

    for project_data in metrics.values():
        _derive_project_totals(project_data)
        for key in TOTAL_COUNT_METRIC_KEYS:
            total_metrics[key] += _to_int(project_data.get(key, 0))

    total = _to_int(total_metrics.get("total_contributions", 0))
    if total > 0:
        total_metrics["code_pct"] = round(
            100.0 * _to_int(total_metrics.get("code_contributions", 0)) / total,
            1,
        )
        total_metrics["collab_pct"] = round(
            100.0 * _to_int(total_metrics.get("collab_contributions", 0)) / total,
            1,
        )
    else:
        total_metrics["code_pct"] = 0.0
        total_metrics["collab_pct"] = 0.0

    return dict(total_metrics)


def _resolve_user_id(
    user_id: int | None,
    api_base_url: str,
    api_token: str,
) -> int | None:
    if user_id is not None:
        return user_id if user_id > 0 else None

    user = _fetch_authenticated_user(api_base_url, api_token)
    resolved_user_id = _to_int(user.get("id"))
    return resolved_user_id if resolved_user_id > 0 else None


def _build_non_zero_metrics(
    events: list[dict[str, Any]],
    api_base_url: str,
    api_token: str,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], bool]:
    metrics: dict[str, dict[str, Any]] = defaultdict(lambda: defaultdict(int))
    project_name_cache: dict[int, str | None] = {}
    event_records: list[dict[str, Any]] = []
    has_real_dates = False

    for event in events:
        project_name = _event_project_name(
            event,
            api_base_url,
            api_token,
            project_name_cache,
        )
        if not project_name:
            continue

        project_data = metrics[project_name]
        event_counts = _event_counts_from_event(event)
        for metric_key, count in event_counts.items():
            project_data[metric_key] += count

        event_date = _event_date_from_api_event(event)
        has_real_dates = has_real_dates or event_date is not None
        for metric_key, count in event_counts.items():
            if count > 0:
                event_records.append(
                    {
                        "event_date": event_date,
                        "project": project_name,
                        "event_type": metric_key,
                        "count": count,
                    },
                )

    non_zero_metrics: dict[str, dict[str, Any]] = {}
    for project_name, project_data in metrics.items():
        _derive_project_totals(project_data)
        if _to_int(project_data.get("total_contributions", 0)) > 0:
            non_zero_metrics[project_name] = project_data

    return non_zero_metrics, event_records, has_real_dates


def fetch_metrics_from_api_with_time(
    user_id: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Any, dict[str, bool | int | str]] | None:
    """Fetch API metrics plus timeline dataframe and timeline metadata."""
    result: (
        tuple[dict[str, Any], dict[str, Any], Any, dict[str, bool | int | str]] | None
    ) = None

    try:
        api_token = os.getenv("GITLAB_API_TOKEN")
        api_base_url = os.getenv("GITLAB_API_BASE_URL")
        if not api_token or not api_base_url:
            logger.warning(
                "API credentials not configured. Set GITLAB_API_TOKEN and "
                "GITLAB_API_BASE_URL in .env file to enable API ingestion.",
            )
            return None

        resolved_user_id = _resolve_user_id(user_id, api_base_url, api_token)
        if resolved_user_id is None:
            logger.error("Unable to resolve authenticated GitLab user id")
            return None

        period_start, period_end = _api_window()

        events = _fetch_events(
            base_url=api_base_url,
            token=api_token,
            user_id=resolved_user_id,
            after_date=period_start.isoformat(),
            before_date=period_end.isoformat(),
        )
        if not events:
            logger.warning("No events returned from GitLab API; using parser fallback")
            return None

        non_zero_metrics, event_records, has_real_dates = _build_non_zero_metrics(
            events,
            api_base_url,
            api_token,
        )
        if not non_zero_metrics:
            logger.warning("No project-scoped metrics could be derived from API events")
            return None

        total_metrics = _aggregate_totals(non_zero_metrics)
        normalized_metrics = {
            project: dict(data) for project, data in non_zero_metrics.items()
        }
        timeline_df, timeline_meta = build_timeline(
            event_records,
            has_real_dates,
            period_start=period_start,
            period_end=period_end,
        )

        logger.info(
            "Loaded API metrics for %s project(s) across %s event(s)",
            len(normalized_metrics),
            len(events),
        )
        result = (normalized_metrics, total_metrics, timeline_df, timeline_meta)

    except (HTTPError, URLError):
        logger.exception("GitLab API connectivity failure")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, TimeoutError):
        logger.exception("Failed to parse GitLab API response")

    return result


def fetch_metrics_from_api(
    user_id: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """
    Fetch GitLab metrics from API for a user.

    Credentials are loaded from environment variables:
        - GITLAB_API_TOKEN: GitLab personal access token
        - GITLAB_API_BASE_URL: Base URL of GitLab instance

    Args:
        user_id: Optional user ID; if None, uses authenticated user

    Returns:
        Tuple of (metrics, total_metrics) dicts matching parser output format, or None on failure.

    Metric dict format:
    {
        "project_name": {
            "commits": int,
            "branch_created": int,
            "branch_deleted": int,
            "mr_opened": int,
            "mr_merged": int,
            "mr_approved": int,
            "mr_commented": int,
            "issue_opened": int,
            "code_contributions": int,
            "collab_contributions": int,
            "total_contributions": int,
            "code_pct": float,
            "collab_pct": float,
        },
        ...
    }

    total_metrics: Same structure but aggregated across all projects.
    """
    result_with_time = fetch_metrics_from_api_with_time(user_id=user_id)
    if result_with_time is None:
        return None

    metrics, total_metrics, _, _ = result_with_time
    return metrics, total_metrics
