from __future__ import annotations

from pathlib import Path
import yaml

from ai_factory.core.entities import BucketMetrics, FlowMetrics
from visualization.experiment_visualizer import (
    visualize_ai_factory_comm_distributions,
    visualize_sweep_time_comparison,
    visualize_sweep_time_comparison_from_yaml,
)


def test_visualize_ai_factory_comm_distributions_saves_file(tmp_path: Path) -> None:
    bucket_metrics = [
        BucketMetrics(
            job_id=1,
            step_id=0,
            phase_id=1,
            phase_name="gradient_sync",
            bucket_id=0,
            start_time=0.0,
            end_time=0.010,
            flow_count=8,
            transmitted_bytes=9000,
            useful_bytes=8000,
        ),
        BucketMetrics(
            job_id=1,
            step_id=0,
            phase_id=1,
            phase_name="gradient_sync",
            bucket_id=1,
            start_time=0.010,
            end_time=0.025,
            flow_count=8,
            transmitted_bytes=9000,
            useful_bytes=8000,
        ),
    ]
    flow_metrics = [
        FlowMetrics(
            flow_id=11,
            job_id=1,
            step_id=0,
            phase_id=1,
            bucket_id=0,
            tag="reduce_scatter/ring_step_0",
            src_node_id="h1",
            dst_node_id="h2",
            start_time=0.0,
            end_time=0.003,
            transmitted_bytes=1125,
            useful_bytes=1000,
        ),
        FlowMetrics(
            flow_id=12,
            job_id=1,
            step_id=0,
            phase_id=1,
            bucket_id=0,
            tag="all_gather/ring_step_0",
            src_node_id="h2",
            dst_node_id="h3",
            start_time=0.001,
            end_time=0.005,
            transmitted_bytes=1125,
            useful_bytes=1000,
        ),
    ]

    output = visualize_ai_factory_comm_distributions(
        bucket_metrics,
        flow_metrics,
        routing_mode="adaptive",
        redundancy_percent=12.5,
        out_dir=str(tmp_path),
        show=False,
    )

    assert output is not None
    assert Path(output).exists()


def test_visualize_sweep_time_comparison_saves_four_files(tmp_path: Path) -> None:
    summary = [
        {"ok": True, "chunk_redundancy_percent": 0.0, "link_failure_percent": 0.0, "packet_stall_percent": 0.0, "flow_time_avg_ms": 1.0, "bucket_time_avg_ms": 5.0, "step_time_avg_ms": 20.0, "job_time_avg_ms": 50.0},
        {"ok": True, "chunk_redundancy_percent": 0.0, "link_failure_percent": 0.0, "packet_stall_percent": 3.0, "flow_time_avg_ms": 1.5, "bucket_time_avg_ms": 5.5, "step_time_avg_ms": 22.0, "job_time_avg_ms": 55.0},
        {"ok": True, "chunk_redundancy_percent": 12.5, "link_failure_percent": 0.0, "packet_stall_percent": 0.0, "flow_time_avg_ms": 0.9, "bucket_time_avg_ms": 4.8, "step_time_avg_ms": 18.5, "job_time_avg_ms": 49.0},
        {"ok": True, "chunk_redundancy_percent": 12.5, "link_failure_percent": 0.0, "packet_stall_percent": 3.0, "flow_time_avg_ms": 1.3, "bucket_time_avg_ms": 5.2, "step_time_avg_ms": 21.0, "job_time_avg_ms": 52.0},
    ]

    outputs = visualize_sweep_time_comparison(summary, out_dir=str(tmp_path), show=False)

    assert len(outputs) == 4
    assert all(Path(output).exists() for output in outputs)


def test_visualize_sweep_time_comparison_from_yaml_saves_four_files(tmp_path: Path) -> None:
    summary = [
        {"ok": True, "chunk_redundancy_percent": 0.0, "packet_stall_percent": 0.0, "flow_time_avg_ms": 1.0, "bucket_time_avg_ms": 5.0, "step_time_avg_ms": 20.0, "job_time_avg_ms": 50.0},
        {"ok": True, "chunk_redundancy_percent": 0.0, "packet_stall_percent": 3.0, "flow_time_avg_ms": 1.5, "bucket_time_avg_ms": 5.5, "step_time_avg_ms": 22.0, "job_time_avg_ms": 55.0},
        {"ok": True, "chunk_redundancy_percent": 12.5, "packet_stall_percent": 0.0, "flow_time_avg_ms": 0.9, "bucket_time_avg_ms": 4.8, "step_time_avg_ms": 18.5, "job_time_avg_ms": 49.0},
        {"ok": True, "chunk_redundancy_percent": 12.5, "packet_stall_percent": 3.0, "flow_time_avg_ms": 1.3, "bucket_time_avg_ms": 5.2, "step_time_avg_ms": 21.0, "job_time_avg_ms": 52.0},
    ]
    summary_path = tmp_path / "sweep_summary.yaml"
    summary_path.write_text(yaml.safe_dump(summary, sort_keys=False), encoding="utf-8")

    outputs = visualize_sweep_time_comparison_from_yaml(str(summary_path), out_dir=str(tmp_path), show=False)

    assert len(outputs) == 4
    assert all(Path(output).exists() for output in outputs)


