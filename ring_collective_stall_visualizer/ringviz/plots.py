import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


STALL_BUCKET_ORDER = ["0", "1", "2", "3", "4", "5+"]

STALL_COLOR_MAP = {
    "0": "#9E9E9E",   # gray
    "1": "#0072B2",   # blue
    "2": "#E69F00",   # orange
    "3": "#009E73",   # green
    "4": "#CC79A7",   # purple
    "5+": "#D55E00",  # vermillion
}

def _row_value(row: pd.Series, key: str, default: object) -> object:
    return row.get(key, default)


def _prepare_gantt_frame(
    df: pd.DataFrame,
    *,
    chain_limit: int | None,
    normalize_time: bool,
) -> tuple[pd.DataFrame, list[str], float]:
    plot_df = df.copy()
    chains = list(plot_df["chain"].drop_duplicates())

    if chain_limit is not None:
        chains = chains[:chain_limit]
        plot_df = plot_df[plot_df["chain"].isin(chains)]

    origin = 0.0
    if normalize_time and not plot_df.empty:
        origin = float(plot_df["start_s"].min())
        plot_df["plot_start_s"] = plot_df["start_s"] - origin
        plot_df["plot_end_s"] = plot_df["end_s"] - origin
    else:
        plot_df["plot_start_s"] = plot_df["start_s"]
        plot_df["plot_end_s"] = plot_df["end_s"]

    return plot_df, chains, origin


def _build_gantt_hover(row: pd.Series, *, start_col: str, end_col: str, include_absolute_time: bool) -> str:
    def _time_text(label: str, rel_value: object, abs_value: object | None) -> str:
        rel_text = f"{float(rel_value):.6f} s" if rel_value is not None and rel_value != "" else ""
        if include_absolute_time and abs_value is not None and abs_value != rel_value:
            abs_text = f"{float(abs_value):.6f} s"
            return f"{label}: {rel_text} (abs {abs_text})"
        return f"{label}: {rel_text}"

    parts = [
        f"chain: {row.get('chain', '')}",
        f"hop: {row.get('hop_index', '')}",
        f"edge: {row.get('edge', '')}",
        _time_text("start", row.get(start_col), row.get('start_s')),
        _time_text("end", row.get(end_col), row.get('end_s')),
        f"duration: {float(row.get('duration_ms', 0.0)):.3f} ms",
        f"stalled packets: {row.get('stalled_packets', '')}",
        f"max egress: {row.get('max_egress', '')}",
        f"avg egress: {float(row.get('avg_egress', 0.0)):.3f}",
    ]
    return "<br>".join(parts)


def _make_gantt_figure(
    plot_df: pd.DataFrame,
    *,
    chains: list[str],
    color_by: str,
    title: str,
    base_col: str,
    hover_start_col: str,
    hover_end_col: str,
    include_absolute_time: bool,
) -> go.Figure:
    category_orders = {"chain": chains[::-1]}
    color_discrete_map = None

    if color_by == "stall_bucket":
        category_orders["stall_bucket"] = STALL_BUCKET_ORDER
        color_discrete_map = STALL_COLOR_MAP

    color_continuous_scale = None
    if color_by in {"stalled_packets", "duration_ms", "max_egress", "avg_egress"}:
        # Mirror the Streamlit interactive view: a sequential Blue scale where
        # 0 / low values are white/very-light-blue and high values are dark navy.
        color_continuous_scale = px.colors.sequential.Blues

    plot_df = plot_df.copy()
    plot_df["hover"] = plot_df.apply(
        lambda row: _build_gantt_hover(
            row,
            start_col=hover_start_col,
            end_col=hover_end_col,
            include_absolute_time=include_absolute_time,
        ),
        axis=1,
    )

    fig = px.bar(
        plot_df,
        x="duration_s",
        y="chain",
        base=base_col,
        color=color_by,
        orientation="h",
        hover_name="edge",
        custom_data=["hover"],
        category_orders=category_orders,
        color_discrete_map=color_discrete_map,
        color_continuous_scale=color_continuous_scale,
        labels={
            "duration_s": "Duration [s]",
            "chain": "Ring chain",
            "stall_bucket": "Stalled packets",
            "stalled_packets": "Stalled packets",
            "duration_ms": "Duration [ms]",
            "max_egress": "Max egress",
            "avg_egress": "Avg egress",
        },
        title=title,
    )

    fig.update_traces(
        hovertemplate="%{customdata[0]}<extra></extra>",
        marker_line_color="black",
        marker_line_width=0.8,
        opacity=0.9,
    )

    fig.update_layout(
        title_font_size=14,
        title_x=0.5,
        title_xanchor="center",
    )

    return fig


