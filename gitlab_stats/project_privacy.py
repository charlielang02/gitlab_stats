"""Keep source project labels out of persisted and displayed metrics."""

from __future__ import annotations

import re

from gitlab_stats.dashboard_utils.metrics_schema import BASE_METRIC_KEYS
from gitlab_stats.dashboard_utils.metrics_schema import JIRA_METRIC_KEYS


def project_alias(source: str, project_id: object) -> str:
    """Return a canonical, source-scoped alias for a positive numeric ID."""
    raw_id = str(project_id)
    if source not in {"gitlab", "jira"} or not re.fullmatch(r"[0-9]+", raw_id):
        raise ValueError("Project alias requires a supported source and numeric ID")
    numeric_id = int(raw_id)
    if numeric_id <= 0:
        raise ValueError("Project alias requires a positive ID")
    return f"{source}-project-{numeric_id}"


def is_project_alias(value: object, source: str) -> bool:
    """Check the exact canonical alias format without accepting source labels."""
    return bool(re.fullmatch(rf"{re.escape(source)}-project-[1-9][0-9]*", str(value)))


def validate_event_identity(project: object, event_type: object, source: str) -> None:
    """Reject private labels and unexpected categories without echoing their values."""
    categories = BASE_METRIC_KEYS if source == "gitlab" else JIRA_METRIC_KEYS
    if not is_project_alias(project, source) or event_type not in categories:
        raise ValueError(
            "Unsafe project alias or event category; migrate legacy records first",
        )
