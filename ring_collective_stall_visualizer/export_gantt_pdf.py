from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd
import plotly.graph_objects as go

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from ringviz.parser import parse_log_text
from ringviz.plots import make_gantt, make_gantt_comparison


def load_log(path: Path) -> pd.DataFrame:
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_log_text(text)


def _apply_filters(df: pd.DataFrame, filter_specs: list[str]) -> pd.DataFrame:
    out = df
    for spec in filter_specs:
        if "=" not in spec:
            raise ValueError(f"Invalid --filter format: {spec!r} (expected key=v1,v2,...)")
        key, raw_values = spec.split("=", 1)
        key = key.strip()
        values = [part.strip() for part in raw_values.split(",") if part.strip()]
        if not key or not values:
            raise ValueError(f"Invalid --filter format: {spec!r} (expected key=v1,v2,...)")
        if key not in out.columns:
            raise ValueError(f"Invalid --filter {spec!r}: the log has no column {key!r}")
        out = out[out[key].astype(str).isin(set(values))]
    return out


def _build_export_figure(fig: go.Figure) -> tuple[go.Figure, int, int]:
    export_fig = go.Figure(fig)

    annotations = list(export_fig.layout.annotations)
    subtitle_annotations = [
        a for a in annotations
        if not a.showarrow and str(a.text).strip()
    ]
    n_panels = max(1, len(subtitle_annotations))

    if n_panels == 1:
        layout_json = export_fig.layout.to_plotly_json()
        n_xaxes = int(sum(1 for k in layout_json if k.startswith("xaxis")))
        if n_xaxes > n_panels:
            n_panels = n_xaxes

    y_values: set[str] = set()
    for trace in export_fig.data:
        y_arr = trace.y
        if y_arr is not None:
            y_values.update(str(v) for v in y_arr if v is not None)
    chains_per_panel = max(1, len(y_values))

    export_height = max(900, 260 + n_panels * (chains_per_panel * 44 + 110))
    export_width = 2200 if n_panels > 1 else 1600

    existing_layout = export_fig.layout.to_plotly_json()
    coloraxis_preserve = {k: v for k, v in existing_layout.items() if k.startswith("coloraxis")}

    export_fig.update_layout(
        width=export_width,
        height=export_height,
        font=dict(size=16),
        title=dict(font=dict(size=20), x=0.5, xanchor="center"),
        margin=dict(l=145, r=135, t=115, b=135),
        bargap=0.28,
    )
    if coloraxis_preserve:
        export_fig.update_layout(**coloraxis_preserve)

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


def build_gantt_export_figure(
    frames: list[pd.DataFrame],
    *,
    color_by: str,
    chain_limit: int,
    labels: list[str] | None = None,
    title: str | None = None,
) -> tuple[go.Figure, int, int]:
    """The PDF-sized Gantt figure of one log, or of up to four logs side by side; returns (figure, width, height)."""
    if len(frames) == 1:
        fig = make_gantt(frames[0], color_by=color_by, chain_limit=chain_limit)
    else:
        fig = make_gantt_comparison(frames, labels=labels, color_by=color_by, chain_limit=chain_limit)
    if title:
        fig.update_layout(title_text=title)
    return _build_export_figure(fig)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export ring-collective Gantt directly to PDF (no Streamlit UI).")
    parser.add_argument("logs", nargs="+", help="One to four input .log/.txt files")
    parser.add_argument("--out", required=True, help="Output PDF path")
    parser.add_argument(
        "--color-by",
        required=True,
        choices=["stall_bucket", "stalled_packets", "duration_ms", "max_egress", "avg_egress"],
        help="Gantt coloring dimension",
    )
    parser.add_argument("--chain-limit", type=int, required=True, help="Max number of chains to display")
    parser.add_argument(
        "--labels",
        help="Optional comma-separated subplot labels for multi-log mode (e.g. 'Baseline,Tuned'); unlabeled panels are named 'Scan N'",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help="Filter rows before plotting, format key=v1,v2,... (repeatable)",
    )
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)

    input_paths = [Path(p).expanduser().resolve() for p in args.logs]
    if len(input_paths) == 0:
        raise SystemExit("Provide at least one log path")
    if len(input_paths) > 4:
        raise SystemExit("At most four logs are supported")

    frames: list[pd.DataFrame] = []
    for p in input_paths:
        if not p.exists():
            raise FileNotFoundError(f"Input log not found: {p}")
        df = load_log(p)
        if df.empty:
            raise ValueError(f"No flow records parsed from: {p}")
        filtered = _apply_filters(df, args.filter)
        if filtered.empty:
            raise ValueError(f"All rows filtered out for: {p}")
        frames.append(filtered)

    labels = [part.strip() for part in args.labels.split(",") if part.strip()] if args.labels else None
    export_fig, export_width, export_height = build_gantt_export_figure(
        frames, color_by=args.color_by, chain_limit=args.chain_limit, labels=labels
    )

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_bytes = export_fig.to_image(format="pdf", width=export_width, height=export_height)
    out_path.write_bytes(pdf_bytes)

    print(f"Wrote PDF to: {out_path}")
    print(f"Export size: {export_width} x {export_height}")
    print(f"Logs: {len(frames)} | color_by={args.color_by} | chain_limit={args.chain_limit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


