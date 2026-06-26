from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import math
import multiprocessing
import os
from pathlib import Path
import re
from typing import Any

import yaml

from sim.config.loader import load_experiment_spec
from sim.config.models import ConfigError
from sim.runners.experiment_runner import run_experiment


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _metric_value(metric: Any, key: str, default: Any = None) -> Any:
    if isinstance(metric, dict):
        return metric.get(key, default)
    return getattr(metric, key, default)


def _natural_sort_key(value: str) -> tuple[Any, ...]:
    parts = re.split(r"(\d+)", str(value))
    return tuple(int(part) if part.isdigit() else part.lower() for part in parts)


def _build_step_traffic_matrices(flow_metrics: list[Any]) -> list[dict[str, Any]]:
    step_pairs: dict[int, dict[tuple[str, str], int]] = {}
    step_nodes: dict[int, set[str]] = {}

    for metric in flow_metrics:
        step_id_raw = _metric_value(metric, "step_id")
        src = _metric_value(metric, "src_node_id")
        dst = _metric_value(metric, "dst_node_id")
        if step_id_raw is None or not src or not dst:
            continue

        try:
            step_id = int(step_id_raw)
        except (TypeError, ValueError):
            continue

        transmitted_bytes = _metric_value(metric, "transmitted_bytes")
        useful_bytes = _metric_value(metric, "useful_bytes")
        try:
            byte_count = int(transmitted_bytes if transmitted_bytes is not None else (useful_bytes if useful_bytes is not None else 0))
        except (TypeError, ValueError):
            byte_count = 0

        step_pairs.setdefault(step_id, {})[(str(src), str(dst))] = step_pairs.setdefault(step_id, {}).get((str(src), str(dst)), 0) + max(0, byte_count)
        step_nodes.setdefault(step_id, set()).update((str(src), str(dst)))

    matrices: list[dict[str, Any]] = []
    for step_id in sorted(step_pairs):
        nodes = sorted(step_nodes.get(step_id, set()), key=_natural_sort_key)
        if not nodes:
            continue
        node_index = {node: idx for idx, node in enumerate(nodes)}
        matrix = [[0 for _ in nodes] for _ in nodes]
        total_bytes = 0
        nonzero_pairs = 0
        for (src, dst), byte_count in step_pairs[step_id].items():
            matrix[node_index[src]][node_index[dst]] += byte_count
            total_bytes += byte_count
            if byte_count > 0:
                nonzero_pairs += 1
        matrices.append(
            {
                "step_id": step_id,
                "nodes": nodes,
                "matrix_bytes": matrix,
                "total_transmitted_bytes": total_bytes,
                "nonzero_pairs": nonzero_pairs,
            }
        )
    return matrices


def _normalize_flow_stall_counts(raw_counts: Any) -> dict[int, int]:
    if not isinstance(raw_counts, dict):
        return {}

    normalized: dict[int, int] = {}
    for flow_id_raw, count_raw in raw_counts.items():
        try:
            flow_id = int(flow_id_raw)
            count = max(0, int(count_raw))
        except (TypeError, ValueError):
            continue
        normalized[flow_id] = count
    return normalized


