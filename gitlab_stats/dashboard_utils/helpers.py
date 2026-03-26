"""Reusable helper functions and constants for the Streamlit dashboard."""

from pathlib import Path

import pandas as pd
import streamlit as st

PRIMARY = "#0B3954"
SECONDARY = "#A11692"
ACCENT = "#58BC82"
HIGHLIGHT = "#FCFC62"
PALETTE = [PRIMARY, SECONDARY, ACCENT, HIGHLIGHT]
CONTINUOUS_SCALE = [
    [0.0, HIGHLIGHT],
    [0.4, ACCENT],
    [0.75, PRIMARY],
    [1.0, SECONDARY],
]
HEATMAP_SCALE = [
    [0.0, HIGHLIGHT],
    [0.35, ACCENT],
    [0.7, PRIMARY],
    [0.9, SECONDARY],
    [1.0, "#4a0b44"],
]

ORDERED_CATEGORIES = [
    "commits",
    "mr_opened",
    "mr_merged",
    "mr_approved",
    "mr_commented",
    "branch_created",
    "branch_deleted",
    "issue_opened",
    "code_contributions",
    "collab_contributions",
    "total_contributions",
    "code_pct",
    "collab_pct",
]


def inject_dashboard_styles():
    """Inject custom CSS styles used across dashboard sections."""
    st.markdown(
        """
        <style>
            .main-header {
                font-size: 3.5rem;
                font-weight: bold;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 1rem;
            }
            .insight-box {
                background-color: #e7f3ff;
                color: #0f172a;
                padding: 1rem;
                border-radius: 0.5rem;
                border-left: 4px solid #4facfe;
            }
            .insight-box strong {
                color: #0f172a;
            }
            .project-metrics-table {
                width: 100%;
                border-collapse: collapse;
            }
            .project-metrics-table th {
                background-color: #f0f2f6;
                color: #262730;
                text-align: left;
                padding: 0.55rem;
                border: 1px solid #e6e9ef;
            }
            .project-metrics-table td {
                padding: 0.55rem;
                border: 1px solid #e6e9ef;
            }
            @media (prefers-color-scheme: dark) {
                .insight-box {
                    background-color: #1f2937;
                    color: #e5e7eb;
                    border-left: 4px solid #4facfe;
                }
                .insight-box strong {
                    color: #f3f4f6;
                }
                .project-metrics-table th {
                    background-color: #262730;
                    color: #fafafa;
                    border: 1px solid #3a3f4b;
                }
                .project-metrics-table td {
                    border: 1px solid #3a3f4b;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_main_header():
    """Render branded dashboard title."""
    st.markdown(
        '<div class="main-header">📊 GitLab Contributions Dashboard</div>',
        unsafe_allow_html=True,
    )


def resolve_selected_path(file_path, placeholder_file_path):
    """Resolve active source file with fallback placeholder support."""
    selected_path = Path(file_path)
    placeholder_path = Path(placeholder_file_path)

    if selected_path.exists():
        return selected_path, False

    if placeholder_path.exists():
        return placeholder_path, True

    return None, False


def prepare_metric_df(metrics):
    """Build ordered metrics dataframe from parsed metrics dictionary."""
    metric_df = pd.DataFrame.from_dict(metrics, orient="index").fillna(0)
    ordered_columns = [
        column for column in ORDERED_CATEGORIES if column in metric_df.columns
    ]
    remaining_columns = [
        column for column in metric_df.columns if column not in ordered_columns
    ]
    metric_df = metric_df[ordered_columns + remaining_columns]
    metric_df = metric_df.sort_values(by="total_contributions", ascending=False)
    return metric_df, ordered_columns


def compute_profile_summary(metric_df, total_metrics):
    """Compute profile-level narrative summary fields."""
    dominant_style = (
        "Code-Heavy"
        if total_metrics["code_contributions"] > total_metrics["collab_contributions"]
        else "Collaboration-Heavy"
    )
    signal = (
        "High Commit Velocity"
        if metric_df["commits"].mean() > metric_df["collab_contributions"].mean()
        else "High Collaboration Activity"
    )
    return dominant_style, metric_df.index[0], signal


def format_project_metrics_table(project_data, ordered_columns):
    """Create styled HTML table for project metric details."""
    project_metrics_df = (
        project_data[ordered_columns].rename_axis("Metric").reset_index(name="Value")
    )
    pct_metrics = {"code_pct", "collab_pct"}
    project_metrics_df["Value"] = [
        f"{value:.1f}" if metric in pct_metrics else f"{int(value)}"
        for metric, value in zip(
            project_metrics_df["Metric"],
            project_metrics_df["Value"],
            strict=False,
        )
    ]
    return project_metrics_df.to_html(
        index=False,
        classes="project-metrics-table",
        border=0,
    )
