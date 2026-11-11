from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from run_label import label_slug


def _natural_sort_key(value: str) -> tuple[Any, ...]:
    parts = re.split(r"(\d+)", str(value))
    return tuple(int(part) if part.isdigit() else part.lower() for part in parts)


def _fmt_float(value: Any) -> str:
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return ""


def _step_relative_float(value: Any, *, origin: float) -> str:
    try:
        return f"{float(value) - float(origin):.6f}"
    except (TypeError, ValueError):
        return ""


def _build_chains_for_group(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_step_sender: dict[int, dict[str, dict[str, Any]]] = {}
    max_ring_step = -1
    for record in records:
        ring_step = record.get("ring_step")
        src = str(record.get("src_node_id") or "")
        if ring_step is None or not src:
            continue
        try:
            step = int(ring_step)
        except (TypeError, ValueError):
            continue
        by_step_sender.setdefault(step, {})[src] = record
        max_ring_step = max(max_ring_step, step)

    if 0 not in by_step_sender:
        return {}

    chains: dict[str, list[dict[str, Any]]] = {}
    for origin in sorted(by_step_sender[0].keys(), key=_natural_sort_key):
        current = origin
        chain_records: list[dict[str, Any]] = []
        for step in range(0, max_ring_step + 1):
            flow_record = by_step_sender.get(step, {}).get(current)
            if flow_record is None:
                break
            chain_records.append(flow_record)
            current = str(flow_record.get("dst_node_id") or "")
            if not current:
                break
        if chain_records:
            chains[origin] = chain_records
    return chains


def _write_step_file(path: Path, records: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    lines.append("header: net packets in flow, gross packets in flow")
    lines.append(
        "columns: sending host, receiving host, sim start time (step-relative), sim end time (step-relative), sim duration, # of packets stalled, max place in egress, average place in egress, latest arriving valuable packet to receiver (N): start time, end time, list of egress values, sum of egress"
    )
    lines.append("")

    step_origin_time = min(
        (float(record.get("sim_start_time")) for record in records if record.get("sim_start_time") is not None),
        default=0.0,
    )

    grouped: dict[tuple[Any, Any, Any, Any, Any], list[dict[str, Any]]] = {}
    for record in records:
        key = (
            record.get("job_id"),
            record.get("step_id"),
            record.get("phase_id"),
            record.get("bucket_id"),
            record.get("op_tag"),
        )
        grouped.setdefault(key, []).append(record)

    for key in sorted(grouped.keys(), key=lambda x: tuple(_natural_sort_key(str(v)) for v in x)):
        job_id, step_id, phase_id, bucket_id, op_tag = key
        lines.append(f"[chain_group] job={job_id} step={step_id} phase={phase_id} bucket={bucket_id} op={op_tag}")
        chains = _build_chains_for_group(grouped[key])
        if not chains:
            lines.append("  (no complete ring chains found)")
            lines.append("")
            continue

        for chain_origin in sorted(chains.keys(), key=_natural_sort_key):
            lines.append(f"chain {chain_origin}")
            for record in sorted(chains[chain_origin], key=lambda item: int(item.get("ring_step", -1))):
                latest_egress_values = list(record.get("latest_valuable_packet_egress_values") or [])
                lines.append(
                    "  "
                    + " | ".join(
                        [
                            f"net packets in flow={record.get('net_packets_in_flow', 0)}",
                            f"gross packets in flow={record.get('gross_packets_in_flow', 0)}",
                            f"sending host={record.get('src_node_id', '')}",
                            f"receiving host={record.get('dst_node_id', '')}",
                            f"sim start time={_step_relative_float(record.get('sim_start_time'), origin=step_origin_time)}",
                            f"sim end time={_step_relative_float(record.get('sim_end_time'), origin=step_origin_time)}",
                            f"sim duration={_fmt_float(record.get('sim_duration'))}",
                            f"# of packets stalled={int(record.get('packets_stalled', 0) or 0)}",
                            f"max place in egress={int(record.get('max_place_in_egress', 0) or 0)}",
                            f"average place in egress={_fmt_float(record.get('avg_place_in_egress'))}",
                            f"N start time={_step_relative_float(record.get('latest_valuable_packet_start_time'), origin=step_origin_time)}",
                            f"N end time={_step_relative_float(record.get('latest_valuable_packet_end_time'), origin=step_origin_time)}",
                            f"N egress values={latest_egress_values}",
                            f"N egress sum={int(record.get('latest_valuable_packet_egress_sum', 0) or 0)}",
                        ]
                    )
                )
            lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


# Which training steps of each run get a Gantt PDF, in this order.
SAMPLE_KINDS = ("first", "middle", "slowest")


def _record_job_step(record: Any) -> tuple[int, int] | None:
    if not isinstance(record, dict):
        return None
    try:
        step_id = int(record.get("step_id"))
        job_id = int(record.get("job_id", 0) or 0)
    except (TypeError, ValueError):
        return None
    return (job_id, step_id) if step_id >= 0 else None


def sample_chain_log_steps(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pick the first, middle and slowest training step of each job.

    "Slowest" is the step whose ring flows span the longest time (first flow start to
    last flow end). Returns one entry per picked step: {"job_id", "step_id", "kinds"},
    where `kinds` lists every sample kind that step was picked as.
    """
    span: dict[tuple[int, int], list[float]] = {}
    for record in records:
        job_step = _record_job_step(record)
        if job_step is None:
            continue
        try:
            start, end = float(record["sim_start_time"]), float(record["sim_end_time"])
        except (KeyError, TypeError, ValueError):
            continue
        bounds = span.setdefault(job_step, [start, end])
        bounds[0], bounds[1] = min(bounds[0], start), max(bounds[1], end)

    samples: list[dict[str, Any]] = []
    for job_id in sorted({job for job, _ in span}):
        steps = sorted(step for job, step in span if job == job_id)
        picked = {
            "first": steps[0],
            "middle": steps[len(steps) // 2],
            # Ties go to the earliest step.
            "slowest": max(steps, key=lambda step: (span[(job_id, step)][1] - span[(job_id, step)][0], -step)),
        }
        for step_id in sorted(set(picked.values())):
            kinds = [kind for kind in SAMPLE_KINDS if picked[kind] == step_id]
            samples.append({"job_id": job_id, "step_id": step_id, "kinds": kinds})
    return samples


def keep_sampled_steps(records: list[dict[str, Any]], samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keep = {(sample["job_id"], sample["step_id"]) for sample in samples}
    return [record for record in records if _record_job_step(record) in keep]


def run_chain_log_dir(root: Path, run_label: str) -> Path:
    return root / (label_slug(run_label) or "run")


def chain_log_path(root: Path, run_label: str, job_id: int, step_id: int) -> Path:
    """Where write_sweep_deep_flow_logs puts the chain log of one run step."""
    return run_chain_log_dir(root, run_label) / f"job_{job_id}_step_{step_id}.txt"


def write_sweep_deep_flow_logs(summary: list[dict[str, Any]], *, out_dir: str) -> list[Path]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for row in summary:
        if not isinstance(row, dict) or not row.get("ok", False):
            continue
        if not bool(row.get("deep_flow_chain_log_enabled", False)):
            continue

        raw_records = row.get("deep_flow_chain_diagnostics")
        if not isinstance(raw_records, list) or not raw_records:
            continue

        run_label = str(row.get("label") or "run")
        run_chain_log_dir(root, run_label).mkdir(parents=True, exist_ok=True)

        by_step: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for record in raw_records:
            job_step = _record_job_step(record)
            if job_step is not None:
                by_step.setdefault(job_step, []).append(record)

        for (job_id, step_id), records in sorted(by_step.items()):
            step_path = chain_log_path(root, run_label, job_id, step_id)
            _write_step_file(step_path, records)
            written.append(step_path)

    return written

