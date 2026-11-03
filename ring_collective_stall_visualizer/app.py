import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go

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


def _numeric_series(df: pd.DataFrame, col: str, default: float) -> pd.Series:
    if col not in df.columns:
        return pd.Series([default] * len(df), index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def _png_export_button(fig, *, label: str, filename_prefix: str, key: str) -> None:
    export_fig, export_width, export_height = _build_export_figure(fig)
    try:
        png_bytes = export_fig.to_image(format="png", width=export_width, height=export_height, scale=2)
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


def _pdf_export_button(fig, *, label: str, filename_prefix: str, key: str) -> None:
    """Render a download button for the given Plotly figure as a PDF file.

    Requires kaleido (same dependency as PNG export).
    """
    export_fig, export_width, export_height = _build_export_figure(fig)
    try:
        pdf_bytes = export_fig.to_image(format="pdf", width=export_width, height=export_height)
    except Exception:
        st.caption("PDF export unavailable. Install/upgrade kaleido to enable image export.")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label=label,
        data=pdf_bytes,
        file_name=f"{filename_prefix}_{ts}.pdf",
        mime="application/pdf",
        key=key,
    )


def _build_export_figure(fig) -> tuple[go.Figure, int, int]:
    """Create a presentation-quality copy of *fig* sized for static PDF/PNG export.

    The figure height is derived from the actual number of subplot panels and
    unique chain rows so the export is never clipped regardless of how large
    the comparison Gantt is.
    """
    export_fig = go.Figure(fig)

    # ── Count subplot panels ─────────────────────────────────────────────────
    # make_subplots() places subplot-title annotations with showarrow=False.
    annotations = list(export_fig.layout.annotations)
    subtitle_annotations = [
        a for a in annotations
        if not a.showarrow and str(a.text).strip()
    ]
    n_panels = max(1, len(subtitle_annotations))

    # Without subplot titles, count the numbered xaxis entries in the layout instead.
    if n_panels == 1:
        layout_json = export_fig.layout.to_plotly_json()
        n_xaxes = sum(1 for k in layout_json if k.startswith("xaxis"))
        n_panels = max(n_panels, n_xaxes)

    # ── Count unique chain rows (y-axis values) across all traces ───────────
    # In a comparison Gantt every panel shows the same chain names, so the
    # set of unique y-values equals chains-per-panel.
    y_values: set[str] = set()
    for trace in export_fig.data:
        y_arr = trace.y
        if y_arr is not None:
            y_values.update(str(v) for v in y_arr if v is not None)
    chains_per_panel = max(1, len(y_values))

    # ── Compute required export dimensions ───────────────────────────────────
    # 44 px per chain row · generous panel header (110 px) · top+bottom margin
    _PX_PER_CHAIN   = 44
    _PX_PER_HEADER  = 110   # per-panel title + spacing
    _PX_MARGINS     = 260   # top + bottom total
    export_height = max(
        900,
        _PX_MARGINS + n_panels * (chains_per_panel * _PX_PER_CHAIN + _PX_PER_HEADER),
    )
    is_comparison = n_panels > 1
    export_width = 2200 if is_comparison else 1600

    # ── Apply presentation-quality layout overrides ──────────────────────────
    # Preserve any coloraxis already in the figure layout before update_layout
    # merges the new settings (go.Figure copies layout so it should be there,
    # but we re-assert it explicitly for safety).
    _existing_layout = export_fig.layout.to_plotly_json()
    _coloraxis_preserve = {k: v for k, v in _existing_layout.items() if k.startswith("coloraxis")}

    export_fig.update_layout(
        width=export_width,
        height=export_height,
        font=dict(size=16),
        title=dict(font=dict(size=20), x=0.5, xanchor="center"),
        margin=dict(l=145, r=135, t=115, b=135),
        bargap=0.28,
    )
    # Re-apply coloraxis in case update_layout removed it
    if _coloraxis_preserve:
        export_fig.update_layout(**_coloraxis_preserve)
    export_fig.update_xaxes(
        automargin=True,
        title_standoff=26,
        tickfont=dict(size=14),
        title_font=dict(size=16),
    )
    export_fig.update_yaxes(
        automargin=True,
        title_standoff=22,
        tickfont=dict(size=13),
        title_font=dict(size=16),
    )
    export_fig.update_annotations(font=dict(size=16))
    return export_fig, export_width, export_height


if uploaded is None:
    st.info("Upload a ring log file to start.")
    st.stop()


# The parser already adds `stalled_packets` and `stall_bucket` to every non-empty frame.
df = parse_uploaded_file(uploaded.getvalue())
df_compare = parse_uploaded_file(uploaded_compare.getvalue()) if uploaded_compare is not None else None
df_compare_3 = parse_uploaded_file(uploaded_compare_3.getvalue()) if uploaded_compare_3 is not None else None
df_compare_4 = parse_uploaded_file(uploaded_compare_4.getvalue()) if uploaded_compare_4 is not None else None

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
        config={
            "toImageButtonOptions": {
                "format": "png",
                "filename": "ring_gantt",
                "scale": 3,   # 3× = high-res PNG from the toolbar camera button
            },
            "displaylogo": False,
        },
    )
    _png_export_button(
        gantt_fig,
        label="Download Gantt as PNG",
        filename_prefix="ring_gantt",
        key="download_gantt_png",
    )
    _pdf_export_button(
        gantt_fig,
        label="Download Gantt as PDF",
        filename_prefix="ring_gantt",
        key="download_gantt_pdf",
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
        config={
            "toImageButtonOptions": {
                "format": "png",
                "filename": "ring_heatmap",
                "scale": 3,
            },
            "displaylogo": False,
        },
    )
    _png_export_button(
        heatmap_fig,
        label="Download Heatmap as PNG",
        filename_prefix="ring_heatmap",
        key="download_heatmap_png",
    )
    _pdf_export_button(
        heatmap_fig,
        label="Download Heatmap as PDF",
        filename_prefix="ring_heatmap",
        key="download_heatmap_pdf",
    )
