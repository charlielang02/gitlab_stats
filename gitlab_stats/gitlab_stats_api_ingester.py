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
from gitlab_stats.metrics_schema import BASE_METRIC_KEYS
from gitlab_stats.metrics_schema import TOTAL_COUNT_METRIC_KEYS

logger = logging.getLogger(__name__)


def _iso_date(days_ago: int) -> str:
    return (datetime.now(tz=UTC) - timedelta(days=days_ago)).date().isoformat()


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

    for page in range(1, max_pages + 1):
        query = urlencode(
            {
                "after": after_date,
                "before": before_date,
                "page": page,
                "per_page": per_page,
            },
        )
        url = f"{base_url.rstrip('/')}/users/{user_id}/events?{query}"
        payload = _request_json(url, token)

        if not isinstance(payload, list):
            msg = "Expected JSON list from /users/:id/events endpoint"
            raise TypeError(msg)

        if not payload:
            break

        events.extend(payload)
        if len(payload) < per_page:
            break

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


def _map_event_to_project_metrics(
    project_data: dict[str, Any],
    event: dict[str, Any],
) -> bool:
    action = str(event.get("action_name", "")).strip().lower()
    target = str(event.get("target_type", "")).strip().lower()
    push_data = event.get("push_data") or {}
    ref_type = str(push_data.get("ref_type", "")).lower()
    push_action = str(push_data.get("action", "")).lower()
    updated = False

    if action.startswith("pushed"):
        commit_count = _to_int(push_data.get("commit_count", 0))
        project_data["commits"] += commit_count
        updated = updated or commit_count > 0

    if action.startswith("pushed new") or (
        action.startswith("pushed")
        and ref_type == "branch"
        and push_action == "created"
    ):
        project_data["branch_created"] += 1
        updated = True

    if action == "deleted" and (ref_type == "branch" or push_action == "deleted"):
        project_data["branch_deleted"] += 1
        updated = True

    if action == "opened" and target == "mergerequest":
        project_data["mr_opened"] += 1
        updated = True

    if action == "accepted" and target == "mergerequest":
        project_data["mr_merged"] += 1
        updated = True

    if action == "approved" and target == "mergerequest":
        project_data["mr_approved"] += 1
        updated = True

    if action == "commented on" and target in {"diffnote", "discussionnote", "note"}:
        project_data["mr_commented"] += 1
        updated = True

    if action == "opened" and target in {"issue", "workitem"}:
        project_data["issue_opened"] += 1
        updated = True

    return updated


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
) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = defaultdict(lambda: defaultdict(int))
    project_name_cache: dict[int, str | None] = {}

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
        _map_event_to_project_metrics(project_data, event)

    non_zero_metrics: dict[str, dict[str, Any]] = {}
    for project_name, project_data in metrics.items():
        _derive_project_totals(project_data)
        if _to_int(project_data.get("total_contributions", 0)) > 0:
            non_zero_metrics[project_name] = project_data

    return non_zero_metrics


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
    result: tuple[dict[str, Any], dict[str, Any]] | None = None

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

        events = _fetch_events(
            base_url=api_base_url,
            token=api_token,
            user_id=resolved_user_id,
            after_date=_iso_date(config.API_LOOKBACK_DAYS),
            before_date=_iso_date(0),
        )
        if not events:
            logger.warning("No events returned from GitLab API; using parser fallback")
            return None

        non_zero_metrics = _build_non_zero_metrics(events, api_base_url, api_token)
        if not non_zero_metrics:
            logger.warning("No project-scoped metrics could be derived from API events")
            return None

        total_metrics = _aggregate_totals(non_zero_metrics)
        normalized_metrics = {
            project: dict(data) for project, data in non_zero_metrics.items()
        }

        logger.info(
            "Loaded API metrics for %s project(s) across %s event(s)",
            len(normalized_metrics),
            len(events),
        )
        result = (normalized_metrics, total_metrics)

    except (HTTPError, URLError):
        logger.exception("GitLab API connectivity failure")

    except (ValueError, TypeError, KeyError, json.JSONDecodeError, TimeoutError):
        logger.exception("Failed to parse GitLab API response")

    return result