def _add_missing_stall_bucket_legend(
    fig: go.Figure,
    *,
    plot_frames: list[pd.DataFrame],
    chain_lists: list[list[str]],
    row: int,
    col: int,
) -> None:
    present_by_frame = [
        set(frame["stall_bucket"].dropna().astype(str).unique()) if not frame.empty else set()
        for frame in plot_frames
    ]
    all_present = set().union(*present_by_frame) if present_by_frame else set()
    first_present = present_by_frame[0] if present_by_frame else set()
    anchor_chain = next((chains[0] for chains in chain_lists if chains), "")

    for bucket in STALL_BUCKET_ORDER:
        if bucket not in all_present or bucket in first_present:
            continue
        fig.add_trace(
            go.Bar(
                x=[0],
                y=[anchor_chain],
                name=bucket,
                orientation="h",
                marker=dict(
                    color=STALL_COLOR_MAP[bucket],
                    line=dict(color="black", width=0.8),
                ),
                visible="legendonly",
                showlegend=True,
                hoverinfo="skip",
            ),
            row=row,
            col=col,
        )


def make_gantt(
    df: pd.DataFrame,
    *,
    color_by: str,
    chain_limit: int | None,
) -> go.Figure:
    if df.empty:
        return go.Figure()

    plot_df, chains, _origin = _prepare_gantt_frame(df, chain_limit=chain_limit, normalize_time=False)

    fig = _make_gantt_figure(
        plot_df,
        chains=chains,
        color_by=color_by,
        title="Ring collective Gantt view",
        base_col="plot_start_s",
        hover_start_col="start_s",
        hover_end_col="end_s",
        include_absolute_time=False,
    )

    if color_by == "stall_bucket":
        present_buckets = set(plot_df["stall_bucket"].dropna().astype(str).unique())

        for bucket in STALL_BUCKET_ORDER:
            if bucket in present_buckets:
                continue

            fig.add_trace(
                go.Bar(
                    x=[0],
                    y=[chains[0] if chains else ""],
                    name=bucket,
                    orientation="h",
                    marker=dict(
                        color=STALL_COLOR_MAP[bucket],
                        line=dict(color="black", width=0.8),
                    ),
                    visible="legendonly",
                    showlegend=True,
                    hoverinfo="skip",
                )
            )

    fig.update_layout(
        barmode="overlay",
        bargap=0.35,
        height=max(420, 30 * len(chains) + 120),
        legend_title="Stalled packets" if color_by == "stall_bucket" else color_by,
        legend_traceorder="normal",
        margin=dict(l=90, r=40, t=70, b=80),
        title_font_size=14,
    )
    fig.update_xaxes(title_text="Simulation time [s]", title_standoff=18, automargin=True)
    fig.update_yaxes(title_text="Chain start host", title_standoff=16, automargin=True)

    return fig


