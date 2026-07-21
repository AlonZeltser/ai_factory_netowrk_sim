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


def _row_value(row: pd.Series, key: str, default: object = "") -> object:
    return row.get(key, default)


def _prepare_gantt_frame(
    df: pd.DataFrame,
    *,
    chain_limit: int | None = None,
    normalize_time: bool = False,
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
    def _time_text(label: str, rel_value: object, abs_value: object | None = None) -> str:
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

    return fig


def make_gantt(
    df: pd.DataFrame,
    color_by: str = "stall_bucket",
    chain_limit: int | None = None,
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
        height=max(450, 32 * len(chains)),
        xaxis_title="Simulation time [s]",
        yaxis_title="Chain start host",
        legend_title="Stalled packets" if color_by == "stall_bucket" else color_by,
        legend_traceorder="normal",
        margin=dict(l=20, r=20, t=60, b=40),
    )

    return fig


def make_gantt_comparison(
    left_df: pd.DataFrame,
    right_df: pd.DataFrame,
    *,
    left_label: str = "Scan 1",
    right_label: str = "Scan 2",
    color_by: str = "stall_bucket",
    chain_limit: int | None = None,
) -> go.Figure:
    if left_df.empty and right_df.empty:
        return go.Figure()

    left_plot, left_chains, _left_origin = _prepare_gantt_frame(
        left_df,
        chain_limit=chain_limit,
        normalize_time=True,
    )
    right_plot, right_chains, _right_origin = _prepare_gantt_frame(
        right_df,
        chain_limit=chain_limit,
        normalize_time=True,
    )

    left_fig = _make_gantt_figure(
        left_plot,
        chains=left_chains,
        color_by=color_by,
        title=left_label,
        base_col="plot_start_s",
        hover_start_col="plot_start_s",
        hover_end_col="plot_end_s",
        include_absolute_time=True,
    ) if not left_plot.empty else go.Figure()
    right_fig = _make_gantt_figure(
        right_plot,
        chains=right_chains,
        color_by=color_by,
        title=right_label,
        base_col="plot_start_s",
        hover_start_col="plot_start_s",
        hover_end_col="plot_end_s",
        include_absolute_time=True,
    ) if not right_plot.empty else go.Figure()

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(left_label, right_label),
    )

    for trace in left_fig.data:
        fig.add_trace(trace, row=1, col=1)
    for trace in right_fig.data:
        trace.showlegend = False
        fig.add_trace(trace, row=2, col=1)

    if color_by == "stall_bucket":
        left_present = set(left_plot["stall_bucket"].dropna().astype(str).unique()) if not left_plot.empty else set()
        right_present = set(right_plot["stall_bucket"].dropna().astype(str).unique()) if not right_plot.empty else set()
        all_present = left_present | right_present
        anchor_chain = left_chains[0] if left_chains else (right_chains[0] if right_chains else "")
        for bucket in STALL_BUCKET_ORDER:
            if bucket not in all_present or bucket in left_present:
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
                row=1,
                col=1,
            )

    max_end = 0.0
    if not left_plot.empty:
        max_end = max(max_end, float(left_plot["plot_end_s"].max()))
    if not right_plot.empty:
        max_end = max(max_end, float(right_plot["plot_end_s"].max()))

    fig.update_layout(
        barmode="overlay",
        bargap=0.35,
        height=max(650, 120 + 28 * max(len(left_chains), len(right_chains)) * 2),
        xaxis_title="Aligned simulation time [s]",
        legend_title="Stalled packets" if color_by == "stall_bucket" else color_by,
        legend_traceorder="normal",
        margin=dict(l=20, r=20, t=70, b=40),
    )
    fig.update_yaxes(title_text="Chain start host", row=1, col=1)
    fig.update_yaxes(title_text="Chain start host", row=2, col=1)
    if max_end > 0.0:
        fig.update_xaxes(range=[0.0, max_end * 1.02], row=1, col=1)

    return fig


def make_heatmap(
    df: pd.DataFrame,
    metric: str = "duration_ms",
    chain_limit: int | None = None,
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
                f"chain: {_row_value(r, 'chain')}"
                f"<br>hop: {_row_value(r, 'hop_index')}"
                f"<br>edge: {_row_value(r, 'edge')}"
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
        xaxis_title="Hop index in chain",
        yaxis_title="Chain start host",
        height=max(450, 32 * len(pivot.index)),
        margin=dict(l=20, r=20, t=60, b=40),
    )

    return fig