def _build_flow_stall_stats(flow_metrics: list[Any], stall_counts_by_flow_id: dict[int, int]) -> dict[str, Any]:
    training_flow_ids: set[int] = set()
    bucket_flow_ids: dict[tuple[int, int, int, int], set[int]] = {}

    for metric in flow_metrics:
        step_id_raw = _metric_value(metric, "step_id")
        flow_id_raw = _metric_value(metric, "flow_id")
        if step_id_raw is None or flow_id_raw is None:
            continue

        try:
            step_id = int(step_id_raw)
            flow_id = int(flow_id_raw)
        except (TypeError, ValueError):
            continue
        if step_id < 0:
            # Exclude non-training traffic such as background mice flows.
            continue

        training_flow_ids.add(flow_id)

        bucket_id_raw = _metric_value(metric, "bucket_id")
        if bucket_id_raw is None:
            continue
        try:
            job_id = int(_metric_value(metric, "job_id", 0) or 0)
            phase_id = int(_metric_value(metric, "phase_id", 0) or 0)
            bucket_id = int(bucket_id_raw)
        except (TypeError, ValueError):
            continue

        bucket_key = (job_id, step_id, phase_id, bucket_id)
        bucket_flow_ids.setdefault(bucket_key, set()).add(flow_id)

    avg_stalls_per_flow = (
        float(sum(stall_counts_by_flow_id.get(flow_id, 0) for flow_id in training_flow_ids)) / float(len(training_flow_ids))
        if training_flow_ids
        else 0.0
    )
    max_stalls_per_flow = (
        max((stall_counts_by_flow_id.get(flow_id, 0) for flow_id in training_flow_ids), default=0)
        if training_flow_ids
        else 0
    )
    bucket_bottleneck_stalls = max(
        (sum(stall_counts_by_flow_id.get(flow_id, 0) for flow_id in flow_ids) for flow_ids in bucket_flow_ids.values()),
        default=0,
    )
    stalls_per_flow_histogram: dict[int, int] = {}
    for flow_id in training_flow_ids:
        stall_count = int(stall_counts_by_flow_id.get(flow_id, 0))
        stalls_per_flow_histogram[stall_count] = stalls_per_flow_histogram.get(stall_count, 0) + 1

    return {
        "avg_stalls_per_flow": avg_stalls_per_flow,
        "max_stalls_per_flow": int(max_stalls_per_flow),
        "bucket_bottleneck_stalls": int(bucket_bottleneck_stalls),
        "training_flow_count": int(len(training_flow_ids)),
        "stalls_per_flow_histogram": stalls_per_flow_histogram,
    }


def _resolve_mtu_bytes(spec: Any, params: dict[str, Any]) -> int:
    """Resolve MTU bytes from resolved spec/summary with safe fallback."""
    candidates: list[Any] = [
        params.get("mtu"),
        (params.get("fabric") or {}).get("mtu") if isinstance(params.get("fabric"), dict) else None,
        spec.topology.params.get("mtu") if hasattr(spec, "topology") and hasattr(spec.topology, "params") else None,
        (spec.topology.params.get("fabric") or {}).get("mtu")
        if hasattr(spec, "topology") and hasattr(spec.topology, "params") and isinstance(spec.topology.params.get("fabric"), dict)
        else None,
    ]
    for value in candidates:
        try:
            mtu = int(value)
            if mtu > 0:
                return mtu
        except (TypeError, ValueError):
            continue
    return 1500


def _default_process_count(task_count: int) -> int:
    if task_count <= 1:
        return 1
    cores = max(1, math.ceil((os.cpu_count() or 1) / 2))
    chunk_size = max(1, math.ceil(task_count / cores))
    # Balance tasks across workers while keeping worker count bounded by roughly half the CPU cores.
    return max(1, min(task_count, int(task_count / chunk_size)))


@dataclass(frozen=True)
class BatchInput:
    label: str
    preset_name: str | None = None
    config_path: str | None = None
    overrides: tuple[str, ...] = ()


