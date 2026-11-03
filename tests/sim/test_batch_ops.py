from __future__ import annotations

from pathlib import Path

from ai_factory.core.entities import FlowMetrics
from sim.runners.batch_runner import _build_flow_stall_stats, collect_batch_inputs, run_batch, write_batch_summary
from sim.config.loader import load_sweep_spec
from sim.runners.sweep_runner import build_sweep_inputs, run_sweep

DP_SMALL = "tests/fixtures/dp_small.yaml"


def test_collect_and_run_batch_from_configs() -> None:
    inputs = collect_batch_inputs(configs=[DP_SMALL])
    summary = run_batch(inputs)

    assert len(summary) == 1
    assert all(item["ok"] for item in summary)




def test_build_flow_stall_stats_aggregates_training_flows_and_gradient_bucket_bottleneck() -> None:
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
            flow_id=5,
            job_id=202,
            step_id=0,
            phase_id=1,
            bucket_id=0,
            tag="rs",
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
            5: 4,
        },
    )

    assert stats == {
        "avg_stalls_per_flow": 1.75,
        "max_stalls_per_flow": 4,
        "gradient_bucket_bottleneck_stalls": 4,
        "training_flow_count": 4,
        "stalls_per_flow_histogram": {1: 1, 2: 1, 4: 1, 0: 1},
    }


def test_build_and_run_sweep(write_sweep_config) -> None:
    cfg = write_sweep_config({"workload.kind": ["dp-heavy", "none"], "topology.params.leaf_count": [8, 16]})
    sweep = load_sweep_spec(cfg)
    inputs = build_sweep_inputs(config_path=cfg, sweep=sweep)
    assert len(inputs) == 4

    summary = run_sweep(config_path=cfg, sweep=sweep)
    assert len(summary) == 4
    assert all(item["ok"] for item in summary)
    assert {item["workload"] for item in summary} == {"dp-heavy", "none"}


