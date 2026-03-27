"""Shared metric key definitions for parser and API ingestion."""

BASE_METRIC_KEYS = (
    "commits",
    "branch_created",
    "branch_deleted",
    "mr_opened",
    "mr_merged",
    "mr_approved",
    "mr_commented",
    "issue_opened",
)

TOTAL_COUNT_METRIC_KEYS = (
    *BASE_METRIC_KEYS,
    "code_contributions",
    "collab_contributions",
    "total_contributions",
)

PERCENTAGE_METRIC_KEYS = (
    "code_pct",
    "collab_pct",
)
