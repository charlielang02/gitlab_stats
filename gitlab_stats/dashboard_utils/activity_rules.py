"""Shared activity parsing/counting rules used by parser and API ingestion."""

import re

MERGE_COMMIT_TITLE_RE = re.compile(
    r"^merge (branch|remote-tracking branch)\b",
    re.IGNORECASE,
)
INTEGRATION_BRANCH_RE = re.compile(
    r"(^|[-_/])(main|master|develop|dev)$",
    re.IGNORECASE,
)

# Treat very large pushes to integration branches as history updates.
HISTORY_PUSH_THRESHOLD = 25
