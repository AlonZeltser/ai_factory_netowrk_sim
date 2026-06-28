import streamlit as st
import pandas as pd

from ringviz.parser import parse_log_text
from ringviz.plots import make_gantt, make_heatmap


st.set_page_config(
    page_title="Ring Collective Stall Visualizer",
    layout="wide",
)


st.title("Ring Collective Stall Visualizer")

st.markdown(
    """
This dashboard visualizes one collective-ring log as:

1. **Gantt view** — how each chain progresses over simulation time.
2. **Heatmap view** — hop-by-hop duration, stalls, or egress pressure.
"""
)


uploaded = st.sidebar.file_uploader(
    "Upload ring log",
    type=["txt", "log"],
)


@st.cache_data
def parse_uploaded_file(file_bytes: bytes) -> pd.DataFrame:
    text = file_bytes.decode("utf-8", errors="replace")
    return parse_log_text(text)


if uploaded is None:
    st.info("Upload a ring log file to start.")
    st.stop()


df = parse_uploaded_file(uploaded.getvalue())

if df.empty:
    st.error("No flow records were parsed. Check the log format.")
    st.stop()


filtered = df.copy()


st.sidebar.header("Filters")

for col in ["job", "step", "phase", "bucket", "op"]:
    if col not in filtered.columns:
        continue

    values = sorted(filtered[col].dropna().unique().tolist())

    if len(values) == 0:
        continue

    if len(values) == 1:
        st.sidebar.caption(f"{col}: {values[0]}")
        continue

    selected = st.sidebar.multiselect(
        label=col,
        options=values,
        default=values,
    )

    filtered = filtered[filtered[col].isin(selected)]


if filtered.empty:
    st.warning("No rows left after filtering.")
    st.stop()


chains = list(filtered["chain"].drop_duplicates())

chain_limit = st.sidebar.slider(
    "Max chains to display",
    min_value=1,
    max_value=max(1, len(chains)),
    value=min(len(chains), 16),
)


st.sidebar.header("Visualization")

view = st.sidebar.radio(
    "View",
    ["Gantt", "Heatmap", "Both"],
)


st.subheader("Run summary")

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.metric("Flows", f"{len(filtered):,}")

with c2:
    st.metric("Chains", f"{filtered['chain'].nunique():,}")

with c3:
    st.metric("Total stalled packets", f"{int(filtered['stalled_packets'].sum()):,}")

with c4:
    stalled_flows = int((filtered["stalled_packets"] > 0).sum())
    st.metric("Flows with stalls", f"{stalled_flows:,}")

with c5:
    step_end = filtered["end_s"].max()
    st.metric("Last completion", f"{step_end:.6f} s")


with st.expander("Parsed data preview"):
    preview_cols = [
        "job",
        "step",
        "phase",
        "bucket",
        "op",
        "chain",
        "hop_index",
        "sender",
        "receiver",
        "start_s",
        "end_s",
        "duration_ms",
        "stalled_packets",
        "stall_bucket",
        "max_egress",
        "avg_egress",
        "n_egress_sum",
    ]

    preview_cols = [c for c in preview_cols if c in filtered.columns]

    st.dataframe(
        filtered[preview_cols],
        use_container_width=True,
    )


if view in ["Gantt", "Both"]:
    st.subheader("Gantt timeline")

    color_by = st.selectbox(
        "Color Gantt by",
        options=[
            "stall_bucket",
            "stalled_packets",
            "duration_ms",
            "max_egress",
            "avg_egress",
        ],
        index=0,
    )

    gantt_fig = make_gantt(
        filtered,
        color_by=color_by,
        chain_limit=chain_limit,
    )

    st.plotly_chart(
        gantt_fig,
        use_container_width=True,
    )


if view in ["Heatmap", "Both"]:
    st.subheader("Hop heatmap")

    heatmap_metric = st.selectbox(
        "Heatmap metric",
        options=[
            "duration_ms",
            "stalled_packets",
            "max_egress",
            "avg_egress",
            "n_egress_sum",
        ],
        index=0,
    )

    heatmap_fig = make_heatmap(
        filtered,
        metric=heatmap_metric,
        chain_limit=chain_limit,
    )

    st.plotly_chart(
        heatmap_fig,
        use_container_width=True,
    )