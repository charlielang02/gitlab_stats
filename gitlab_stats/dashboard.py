"""Generate a Streamlit dashboard to visualize GitLab contributions metrics."""

import pandas as pd
import streamlit as st

from gitlab_stats.gitlab_stats import _parse_gitlab_log

st.set_page_config(layout="wide")

st.title("GitLab Contributions Dashboard")

file_path = st.text_input(
    "Path to contributions file",
    value="gitlab_stats/gitlab_contributions_march_25th.txt",
)

if not file_path:
    st.stop()

metrics, total_metrics = _parse_gitlab_log(file_path)

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
