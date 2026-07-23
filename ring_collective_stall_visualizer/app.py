import streamlit as st
import pandas as pd
from datetime import datetime

from ringviz.parser import parse_log_text
from ringviz.plots import make_gantt, make_gantt_comparison, make_heatmap


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
    key="primary_log",
)

uploaded_compare = st.sidebar.file_uploader(
    "Upload second ring log for comparison",
    type=["txt", "log"],
    key="comparison_log",
)

uploaded_compare_3 = st.sidebar.file_uploader(
    "Upload third ring log for comparison",
    type=["txt", "log"],
    key="comparison_log_3",
)

uploaded_compare_4 = st.sidebar.file_uploader(
    "Upload fourth ring log for comparison",
    type=["txt", "log"],
    key="comparison_log_4",
)


@st.cache_data
def parse_uploaded_file(file_bytes: bytes) -> pd.DataFrame:
    text = file_bytes.decode("utf-8", errors="replace")
    return parse_log_text(text)


def _numeric_series(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series([default] * len(df), index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def _normalize_visualizer_df(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None:
        return None
    normalized = df.copy()
    if "stalled_packets" not in normalized.columns:
        if "stall_packets_declared" in normalized.columns:
            normalized["stalled_packets"] = pd.to_numeric(normalized["stall_packets_declared"], errors="coerce").fillna(0)
        else:
            normalized["stalled_packets"] = pd.Series([pd.NA] * len(normalized), index=normalized.index, dtype="Int64")
    if "stall_bucket" not in normalized.columns:
        stalled = pd.to_numeric(normalized["stalled_packets"], errors="coerce")
        normalized["stall_bucket"] = stalled.apply(
            lambda x: "unknown" if pd.isna(x) else ("0" if int(x) <= 0 else ("1" if int(x) == 1 else ("2" if int(x) == 2 else ("3" if int(x) == 3 else ("4" if int(x) == 4 else "5+")))))
        )
    return normalized


def _png_export_button(fig, *, label: str, filename_prefix: str, key: str) -> None:
    try:
        png_bytes = fig.to_image(format="png", scale=2)
    except Exception:
        st.caption("PNG export unavailable. Install/upgrade kaleido to enable image export.")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label=label,
        data=png_bytes,
        file_name=f"{filename_prefix}_{ts}.png",
        mime="image/png",
        key=key,
    )


if uploaded is None:
    st.info("Upload a ring log file to start.")
    st.stop()


df = _normalize_visualizer_df(parse_uploaded_file(uploaded.getvalue()))
df_compare = _normalize_visualizer_df(parse_uploaded_file(uploaded_compare.getvalue())) if uploaded_compare is not None else None
df_compare_3 = _normalize_visualizer_df(parse_uploaded_file(uploaded_compare_3.getvalue())) if uploaded_compare_3 is not None else None
df_compare_4 = _normalize_visualizer_df(parse_uploaded_file(uploaded_compare_4.getvalue())) if uploaded_compare_4 is not None else None

if df.empty:
    st.error("No flow records were parsed. Check the log format.")
    st.stop()


filtered = df.copy()
filtered_compare = df_compare.copy() if df_compare is not None else None
filtered_compare_3 = df_compare_3.copy() if df_compare_3 is not None else None
filtered_compare_4 = df_compare_4.copy() if df_compare_4 is not None else None


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
    if filtered_compare is not None and col in filtered_compare.columns:
        filtered_compare = filtered_compare[filtered_compare[col].isin(selected)]
    if filtered_compare_3 is not None and col in filtered_compare_3.columns:
        filtered_compare_3 = filtered_compare_3[filtered_compare_3[col].isin(selected)]
    if filtered_compare_4 is not None and col in filtered_compare_4.columns:
        filtered_compare_4 = filtered_compare_4[filtered_compare_4[col].isin(selected)]


if filtered.empty:
    st.warning("No rows left after filtering.")
    st.stop()

if filtered_compare is not None and filtered_compare.empty:
    st.warning("No rows left in the comparison log after filtering.")
    filtered_compare = None

if filtered_compare_3 is not None and filtered_compare_3.empty:
    st.warning("No rows left in the third comparison log after filtering.")
    filtered_compare_3 = None

if filtered_compare_4 is not None and filtered_compare_4.empty:
    st.warning("No rows left in the fourth comparison log after filtering.")
    filtered_compare_4 = None


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

comparison_frames = [
    frame
    for frame in [filtered_compare, filtered_compare_3, filtered_compare_4]
    if frame is not None
]

compare_mode = len(comparison_frames) > 0 and view in ["Gantt", "Both"]


st.subheader("Run summary")

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.metric("Flows", f"{len(filtered):,}")

with c2:
    st.metric("Chains", f"{filtered['chain'].nunique():,}")

with c3:
    stalled_series_raw = pd.to_numeric(filtered["stalled_packets"], errors="coerce") if "stalled_packets" in filtered.columns else pd.Series([pd.NA] * len(filtered), index=filtered.index)
    if stalled_series_raw.notna().any():
        st.metric("Total stalled packets", f"{int(stalled_series_raw.fillna(0).sum()):,}")
    else:
        st.metric("Total stalled packets", "unknown")

with c4:
    if stalled_series_raw.notna().any():
        stalled_flows = int((stalled_series_raw.fillna(0) > 0).sum())
        st.metric("Flows with stalls", f"{stalled_flows:,}")
    else:
        st.metric("Flows with stalls", "unknown")

with c5:
    step_end = float(_numeric_series(filtered, "end_s", default=0.0).max())
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

    gantt_options = [
        c
        for c in ["stall_bucket", "stalled_packets", "duration_ms", "max_egress", "avg_egress"]
        if c in filtered.columns
    ]
    if not gantt_options:
        st.warning("No compatible Gantt color columns were parsed.")
        st.stop()

    color_by = st.selectbox(
        "Color Gantt by",
        options=gantt_options,
        index=0,
    )

    if compare_mode:
        compare_label_1 = st.sidebar.text_input("Comparison label 1", value="Scan 1")
        compare_label_2 = st.sidebar.text_input("Comparison label 2", value="Scan 2")
        compare_label_3 = st.sidebar.text_input("Comparison label 3", value="Scan 3")
        compare_label_4 = st.sidebar.text_input("Comparison label 4", value="Scan 4")
        gantt_fig = make_gantt_comparison(
            [filtered, *comparison_frames],
            labels=[compare_label_1, compare_label_2, compare_label_3, compare_label_4],
            color_by=color_by,
            chain_limit=chain_limit,
        )
    else:
        gantt_fig = make_gantt(
            filtered,
            color_by=color_by,
            chain_limit=chain_limit,
        )

    st.plotly_chart(
        gantt_fig,
        use_container_width=True,
    )
    _png_export_button(
        gantt_fig,
        label="Download Gantt as PNG",
        filename_prefix="ring_gantt",
        key="download_gantt_png",
    )


if view in ["Heatmap", "Both"]:
    st.subheader("Hop heatmap")

    heatmap_options = [
        c
        for c in ["duration_ms", "stalled_packets", "max_egress", "avg_egress", "n_egress_sum"]
        if c in filtered.columns
    ]
    if not heatmap_options:
        st.warning("No compatible heatmap metric columns were parsed.")
        st.stop()

    heatmap_metric = st.selectbox(
        "Heatmap metric",
        options=heatmap_options,
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
    _png_export_button(
        heatmap_fig,
        label="Download Heatmap as PNG",
        filename_prefix="ring_heatmap",
        key="download_heatmap_png",
    )
