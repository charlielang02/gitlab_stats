"""Parses a txt file containing gitlab contributions
prints a summary of contributions per project and total contributions."""

import re
from collections import defaultdict

# --- Regex patterns ---
PROJECT_RE = re.compile(r"at (.+)")
MORE_COMMITS_RE = re.compile(r"\.\.\. and (\d+) more commits")

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


def count_commits(lines, start_index):
    """
    Count commits for a push event.
    Looks ahead a few lines for '... and X more commits'
    """
    base_commits = 1
    extra_commits = 0

    for i in range(start_index, min(start_index + 5, len(lines))):
        match = MORE_COMMITS_RE.search(lines[i])
        if match:
            extra_commits = int(match.group(1))
            break

    return base_commits + extra_commits


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
            commit_count = count_commits(lines, i)
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
        for key in (
            "commits",
            "branch_created",
            "branch_deleted",
            "mr_opened",
            "mr_merged",
            "mr_approved",
            "mr_commented",
            "issue_opened",
            "code_contributions",
            "collab_contributions",
            "total_contributions",
        ):
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
    base_order = [
        "commits",
        "branch_created",
        "branch_deleted",
        "mr_opened",
        "mr_merged",
        "mr_approved",
        "mr_commented",
        "issue_opened",
    ]

    total_order = [
        "code_contributions",
        "collab_contributions",
        "total_contributions",
    ]

    pct_order = [
        "code_pct",
        "collab_pct",
    ]

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
    file_path = "gitlab_contributions_march_25th.txt"
    metrics, total_metrics = _parse_gitlab_log(file_path)
    _print_summary(metrics, total_metrics)


if __name__ == "__main__":
    main()
