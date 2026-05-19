from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from sim.config.loader import load_experiment_spec
from sim.config.models import ConfigError
from sim.runners.experiment_runner import run_experiment


_REPO_ROOT = Path(__file__).resolve().parents[2]


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


def run_batch(inputs: list[BatchInput], *, stop_on_error: bool = False) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []

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

    for item in inputs:
        try:
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

            summary.append(
                {
                    "label": item.label,
                    "ok": True,
                    "topology": spec.topology.name,
                    "workload": spec.workload.name,
                    "routing_mode": spec.routing.mode,
                    "link_failure_percent": params.get("link_failure_percent"),
                    "packet_stall_percent": params.get("packet_stall_percent", 0.0),
                    "chunk_redundancy_percent": params.get("chunk_redundancy_percent", 0.0),
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
                    "total_packets": stats.get("total packets count"),
                    "dropped_packets": stats.get("dropped packets count"),
                    "sim_time_s": stats.get("total run time (simulator time in seconds)"),
                }
            )
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

