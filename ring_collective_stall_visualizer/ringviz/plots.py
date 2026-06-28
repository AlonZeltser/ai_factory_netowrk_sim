import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


STALL_BUCKET_ORDER = ["0", "1", "2", "3", "4", "5+"]

STALL_COLOR_MAP = {
    "0": "#9E9E9E",   # gray
    "1": "#0072B2",   # blue
    "2": "#E69F00",   # orange
    "3": "#009E73",   # green
    "4": "#CC79A7",   # purple
    "5+": "#D55E00",  # vermillion
}


def make_gantt(
    df: pd.DataFrame,
    color_by: str = "stall_bucket",
    chain_limit: int | None = None,
) -> go.Figure:
    if df.empty:
        return go.Figure()

    plot_df = df.copy()

    chains = list(plot_df["chain"].drop_duplicates())

    if chain_limit is not None:
        chains = chains[:chain_limit]
        plot_df = plot_df[plot_df["chain"].isin(chains)]

    category_orders = {
        "chain": chains[::-1],
    }

    color_discrete_map = None

    if color_by == "stall_bucket":
        category_orders["stall_bucket"] = STALL_BUCKET_ORDER
        color_discrete_map = STALL_COLOR_MAP

    plot_df["hover"] = (
        "chain: " + plot_df["chain"].astype(str)
        + "<br>hop: " + plot_df["hop_index"].astype(str)
        + "<br>edge: " + plot_df["edge"].astype(str)
        + "<br>start: " + plot_df["start_s"].round(6).astype(str) + " s"
        + "<br>end: " + plot_df["end_s"].round(6).astype(str) + " s"
        + "<br>duration: " + plot_df["duration_ms"].round(3).astype(str) + " ms"
        + "<br>stalled packets: " + plot_df["stalled_packets"].astype(str)
        + "<br>max egress: " + plot_df["max_egress"].astype(str)
        + "<br>avg egress: " + plot_df["avg_egress"].round(3).astype(str)
    )

    fig = px.bar(
        plot_df,
        x="duration_s",
        y="chain",
        base="start_s",
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
        title="Ring collective Gantt view",
    )

    fig.update_traces(
        hovertemplate="%{customdata[0]}<extra></extra>",
        marker_line_color="black",
        marker_line_width=0.8,
        opacity=0.9,
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
                f"chain: {r['chain']}"
                f"<br>hop: {r['hop_index']}"
                f"<br>edge: {r['edge']}"
                f"<br>{metric}: {r[metric]:.6g}"
                f"<br>duration: {r['duration_ms']:.3f} ms"
                f"<br>stalled packets: {r['stalled_packets']}"
                f"<br>max egress: {r['max_egress']}"
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