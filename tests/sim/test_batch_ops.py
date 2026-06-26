from __future__ import annotations

from pathlib import Path

from ai_factory.core.entities import FlowMetrics
from sim.runners.batch_runner import _build_flow_stall_stats, collect_batch_inputs, run_batch, write_batch_summary
from sim.runners.sweep_runner import build_sweep_inputs, run_sweep


def test_collect_and_run_batch_from_presets() -> None:
    inputs = collect_batch_inputs(presets=["ai/su-dp-low-small", "ai/su-mixed-light"])
    summary = run_batch(inputs)

    assert len(summary) == 2
    assert all(item["ok"] for item in summary)


def test_collect_batch_from_directory_and_write_summary(tmp_path: Path) -> None:
    cfg = tmp_path / "batch_case.yaml"
    topology_defaults = Path("sim/presets/ai/topology-clos-large-scale-unit.yaml").resolve()
    cfg.write_text(
        f"""
extends: {topology_defaults}
kind: experiment
meta:
  name: batch-case
run:
  visualize: false
routing:
  mode: ecmp
  ecmp_flowlet_n_packets: 1
workload:
  kind: none
  params: {{}}
""".strip(),
        encoding="utf-8",
    )

    inputs = collect_batch_inputs(directory=str(tmp_path))
    summary = run_batch(inputs)
    assert len(summary) == 1
    assert summary[0]["ok"] is True

    out = write_batch_summary(summary, str(tmp_path / "summary.yaml"))
    assert out.exists()
    assert "batch-case" not in out.read_text(encoding="utf-8") or out.read_text(encoding="utf-8")


def test_build_flow_stall_stats_aggregates_training_flows_and_bucket_bottleneck() -> None:
    flow_metrics = [
        FlowMetrics(
            flow_id=1,
            job_id=101,
            step_id=0,
            phase_id=1,
            bucket_id=0,
            tag="rs",
            src_node_id="h1",
            dst_node_id="h2",
            start_time=0.0,
            end_time=0.001,
            transmitted_bytes=4096,
            useful_bytes=4096,
        ),
        FlowMetrics(
            flow_id=2,
            job_id=101,
            step_id=0,
            phase_id=1,
            bucket_id=0,
            tag="ag",
            src_node_id="h2",
            dst_node_id="h3",
            start_time=0.0,
            end_time=0.001,
            transmitted_bytes=4096,
            useful_bytes=4096,
        ),
        FlowMetrics(
            flow_id=3,
            job_id=101,
            step_id=1,
            phase_id=1,
            bucket_id=1,
            tag="rs",
            src_node_id="h1",
            dst_node_id="h3",
            start_time=0.0,
            end_time=0.001,
            transmitted_bytes=4096,
            useful_bytes=4096,
        ),
        FlowMetrics(
            flow_id=4,
            job_id=-1,
            step_id=-1,
            phase_id=-1,
            bucket_id=None,
            tag="mice",
            src_node_id="h3",
            dst_node_id="h4",
            start_time=0.0,
            end_time=0.001,
            transmitted_bytes=4096,
            useful_bytes=4096,
        ),
        FlowMetrics(
            flow_id=5,
            job_id=202,
            step_id=0,
            phase_id=1,
            bucket_id=0,
            tag="tp",
            src_node_id="h4",
            dst_node_id="h5",
            start_time=0.0,
            end_time=0.001,
            transmitted_bytes=4096,
            useful_bytes=4096,
        ),
    ]

    stats = _build_flow_stall_stats(
        flow_metrics,
        {
            1: 2,
            2: 1,
            4: 9,
            5: 4,
        },
    )

    assert stats == {
        "avg_stalls_per_flow": 1.75,
        "max_stalls_per_flow": 4,
        "bucket_bottleneck_stalls": 4,
        "training_flow_count": 4,
        "stalls_per_flow_histogram": {1: 1, 2: 1, 4: 1, 0: 1},
    }


def test_build_and_run_sweep() -> None:
    inputs = build_sweep_inputs(
        preset_name="ai/su-dp-low-small",
        vary_specs=["workload.kind=dp-heavy,none", "topology.params.leaf_count=8,16"],
    )
    assert len(inputs) == 4

    summary = run_sweep(
        preset_name="ai/su-dp-low-small",
        vary_specs=["workload.kind=dp-heavy,none", "topology.params.leaf_count=8,16"],
    )
    assert len(summary) == 4
    assert all(item["ok"] for item in summary)
    assert {item["workload"] for item in summary} == {"dp-heavy", "none"}


