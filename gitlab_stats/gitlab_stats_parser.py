"""Parses a txt file containing gitlab contributions
prints a summary of contributions per project and total contributions."""

import re
from collections import defaultdict

from gitlab_stats.activity_rules import HISTORY_PUSH_THRESHOLD
from gitlab_stats.activity_rules import INTEGRATION_BRANCH_RE
from gitlab_stats.activity_rules import MERGE_COMMIT_TITLE_RE
from gitlab_stats.metrics_schema import BASE_METRIC_KEYS
from gitlab_stats.metrics_schema import PERCENTAGE_METRIC_KEYS
from gitlab_stats.metrics_schema import TOTAL_COUNT_METRIC_KEYS

# --- Regex patterns ---
PROJECT_RE = re.compile(r"at (.+)")
BRANCH_RE = re.compile(r"pushed to branch\s+([^\s]+)")
MORE_COMMITS_RE = re.compile(r"\.\.\. and (\d+) more commits?")

ACTION_PATTERNS = {
    "commit_event": re.compile(r"pushed to branch"),
    "branch_created": re.compile(r"pushed new branch"),
    "branch_deleted": re.compile(r"deleted branch"),
    "mr_opened": re.compile(r"opened merge request"),
    "mr_merged": re.compile(r"accepted merge request"),
    "mr_approved": re.compile(r"approved merge request"),
    "mr_commented": re.compile(r"commented on merge request"),
    "issue_opened": re.compile(r"opened issue"),
}


def _extract_project(line):
    match = PROJECT_RE.search(line)
    if not match:
        return None

    full_path = match.group(1).strip()
    return full_path.split("/")[-1].strip()


def _classify_action(line):
    for action, pattern in ACTION_PATTERNS.items():
        if pattern.search(line):
            return action
    return None


def _extract_branch(line):
    match = BRANCH_RE.search(line)
    return match.group(1).strip() if match else None


def _is_merge_push(lines, start_index):
    """Return True when the push's primary commit title is a merge commit."""
    for i in range(start_index + 1, min(start_index + 6, len(lines))):
        candidate = lines[i].strip()
        if "\u00b7" in candidate:
            commit_title = candidate.split("\u00b7", maxsplit=1)[1].strip()
            return bool(MERGE_COMMIT_TITLE_RE.search(commit_title))
    return False


def count_commits(lines, start_index, branch_name=None):
    """
    Count commits for a push event.
    Looks ahead a few lines for '... and X more commits'
    """
    base_commits = 1

    # Merge commits should count as a single commit even when UI text says
    # "... and X more commits" for included branch history.
    if _is_merge_push(lines, start_index):
        return base_commits

    extra_commits = 0

    for i in range(start_index, min(start_index + 5, len(lines))):
        match = MORE_COMMITS_RE.search(lines[i])
        if match:
            extra_commits = int(match.group(1))
            break

    total_commits = base_commits + extra_commits

    # Large push counts on integration branches are commonly branch-history
    # sync events and should be treated as one contribution.
    if (
        total_commits >= HISTORY_PUSH_THRESHOLD
        and branch_name
        and INTEGRATION_BRANCH_RE.search(branch_name)
    ):
        return 1

    return total_commits


# --- Contribution calculations ---


def _compute_code_contributions(data):
    return (
        data.get("commits", 0)
        + data.get("branch_created", 0)
        + data.get("branch_deleted", 0)
    )


def _compute_collab_contributions(data):
    return (
        data.get("mr_opened", 0)
        + data.get("mr_merged", 0)
        + data.get("mr_approved", 0)
        + data.get("mr_commented", 0)
        + data.get("issue_opened", 0)
    )


def _parse_gitlab_log(file_path):
    metrics = defaultdict(lambda: defaultdict(int))

    with open(file_path, encoding="utf-8") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i]

        action = _classify_action(line)
        if not action:
            i += 1
            continue

        project = _extract_project(line)
        if not project:
            i += 1
            continue

        if action == "commit_event":
            commit_count = count_commits(lines, i, _extract_branch(line))
            metrics[project]["commits"] += commit_count
        else:
            metrics[project][action] += 1

        i += 1

    # --- Compute totals ---
    total_metrics = defaultdict(int)

    for data in metrics.values():
        code_total = _compute_code_contributions(data)
        collab_total = _compute_collab_contributions(data)
        total = code_total + collab_total

        data["code_contributions"] = code_total
        data["collab_contributions"] = collab_total
        data["total_contributions"] = total

        # --- Percentages ---
        if total > 0:
            data["code_pct"] = round(100 * code_total / total, 1)
            data["collab_pct"] = round(100 * collab_total / total, 1)
        else:
            data["code_pct"] = 0.0
            data["collab_pct"] = 0.0

        # Sum only count-based values across projects.
        for key in TOTAL_COUNT_METRIC_KEYS:
            total_metrics[key] += data.get(key, 0)

    # Recompute percentages for the aggregated totals only.
    if total_metrics["total_contributions"] > 0:
        total_metrics["code_pct"] = round(
            100
            * total_metrics["code_contributions"]
            / total_metrics["total_contributions"],
            1,
        )
        total_metrics["collab_pct"] = round(
            100
            * total_metrics["collab_contributions"]
            / total_metrics["total_contributions"],
            1,
        )
    else:
        total_metrics["code_pct"] = 0.0
        total_metrics["collab_pct"] = 0.0

    return metrics, total_metrics


def _print_summary(metrics, total_metrics):
    base_order = list(BASE_METRIC_KEYS)

    total_order = [
        "code_contributions",
        "collab_contributions",
        "total_contributions",
    ]

    pct_order = list(PERCENTAGE_METRIC_KEYS)

    def print_ordered(data):
        # Base stats
        for key in base_order:
            if key in data:
                print(f"{key:25}: {data[key]}")

        # Totals
        print("--- Totals ---")
        for key in total_order:
            if key in data:
                print(f"{key:25}: {data[key]}")

        # Percentages
        print("--- Percentages ---")
        for key in pct_order:
            if key in data:
                print(f"{key:25}: {data[key]}")

    print("\n===== PER PROJECT =====")
    for project, data in metrics.items():
        print(f"\n=== {project} ===")
        print_ordered(data)

    print("\n===== TOTAL =====")
    print_ordered(total_metrics)


def main():
    """Run the script to parse the gitlab log and print summary."""
    file_path = "../gitlab_contributions.txt"
    metrics, total_metrics = _parse_gitlab_log(file_path)
    _print_summary(metrics, total_metrics)


if __name__ == "__main__":
    main()
