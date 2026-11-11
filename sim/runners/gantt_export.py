"""Gantt PDFs of sample training steps, made from a sweep's chain logs without the web app.

Each run gets one PDF per sample step (first, middle, slowest; see deep_flow_log.SAMPLE_KINDS).
With `sweep.gantt_compare`, the runs that differ only in the compared key also get one PDF per
sample kind with their logs side by side. The figures come from the Ring Collective Stall
Visualizer, so they match its web app and export_gantt_pdf.py.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any

from run_label import label_slug
from sim.config.models import ConfigError, SweepSpec
from sim.runners.deep_flow_log import SAMPLE_KINDS, chain_log_path
from sim.runners.sweep_runner import format_override_value, label_vary_values

_log = logging.getLogger(__name__)

GANTT_COLOR_BY = "stall_bucket"
# Figures rendered per batch; one batch shares one headless-Chrome session, which is much faster.
_RENDER_BATCH = 20


@dataclass(frozen=True)
class GanttPdfPlan:
    logs: tuple[Path, ...]
    labels: tuple[str, ...] | None
    title: str
    out: Path


def _short_key(key: str) -> str:
    return key.rsplit(".", 1)[-1]


def _values_title(values: dict[str, str]) -> str:
    return ", ".join(f"{_short_key(key)}={value}" for key, value in values.items())


def _sample_step(row: dict[str, Any], kind: str) -> tuple[int, int] | None:
    for sample in row.get("deep_flow_chain_sample_steps") or []:
        if kind in sample["kinds"]:
            return int(sample["job_id"]), int(sample["step_id"])
    return None


def plan_gantt_pdfs(
    summary: list[dict[str, Any]], *, sweep: SweepSpec, chain_log_root: Path, out_dir: Path
) -> list[GanttPdfPlan]:
    rows = [row for row in summary if row.get("ok") and row.get("deep_flow_chain_sample_steps")]
    plans: list[GanttPdfPlan] = []

    for row in rows:
        label = str(row["label"])
        title = _values_title(label_vary_values(label)) or label
        for sample in row["deep_flow_chain_sample_steps"]:
            job_id, step_id, kinds = int(sample["job_id"]), int(sample["step_id"]), list(sample["kinds"])
            plans.append(
                GanttPdfPlan(
                    logs=(chain_log_path(chain_log_root, label, job_id, step_id),),
                    labels=None,
                    title=f"{title} | step {step_id} ({', '.join(kinds)})",
                    out=out_dir / label_slug(label) / f"job_{job_id}_step_{step_id}_{'_'.join(kinds)}.pdf",
                )
            )

    if sweep.gantt_compare is None:
        return plans

    key, values = sweep.gantt_compare
    wanted = [format_override_value(value) for value in values]
    # Runs with the same values for every other vary key form one comparison group.
    groups: dict[tuple[tuple[str, str], ...], dict[str, dict[str, Any]]] = {}
    for row in rows:
        run_values = label_vary_values(str(row["label"]))
        if run_values.get(key) not in wanted:
            continue
        others = tuple((k, v) for k, v in run_values.items() if k != key)
        groups.setdefault(others, {})[run_values[key]] = row

    for others, by_value in groups.items():
        members = [(value, by_value[value]) for value in wanted if value in by_value]
        if len(members) < 2:
            continue
        group_title = _values_title(dict(others))
        group_slug = label_slug("_".join(f"{_short_key(k)}={v}" for k, v in others)) or "all"
        for kind in SAMPLE_KINDS:
            logs: list[Path] = []
            labels: list[str] = []
            for value, row in members:
                job_step = _sample_step(row, kind)
                if job_step is None:
                    continue
                logs.append(chain_log_path(chain_log_root, str(row["label"]), *job_step))
                labels.append(f"{_short_key(key)}={value} (step {job_step[1]})")
            if len(logs) < 2:
                continue
            plans.append(
                GanttPdfPlan(
                    logs=tuple(logs),
                    labels=tuple(labels),
                    title=f"{group_title + ' | ' if group_title else ''}{kind} step, by {_short_key(key)}",
                    out=out_dir / f"compare_{label_slug(_short_key(key))}" / f"{group_slug}_{kind}.pdf",
                )
            )
    return plans


def check_gantt_export_ready() -> None:
    """Render a tiny PDF, so a missing package or browser fails before a long sweep, not after it."""
    try:
        import plotly.graph_objects as go
        import plotly.io as pio

        from ring_collective_stall_visualizer.export_gantt_pdf import build_gantt_export_figure  # noqa: F401

        pio.to_image(go.Figure(go.Bar(x=[1], y=["a"], orientation="h")), format="pdf", width=200, height=100)
    except Exception as exc:
        raise ConfigError(
            "sweep.gantt_pdfs needs the visualizer packages and a Chrome browser for PDF export: "
            "pip install -r ring_collective_stall_visualizer/requirements.txt, then, if Chrome is "
            f"missing, run plotly_get_chrome. Error: {exc}"
        ) from exc


def export_gantt_pdfs(
    summary: list[dict[str, Any]], *, sweep: SweepSpec, chain_log_root: Path, out_dir: Path
) -> list[Path]:
    plans = plan_gantt_pdfs(summary, sweep=sweep, chain_log_root=chain_log_root, out_dir=out_dir)
    if not plans:
        return []

    import plotly.io as pio

    from ring_collective_stall_visualizer.export_gantt_pdf import build_gantt_export_figure, load_log

    written: list[Path] = []
    for start in range(0, len(plans), _RENDER_BATCH):
        figures, paths, widths, heights = [], [], [], []
        for plan in plans[start : start + _RENDER_BATCH]:
            frames = [load_log(path) for path in plan.logs]
            if any(frame.empty for frame in frames):
                _log.warning("Skipping Gantt PDF %s: a chain log has no ring chains", plan.out)
                continue
            figure, width, height = build_gantt_export_figure(
                frames,
                color_by=GANTT_COLOR_BY,
                chain_limit=sweep.gantt_chain_limit,
                labels=list(plan.labels) if plan.labels else None,
                title=plan.title,
            )
            plan.out.parent.mkdir(parents=True, exist_ok=True)
            figures.append(figure)
            paths.append(plan.out)
            widths.append(width)
            heights.append(height)
        if figures:
            pio.write_images(figures, paths, format="pdf", width=widths, height=heights)
            written.extend(paths)
        _log.info("Gantt PDFs: %d/%d written", len(written), len(plans))
    return written