def make_gantt_comparison(
    data_frames: list[pd.DataFrame],
    *,
    labels: list[str] | None,
    color_by: str,
    chain_limit: int | None,
) -> go.Figure:
    """`labels` names the panels in order; None (or too few labels) names the rest "Scan N"."""
    non_empty_frames = [df for df in data_frames if not df.empty]
    if not non_empty_frames:
        return go.Figure()

    prepared = [
        _prepare_gantt_frame(df, chain_limit=chain_limit, normalize_time=True)
        for df in non_empty_frames
    ]
    plot_frames = [plot_df for plot_df, _chains, _origin in prepared]
    chain_lists = [chains for _plot_df, chains, _origin in prepared]
    subplot_labels = labels or [f"Scan {idx + 1}" for idx in range(len(plot_frames))]
    subplot_labels = [
        subplot_labels[idx] if idx < len(subplot_labels) else f"Scan {idx + 1}"
        for idx in range(len(plot_frames))
    ]

    subplot_figures = [
        _make_gantt_figure(
            plot_df,
            chains=chains,
            color_by=color_by,
            title=label,
            base_col="plot_start_s",
            hover_start_col="plot_start_s",
            hover_end_col="plot_end_s",
            include_absolute_time=True,
        )
        for (plot_df, chains, _origin), label in zip(prepared, subplot_labels)
    ]

    fig = make_subplots(
        rows=len(subplot_figures),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=tuple(subplot_labels),
    )

    for row_idx, subplot_fig in enumerate(subplot_figures, start=1):
        for trace in subplot_fig.data:
            trace.showlegend = row_idx == 1 and trace.showlegend
            fig.add_trace(trace, row=row_idx, col=1)

    # ── Transfer coloraxis for continuous color columns ───────────────────────
    # When color_by is a numeric column, px.bar stores the colorscale in the
    # subplot figure's layout as "coloraxis".  Traces reference it via
    # marker.coloraxis="coloraxis".  Because make_subplots creates a fresh
    # layout we must copy all coloraxis entries over, merging cmin/cmax ranges
    # across panels so the color scale is consistent.
    _all_cmin: list[float] = []
    _all_cmax: list[float] = []
    _coloraxis_patch: dict = {}
    for _subfig in subplot_figures:
        _sub_json = _subfig.layout.to_plotly_json()
        for _key, _val in _sub_json.items():
            if not _key.startswith("coloraxis"):
                continue
            if _key not in _coloraxis_patch:
                _coloraxis_patch[_key] = dict(_val) if isinstance(_val, dict) else _val
            if isinstance(_val, dict):
                if "cmin" in _val:
                    _all_cmin.append(float(_val["cmin"]))
                if "cmax" in _val:
                    _all_cmax.append(float(_val["cmax"]))
    if _coloraxis_patch:
        for _key in _coloraxis_patch:
            if isinstance(_coloraxis_patch[_key], dict):
                if _all_cmin:
                    _coloraxis_patch[_key]["cmin"] = min(_all_cmin)
                if _all_cmax:
                    _coloraxis_patch[_key]["cmax"] = max(_all_cmax)
        fig.update_layout(**_coloraxis_patch)

    if color_by == "stall_bucket":
        _add_missing_stall_bucket_legend(
            fig,
            plot_frames=plot_frames,
            chain_lists=chain_lists,
            row=1,
            col=1,
        )

    max_end = max(float(plot_df["plot_end_s"].max()) for plot_df in plot_frames if not plot_df.empty)
    max_chains = max((len(chains) for chains in chain_lists), default=1)
    panel_count = len(subplot_figures)

    fig.update_layout(
        barmode="overlay",
        bargap=0.35,
        height=max(380 + 40 * panel_count, 100 + panel_count * (58 + 24 * max_chains)),
        legend_title="Stalled packets" if color_by == "stall_bucket" else color_by,
        legend_traceorder="normal",
        margin=dict(l=90, r=50, t=80, b=95),
        title_font_size=14,
    )
    fig.update_annotations(font_size=13)
    for row_idx in range(1, panel_count + 1):
        fig.update_yaxes(
            title_text="Chain" if row_idx == 1 else "",
            title_standoff=16,
            automargin=True,
            row=row_idx,
            col=1,
        )
        fig.update_xaxes(
            title_text="Aligned simulation time [s]" if row_idx == panel_count else "",
            title_standoff=22,
            automargin=True,
            row=row_idx,
            col=1,
        )
    if max_end > 0.0:
        fig.update_xaxes(range=[0.0, max_end * 1.02])

    return fig


def make_heatmap(
    df: pd.DataFrame,
    *,
    metric: str,
    chain_limit: int | None,
) -> go.Figure:
    if df.empty:
        return go.Figure()

    plot_df = df.copy()

    chains = list(plot_df["chain"].drop_duplicates())

    if chain_limit is not None:
        chains = chains[:chain_limit]
        plot_df = plot_df[plot_df["chain"].isin(chains)]

    pivot = plot_df.pivot_table(
        index="chain",
        columns="hop_index",
        values=metric,
        aggfunc="mean",
    )

    pivot = pivot.reindex(chains)

    hover_text = []

    for chain in pivot.index:
        row_text = []

        for hop in pivot.columns:
            match = plot_df[
                (plot_df["chain"] == chain)
                & (plot_df["hop_index"] == hop)
            ]

            if match.empty:
                row_text.append("")
                continue

            r = match.iloc[0]

            row_text.append(
                f"chain: {_row_value(r, 'chain', '')}"
                f"<br>hop: {_row_value(r, 'hop_index', '')}"
                f"<br>edge: {_row_value(r, 'edge', '')}"
                f"<br>{metric}: {float(_row_value(r, metric, 0.0)):.6g}"
                f"<br>duration: {float(_row_value(r, 'duration_ms', 0.0)):.3f} ms"
                f"<br>stalled packets: {_row_value(r, 'stalled_packets', 0)}"
                f"<br>max egress: {_row_value(r, 'max_egress', 0)}"
            )

        hover_text.append(row_text)

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            text=hover_text,
            hovertemplate="%{text}<extra></extra>",
            colorbar=dict(title=metric),
        )
    )

    fig.update_layout(
        title=f"Ring hop heatmap: {metric}",
        height=max(520, 38 * len(pivot.index) + 80),
        margin=dict(l=90, r=60, t=80, b=85),
        title_font_size=14,
    )
    fig.update_xaxes(title_text="Hop index in chain", title_standoff=18, automargin=True)
    fig.update_yaxes(title_text="Chain start host", title_standoff=16, automargin=True)

    return fig