def _normalize_config_path(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = (_REPO_ROOT / p).resolve()
    return p


def collect_batch_inputs(
    *,
    presets: list[str] | None = None,
    configs: list[str] | None = None,
    directory: str | None = None,
) -> list[BatchInput]:
    inputs: list[BatchInput] = []
    for preset in presets or []:
        inputs.append(BatchInput(label=f"preset:{preset}", preset_name=preset))
    for config in configs or []:
        path = _normalize_config_path(config)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        inputs.append(BatchInput(label=str(path), config_path=str(path)))
    if directory:
        root = _normalize_config_path(directory)
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Batch directory not found: {root}")
        for path in sorted(root.rglob("*.yml")) + sorted(root.rglob("*.yaml")):
            inputs.append(BatchInput(label=str(path), config_path=str(path)))
    if not inputs:
        raise ConfigError("Batch requires at least one preset, config, or directory input")
    return inputs


def _run_batch_item(item: BatchInput) -> dict[str, Any]:
    def _duration_stats_ms(values: list[float]) -> dict[str, float | None]:
        if not values:
            return {"avg": None, "std": None, "min": None, "max": None}
        avg = sum(values) / len(values)
        var = sum((v - avg) ** 2 for v in values) / len(values)
        return {
            "avg": avg,
            "std": var ** 0.5,
            "min": min(values),
            "max": max(values),
        }

    spec = load_experiment_spec(
        preset_name=item.preset_name,
        config_path=item.config_path,
        overrides=list(item.overrides),
    )
    results = run_experiment(spec)
    stats = results.get("run statistics", {})
    params = results.get("parameters summary", {})
    bucket_metrics = results.get("ai_factory_bucket_metrics", [])
    flow_metrics = results.get("ai_factory_flow_metrics", [])
    flow_chain_diagnostics = results.get("ai_factory_flow_chain_diagnostics", [])

    bucket_durations_ms = [
        (float(getattr(m, "end_time", 0.0)) - float(getattr(m, "start_time", 0.0))) * 1000.0
        if not isinstance(m, dict)
        else (float(m.get("end_time", 0.0)) - float(m.get("start_time", 0.0))) * 1000.0
        for m in bucket_metrics
    ]
    bucket_stats = _duration_stats_ms(bucket_durations_ms)

    flow_durations_ms = [
        (float(getattr(m, "end_time", 0.0)) - float(getattr(m, "start_time", 0.0))) * 1000.0
        if not isinstance(m, dict)
        else (float(m.get("end_time", 0.0)) - float(m.get("start_time", 0.0))) * 1000.0
        for m in flow_metrics
    ]
    flow_stats = _duration_stats_ms(flow_durations_ms)

    job_durations_ms: list[float] = []
    step_avgs_ms: list[float] = []
    step_stds_ms: list[float] = []
    step_mins_ms: list[float] = []
    step_maxs_ms: list[float] = []
    per_job = stats.get("ai_factory_step_time_ms_per_job") or {}
    if isinstance(per_job, dict) and per_job:
        for value in per_job.values():
            if isinstance(value, dict) and value.get("job_duration_ms") is not None:
                job_durations_ms.append(float(value["job_duration_ms"]))
            if isinstance(value, dict) and value.get("step_time_avg_ms") is not None:
                step_avgs_ms.append(float(value["step_time_avg_ms"]))
            if isinstance(value, dict) and value.get("step_time_std_ms") is not None:
                step_stds_ms.append(float(value["step_time_std_ms"]))
            if isinstance(value, dict) and value.get("step_time_min_ms") is not None:
                step_mins_ms.append(float(value["step_time_min_ms"]))
            if isinstance(value, dict) and value.get("step_time_max_ms") is not None:
                step_maxs_ms.append(float(value["step_time_max_ms"]))

    job_stats = _duration_stats_ms(job_durations_ms)
    step_time_avg_ms = (sum(step_avgs_ms) / len(step_avgs_ms)) if step_avgs_ms else None
    step_time_std_ms = (sum(step_stds_ms) / len(step_stds_ms)) if step_stds_ms else None
    step_time_min_ms = min(step_mins_ms) if step_mins_ms else None
    step_time_max_ms = max(step_maxs_ms) if step_maxs_ms else None

    total_packets = stats.get("total packets count")
    stall_counts_by_flow_id = _normalize_flow_stall_counts(stats.get("packet_stall_triggered_count_by_flow_id", {}))
    flow_stall_stats = _build_flow_stall_stats(flow_metrics, stall_counts_by_flow_id)
    
    # Calculate ring-flow redundancy/packetization metrics over training flows only (exclude mice/background traffic).
    mtu_bytes = _resolve_mtu_bytes(spec, params)
    total_redundant_packets = 0
    total_redundant_bytes = 0
    ring_flow_count = 0
    total_packets_before_redundancy = 0
    total_packets_after_redundancy = 0
    total_useful_bytes_ring_flow = 0
    host_ring_useful_bytes: dict[tuple[int, int, int, int, str, str], int] = {}
    for metric in flow_metrics:
        step_id_raw = _metric_value(metric, "step_id")
        if step_id_raw is None:
            continue
        try:
            step_id = int(step_id_raw)
        except (TypeError, ValueError):
            continue
        if step_id < 0:
            # Exclude non-training traffic such as background mice flows.
            continue
        tag = str(_metric_value(metric, "tag", "") or "")
        if "/ring_step_" not in tag:
            continue

        ring_flow_count += 1
        transmitted = _metric_value(metric, "transmitted_bytes", 0)
        useful = _metric_value(metric, "useful_bytes", 0)
        if transmitted is not None and useful is not None:
            try:
                transmitted_bytes = max(0, int(transmitted))
                useful_bytes = max(0, int(useful))
                redundant_bytes = max(0, transmitted_bytes - useful_bytes)
                total_redundant_bytes += redundant_bytes
                total_useful_bytes_ring_flow += useful_bytes
                total_packets_before_redundancy += math.ceil(useful_bytes / float(mtu_bytes))
                total_packets_after_redundancy += math.ceil(transmitted_bytes / float(mtu_bytes))
                if redundant_bytes > 0:
                    total_redundant_packets += math.ceil(redundant_bytes / float(mtu_bytes))

                src_node_id = str(_metric_value(metric, "src_node_id", "") or "")
                bucket_raw = _metric_value(metric, "bucket_id", -1)
                op_tag = tag.split("/", 1)[0]
                ring_host_key = (
                    int(_metric_value(metric, "job_id", 0) or 0),
                    int(step_id),
                    int(_metric_value(metric, "phase_id", 0) or 0),
                    int(bucket_raw) if bucket_raw is not None else -1,
                    op_tag,
                    src_node_id,
                )
                host_ring_useful_bytes[ring_host_key] = host_ring_useful_bytes.get(ring_host_key, 0) + useful_bytes
            except (TypeError, ValueError):
                pass

    avg_redundant_packets_per_flow = (
        float(total_redundant_packets) / float(ring_flow_count)
        if ring_flow_count > 0
        else 0.0
    )
    avg_data_per_step_per_ring_bytes = (
        float(total_useful_bytes_ring_flow) / float(ring_flow_count)
        if ring_flow_count > 0
        else 0.0
    )
    avg_data_per_host_per_ring_bytes = (
        float(sum(host_ring_useful_bytes.values())) / float(len(host_ring_useful_bytes))
        if host_ring_useful_bytes
        else 0.0
    )
    avg_packets_in_ring_before_redundancy = (
        float(total_packets_before_redundancy) / float(ring_flow_count)
        if ring_flow_count > 0
        else 0.0
    )
    avg_packets_in_ring_after_redundancy = (
        float(total_packets_after_redundancy) / float(ring_flow_count)
        if ring_flow_count > 0
        else 0.0
    )
    avg_packets_per_ring_flow = avg_packets_in_ring_after_redundancy
    packets_in_ring_flow_with_redundancy = avg_packets_in_ring_after_redundancy
    
    packet_stall_marked_count = int(stats.get("packet_stall_marked_count", 0) or 0)
    packet_stall_triggered_count = int(stats.get("packet_stall_triggered_count", 0) or 0)
    packet_stall_triggered_percent = (
        (packet_stall_triggered_count / float(total_packets)) * 100.0
        if total_packets
        else 0.0
    )

    return {
        "label": item.label,
        "ok": True,
        "topology": spec.topology.name,
        "workload": spec.workload.name,
        "routing_mode": spec.routing.mode,
        "link_failure_percent": params.get("link_failure_percent"),
        "packet_stall_percent": params.get("packet_stall_percent", 0.0),
        "chunk_redundancy_extra_packets": params.get("chunk_redundancy_extra_packets", 0),
        # Keep historical key for compatibility with older dashboards.
        "chunk_time_avg_ms": flow_stats["avg"],
        "flow_time_avg_ms": flow_stats["avg"],
        "flow_time_std_ms": flow_stats["std"],
        "flow_time_min_ms": flow_stats["min"],
        "flow_time_max_ms": flow_stats["max"],
        "bucket_time_avg_ms": bucket_stats["avg"],
        "bucket_time_std_ms": bucket_stats["std"],
        "bucket_time_min_ms": bucket_stats["min"],
        "bucket_time_max_ms": bucket_stats["max"],
        "step_time_avg_ms": step_time_avg_ms,
        "step_time_std_ms": step_time_std_ms,
        "step_time_min_ms": step_time_min_ms,
        "step_time_max_ms": step_time_max_ms,
        "job_time_avg_ms": job_stats["avg"],
        "job_time_std_ms": job_stats["std"],
        "job_time_min_ms": job_stats["min"],
        "job_time_max_ms": job_stats["max"],
        "total_packets": total_packets,
        "packet_stall_marked_count": packet_stall_marked_count,
        "packet_stall_triggered_count": packet_stall_triggered_count,
        "packet_stall_triggered_percent": packet_stall_triggered_percent,
        "avg_stalls_per_flow": flow_stall_stats["avg_stalls_per_flow"],
        "max_stalls_per_flow": flow_stall_stats["max_stalls_per_flow"],
        "bucket_bottleneck_stalls": flow_stall_stats["bucket_bottleneck_stalls"],
        "training_flow_count": flow_stall_stats["training_flow_count"],
        "stalls_per_flow_histogram": flow_stall_stats["stalls_per_flow_histogram"],
        "total_redundant_packets": total_redundant_packets,
        "total_redundant_bytes": total_redundant_bytes,
        "avg_redundant_packets_per_flow": avg_redundant_packets_per_flow,
        "avg_packets_per_ring_flow": avg_packets_per_ring_flow,
        "avg_data_per_host_per_ring_bytes": avg_data_per_host_per_ring_bytes,
        "avg_data_per_step_per_ring_bytes": avg_data_per_step_per_ring_bytes,
        "avg_packets_in_ring_before_redundancy": avg_packets_in_ring_before_redundancy,
        "avg_packets_in_ring_after_redundancy": avg_packets_in_ring_after_redundancy,
        "packets_in_ring_flow_with_redundancy": packets_in_ring_flow_with_redundancy,
        "dropped_packets": stats.get("dropped packets count", 0),
        "dropped_packets_percent": stats.get("dropped packets percentage", 0.0),
        "max_per_flow_drops": stats.get("max per flow drops", 0),
        "sim_time_s": stats.get("total run time (simulator time in seconds)"),
        "step_traffic_matrices": _build_step_traffic_matrices(flow_metrics),
        "deep_flow_chain_log_enabled": bool(spec.run.deep_flow_chain_log),
        "deep_flow_chain_diagnostics": flow_chain_diagnostics if spec.run.deep_flow_chain_log else [],
    }


def _run_batch_item_safe(item: BatchInput) -> dict[str, Any]:
    try:
        return _run_batch_item(item)
    except Exception as exc:
        return {"label": item.label, "ok": False, "error": str(exc)}


def run_batch(
    inputs: list[BatchInput],
    *,
    stop_on_error: bool = False,
    use_processes: bool = False,
    max_processes: int | None = None,
) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []

    should_parallelize = use_processes and len(inputs) > 1
    if should_parallelize:
        process_count = max_processes or _default_process_count(len(inputs))
        process_count = max(1, min(process_count, len(inputs)))
        mp_ctx = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=process_count, mp_context=mp_ctx) as executor:
            for result in executor.map(_run_batch_item_safe, inputs):
                summary.append(result)
                if stop_on_error and not result.get("ok", False):
                    raise RuntimeError(result.get("error", "Unknown batch worker error"))
        return summary

    for item in inputs:
        try:
            summary.append(_run_batch_item(item))
        except Exception as exc:
            summary.append({"label": item.label, "ok": False, "error": str(exc)})
            if stop_on_error:
                raise
    return summary


def write_batch_summary(summary: list[dict[str, Any]], output_path: str) -> Path:
    path = _normalize_config_path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(summary, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path
