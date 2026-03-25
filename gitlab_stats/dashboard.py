"""Generate a Streamlit dashboard to visualize GitLab contributions metrics."""

from pathlib import Path

import pandas as pd
import streamlit as st

from gitlab_stats.gitlab_stats_parser import _parse_gitlab_log

st.set_page_config(layout="wide")

st.title("GitLab Contributions Dashboard")

DEFAULT_FILE_PATH = "gitlab_contributions_march_25th.txt"
PLACEHOLDER_FILE_PATH = "doc/gitlab_contributions_placeholder.txt"

file_path = st.text_input(
    "Path to contributions file",
    value=DEFAULT_FILE_PATH,
)

if not file_path:
    st.stop()

selected_path = Path(file_path)
placeholder_path = Path(PLACEHOLDER_FILE_PATH)
using_placeholder = False  # pylint: disable=invalid-name

if not selected_path.exists():
    if placeholder_path.exists():
        using_placeholder = True  # pylint: disable=invalid-name
        selected_path = placeholder_path
    else:
        st.error(
            "No contributions file was found, and the placeholder file is missing.",
        )
        st.stop()

if using_placeholder:
    st.warning(
        "Placeholder data is currently shown. Numbers and projects are fake demo data.",
    )

metrics, total_metrics = _parse_gitlab_log(str(selected_path))

metric_df = pd.DataFrame.from_dict(metrics, orient="index").fillna(0)

metric_df = metric_df.sort_values(by="total_contributions", ascending=False)

st.header("Overall Summary")

col1, col2, col3 = st.columns(3)

col1.metric("Total Contributions", int(total_metrics["total_contributions"]))
col2.metric("Code Contributions", int(total_metrics["code_contributions"]))
col3.metric("Collaboration Contributions", int(total_metrics["collab_contributions"]))

st.header("Per Project Breakdown")
st.dataframe(metric_df)

st.header("Top Projects by Contributions")

top_n = st.slider("Number of projects", 5, 20, 10)

st.bar_chart(metric_df["total_contributions"].head(top_n))

st.header("Code vs Collaboration Split")

split_df = metric_df[["code_contributions", "collab_contributions"]]
st.bar_chart(split_df.head(top_n))

st.header("Project Deep Dive")

selected_project = st.selectbox("Select Project", metric_df.index)

if selected_project:
    project_data = metric_df.loc[selected_project]

    st.subheader(selected_project)

    st.write(project_data)

    st.bar_chart(
        project_data[
            [
                "commits",
                "mr_commented",
                "mr_opened",
                "mr_merged",
                "branch_created",
                "branch_deleted",
            ]
        ],
    )
