from __future__ import annotations

import csv
from pathlib import Path
import yaml

from ai_factory.core.entities import GradientBucketMetrics, FlowMetrics
from visualization.experiment_visualizer import (
    visualize_ai_factory_comm_distributions,
    visualize_summary_training_step_traffic_matrices,
    visualize_sweep_time_comparison,
    visualize_sweep_time_comparison_from_yaml,
)


def test_visualize_ai_factory_comm_distributions_saves_file(tmp_path: Path) -> None:
    bucket_metrics = [
        GradientBucketMetrics(
            job_id=1,
            step_id=0,
            phase_id=1,
            phase_name="gradient_sync",
            bucket_id=0,
            release_time=0.0,
            start_time=0.0,
            end_time=0.010,
            flow_count=8,
            transmitted_bytes=9000,
            useful_bytes=8000,
        ),
        GradientBucketMetrics(
            job_id=1,
            step_id=0,
            phase_id=1,
            phase_name="gradient_sync",
            bucket_id=1,
            release_time=0.010,
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
        redundancy_extra_packets=2,
        out_dir=str(tmp_path),
        show=False,
        link_failure_percent=None,
    )

    assert output is not None
    assert Path(output).exists()


def test_visualize_sweep_time_comparison_saves_aggregate_and_per_redundancy_files(tmp_path: Path) -> None:
    summary = [
        {"ok": True, "label": "run-a", "routing_mode": "ecmp", "flow_redundancy_extra_packets": 0, "link_failure_percent": 0.0, "packet_stall_percent": 0.0, "flow_time_avg_ms": 1.0, "flow_time_std_ms": 0.1, "flow_time_min_ms": 0.8, "flow_time_max_ms": 1.2, "ring_flow_time_avg_ms": 1.0, "ring_flow_time_std_ms": 0.1, "ring_flow_time_min_ms": 0.8, "ring_flow_time_max_ms": 1.2, "gradient_bucket_time_avg_ms": 5.0, "gradient_bucket_time_std_ms": 0.25, "gradient_bucket_time_min_ms": 4.5, "gradient_bucket_time_max_ms": 5.5, "training_step_time_avg_ms": 20.0, "training_step_time_std_ms": 0.8, "training_step_time_min_ms": 19.0, "training_step_time_max_ms": 21.0, "training_job_time_avg_ms": 50.0, "training_job_time_std_ms": 1.5, "training_job_time_min_ms": 48.0, "training_job_time_max_ms": 52.0, "total_packets": 1000, "packet_stall_marked_count": 12, "packet_stall_triggered_count": 10, "packet_stall_triggered_percent": 1.0, "avg_stalls_per_flow": 0.5, "max_stalls_per_flow": 2, "gradient_bucket_bottleneck_stalls": 4, "stalls_per_flow_histogram": {0: 40, 1: 8, 2: 2}, "total_redundant_packets": 50, "avg_redundant_packets_per_flow": 0.625, "avg_packets_per_ring_flow": 8.0, "avg_data_per_host_per_ring_bytes": 1024.0, "avg_data_per_collective_per_ring_bytes": 128.0, "avg_packets_in_ring_before_redundancy": 1.0, "avg_packets_in_ring_after_redundancy": 2.0, "packets_in_ring_flow_with_redundancy": 2.0},
        {"ok": True, "label": "run-b", "routing_mode": "ecmp", "flow_redundancy_extra_packets": 0, "link_failure_percent": 0.0, "packet_stall_percent": 3.0, "flow_time_avg_ms": 1.5, "flow_time_std_ms": 0.12, "flow_time_min_ms": 1.2, "flow_time_max_ms": 1.8, "ring_flow_time_avg_ms": 1.5, "ring_flow_time_std_ms": 0.12, "ring_flow_time_min_ms": 1.2, "ring_flow_time_max_ms": 1.8, "gradient_bucket_time_avg_ms": 5.5, "gradient_bucket_time_std_ms": 0.28, "gradient_bucket_time_min_ms": 5.0, "gradient_bucket_time_max_ms": 6.0, "training_step_time_avg_ms": 22.0, "training_step_time_std_ms": 1.0, "training_step_time_min_ms": 20.0, "training_step_time_max_ms": 24.0, "training_job_time_avg_ms": 55.0, "training_job_time_std_ms": 1.8, "training_job_time_min_ms": 53.0, "training_job_time_max_ms": 57.5, "total_packets": 1000, "packet_stall_marked_count": 18, "packet_stall_triggered_count": 15, "packet_stall_triggered_percent": 1.5, "avg_stalls_per_flow": 0.75, "max_stalls_per_flow": 3, "gradient_bucket_bottleneck_stalls": 6, "stalls_per_flow_histogram": {0: 35, 1: 11, 2: 3, 3: 1}, "total_redundant_packets": 50},
        {"ok": True, "label": "run-c", "routing_mode": "adaptive", "flow_redundancy_extra_packets": 2, "link_failure_percent": 0.0, "packet_stall_percent": 0.0, "flow_time_avg_ms": 0.9, "flow_time_std_ms": 0.08, "flow_time_min_ms": 0.7, "flow_time_max_ms": 1.1, "ring_flow_time_avg_ms": 0.9, "ring_flow_time_std_ms": 0.08, "ring_flow_time_min_ms": 0.7, "ring_flow_time_max_ms": 1.1, "gradient_bucket_time_avg_ms": 4.8, "gradient_bucket_time_std_ms": 0.22, "gradient_bucket_time_min_ms": 4.2, "gradient_bucket_time_max_ms": 5.4, "training_step_time_avg_ms": 18.5, "training_step_time_std_ms": 0.7, "training_step_time_min_ms": 17.5, "training_step_time_max_ms": 19.2, "training_job_time_avg_ms": 49.0, "training_job_time_std_ms": 1.3, "training_job_time_min_ms": 47.8, "training_job_time_max_ms": 50.7, "total_packets": 900, "packet_stall_marked_count": 8, "packet_stall_triggered_count": 5, "packet_stall_triggered_percent": 0.5555555556, "avg_stalls_per_flow": 0.3125, "max_stalls_per_flow": 1, "gradient_bucket_bottleneck_stalls": 2, "stalls_per_flow_histogram": {0: 44, 1: 6}, "total_redundant_packets": 113},
        {"ok": True, "label": "run-d", "routing_mode": "adaptive", "flow_redundancy_extra_packets": 2, "link_failure_percent": 0.0, "packet_stall_percent": 3.0, "flow_time_avg_ms": 1.3, "flow_time_std_ms": 0.11, "flow_time_min_ms": 1.0, "flow_time_max_ms": 1.6, "ring_flow_time_avg_ms": 1.3, "ring_flow_time_std_ms": 0.11, "ring_flow_time_min_ms": 1.0, "ring_flow_time_max_ms": 1.6, "gradient_bucket_time_avg_ms": 5.2, "gradient_bucket_time_std_ms": 0.24, "gradient_bucket_time_min_ms": 4.7, "gradient_bucket_time_max_ms": 5.7, "training_step_time_avg_ms": 21.0, "training_step_time_std_ms": 0.9, "training_step_time_min_ms": 19.8, "training_step_time_max_ms": 22.8, "training_job_time_avg_ms": 52.0, "training_job_time_std_ms": 1.6, "training_job_time_min_ms": 50.2, "training_job_time_max_ms": 54.3, "total_packets": 900, "packet_stall_marked_count": 16, "packet_stall_triggered_count": 12, "packet_stall_triggered_percent": 1.3333333333, "avg_stalls_per_flow": 0.75, "max_stalls_per_flow": 2, "gradient_bucket_bottleneck_stalls": 5, "stalls_per_flow_histogram": {0: 30, 1: 15, 2: 5}, "total_redundant_packets": 113},
    ]

    outputs = visualize_sweep_time_comparison(summary, out_dir=str(tmp_path), show=False, training_step_time_lower_zoom_percent=15.0, paper_style=False)

    assert len(outputs) == 21
    assert all(Path(output).exists() for output in outputs)
    # 8 aggregate plots: flow, ring flow, gradient bucket, training step, training step lower-15% zoom,
    # best training step, training job, slowdown heatmap.
    assert sum(Path(output).suffix == ".png" and "_redundancy_" not in Path(output).name for output in outputs) == 8
    assert any(Path(output).name.startswith("training_step_slowdown_heatmap_") for output in outputs)
    assert sum("training_step_time_vs_packet_stall_lower_15pct_" in Path(output).name for output in outputs) == 1
    assert sum("_redundancy_0pkt_" in Path(output).name for output in outputs) == 5
    assert sum("_redundancy_2pkt_" in Path(output).name for output in outputs) == 5
    # One aggregate ring flow time plot plus one per redundancy value.
    assert sum(Path(output).name.startswith("ring_flow_time_vs_") for output in outputs) == 3
    assert any("best_training_step_time_vs_" in Path(output).name for output in outputs)
    assert any("best_redundancy_vs_" in Path(output).name for output in outputs)
    csv_outputs = [output for output in outputs if output.endswith(".csv")]
    assert len(csv_outputs) == 2
    step_csv = [output for output in csv_outputs if "training_step_time_vs_" in Path(output).name]
    dist_csv = [output for output in csv_outputs if "stalls_distribution_vs_" in Path(output).name]
    assert len(step_csv) == 1
    assert len(dist_csv) == 1
    with open(step_csv[0], "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 4
    assert rows[0]["training_step_time_avg_ms"]
    assert rows[0]["training_step_time_min_ms"]
    assert rows[0]["training_step_time_max_ms"]
    assert rows[0]["flow_time_min_ms"]
    assert rows[0]["flow_time_max_ms"]
    assert rows[0]["gradient_bucket_time_min_ms"]
    assert rows[0]["gradient_bucket_time_max_ms"]
    assert rows[0]["total_packets"]
    assert rows[0]["packet_stall_marked_count"]
    assert rows[0]["packet_stall_triggered_count"]
    assert rows[0]["packet_stall_triggered_percent"]
    assert rows[0]["avg_stalls_per_flow"]
    assert rows[0]["max_stalls_per_flow"]
    assert rows[0]["gradient_bucket_bottleneck_stalls"]
    assert rows[0]["total_redundant_packets"]
    assert rows[0]["avg_redundant_packets_per_flow"]
    assert rows[0]["avg_packets_per_ring_flow"]
    assert rows[0]["avg_data_per_host_per_ring_bytes"]
    assert rows[0]["avg_data_per_collective_per_ring_bytes"]
    assert rows[0]["avg_packets_in_ring_before_redundancy"]
    assert rows[0]["avg_packets_in_ring_after_redundancy"]
    assert rows[0]["packets_in_ring_flow_with_redundancy"]
    with open(dist_csv[0], "r", encoding="utf-8", newline="") as fh:
        dist_rows = list(csv.DictReader(fh))
    assert len(dist_rows) > 0
    assert dist_rows[0]["stall_count"]
    assert dist_rows[0]["flow_count"]
    assert dist_rows[0]["flow_fraction_percent"]


def test_visualize_summary_training_step_traffic_matrices_saves_one_file_per_step(tmp_path: Path) -> None:
    summary = [
        {
            "ok": True,
            "label": "dp_small.yaml | routing.mode=adaptive",
            "routing_mode": "adaptive",
            "packet_stall_percent": 3.0,
            "flow_redundancy_extra_packets": 2,
            "training_step_traffic_matrices": [
                {
                    "step_id": 0,
                    "nodes": ["h1", "h2", "h10"],
                    "matrix_bytes": [
                        [0, 1200, 0],
                        [400, 0, 800],
                        [0, 0, 0],
                    ],
                },
                {
                    "step_id": 1,
                    "nodes": ["h2", "h1"],
                    "matrix_bytes": [
                        [0, 1024],
                        [512, 0],
                    ],
                },
            ],
        }
    ]

    outputs = visualize_summary_training_step_traffic_matrices(summary, out_dir=str(tmp_path), show=False)

    assert len(outputs) == 2
    assert all(Path(output).exists() for output in outputs)
    assert any("_step_000_" in Path(output).name for output in outputs)
    assert any("_step_001_" in Path(output).name for output in outputs)


def test_sweep_comparison_skips_ring_flow_plot_for_summaries_without_ring_keys(tmp_path: Path) -> None:
    # Summaries written before the ring flow time keys existed still plot everything else.
    summary = [
        {"ok": True, "label": f"run-{i}", "flow_redundancy_extra_packets": 0, "packet_stall_percent": stall, "flow_time_avg_ms": 1.0 + i, "flow_time_min_ms": 0.5, "flow_time_max_ms": 2.0 + i}
        for i, stall in enumerate([0.0, 3.0])
    ]

    outputs = visualize_sweep_time_comparison(summary, out_dir=str(tmp_path), show=False, training_step_time_lower_zoom_percent=0.0, paper_style=False)

    assert any(Path(output).name.startswith("flow_time_vs_") for output in outputs)
    assert not any(Path(output).name.startswith("ring_flow_time_vs_") for output in outputs)


def test_visualize_sweep_time_comparison_from_yaml_saves_plots_and_step_heatmaps(tmp_path: Path) -> None:
    summary = [
        {"ok": True, "label": "case-a", "flow_redundancy_extra_packets": 0, "packet_stall_percent": 0.0, "flow_time_avg_ms": 1.0, "gradient_bucket_time_avg_ms": 5.0, "training_step_time_avg_ms": 20.0, "training_job_time_avg_ms": 50.0, "max_per_flow_drops": 3, "stalls_per_flow_histogram": {0: 10, 1: 2}, "training_step_traffic_matrices": [{"step_id": 0, "nodes": ["h1", "h2"], "matrix_bytes": [[0, 100], [50, 0]]}]},
        {"ok": True, "label": "case-b", "flow_redundancy_extra_packets": 0, "packet_stall_percent": 3.0, "flow_time_avg_ms": 1.5, "gradient_bucket_time_avg_ms": 5.5, "training_step_time_avg_ms": 22.0, "training_job_time_avg_ms": 55.0, "max_per_flow_drops": 5, "stalls_per_flow_histogram": {0: 7, 1: 4, 2: 1}},
        {"ok": True, "label": "case-c", "flow_redundancy_extra_packets": 2, "packet_stall_percent": 0.0, "flow_time_avg_ms": 0.9, "gradient_bucket_time_avg_ms": 4.8, "training_step_time_avg_ms": 18.5, "training_job_time_avg_ms": 49.0, "max_per_flow_drops": 2, "stalls_per_flow_histogram": {0: 11, 1: 1}, "training_step_traffic_matrices": [{"step_id": 1, "nodes": ["h2", "h3"], "matrix_bytes": [[0, 200], [0, 0]]}]},
        {"ok": True, "label": "case-d", "flow_redundancy_extra_packets": 2, "packet_stall_percent": 3.0, "flow_time_avg_ms": 1.3, "gradient_bucket_time_avg_ms": 5.2, "training_step_time_avg_ms": 21.0, "training_job_time_avg_ms": 52.0, "max_per_flow_drops": 4, "stalls_per_flow_histogram": {0: 6, 1: 5, 2: 1}},
    ]
    summary_path = tmp_path / "sweep_summary.yaml"
    summary_path.write_text(yaml.safe_dump(summary, sort_keys=False), encoding="utf-8")

    outputs = visualize_sweep_time_comparison_from_yaml(str(summary_path), out_dir=str(tmp_path), show=False, training_step_time_lower_zoom_percent=15.0, include_training_step_traffic_matrices=True, paper_style=False)

    assert len(outputs) == 20
    assert all(Path(output).exists() for output in outputs)
    # 7 aggregate plots: 4 metric plots + training step lower-15% zoom + best-training-step-time view + slowdown heatmap.
    assert sum(Path(output).suffix == ".png" and "_redundancy_" not in Path(output).name and "training_step_traffic_matrix_" not in Path(output).name for output in outputs) == 7
    assert sum("training_step_time_vs_packet_stall_lower_15pct_" in Path(output).name for output in outputs) == 1
    # 2 training step traffic matrix heatmaps (one per row that has training_step_traffic_matrices data)
    assert sum("training_step_traffic_matrix_" in Path(output).name for output in outputs) == 2
    # 2 CSVs: step-time points and full stall distribution
    assert sum(Path(output).suffix == ".csv" for output in outputs) == 2





def test_paper_style_sweep_writes_fixed_name_pdfs_and_slowdown_heatmap(tmp_path: Path) -> None:
    times = {(0, 0.0): 10.0, (0, 1.0): 14.0, (0, 4.0): 20.0, (2, 0.0): 11.0, (2, 1.0): 11.5, (2, 4.0): 13.0}
    summary = [
        {
            "ok": True,
            "label": f"r{r}-p{p}",
            "flow_redundancy_extra_packets": r,
            "packet_stall_percent": p,
            "training_step_time_avg_ms": t,
            "training_step_time_std_ms": 0.5,
            "training_step_time_min_ms": t - 1.0,
            "training_step_time_max_ms": t + 1.0,
        }
        for (r, p), t in times.items()
    ]

    outputs = visualize_sweep_time_comparison(
        summary, out_dir=str(tmp_path), show=False, training_step_time_lower_zoom_percent=0.0, paper_style=True
    )

    for name in (
        "training_step_time_vs_packet_stall.pdf",
        "best_redundancy_vs_packet_stall.pdf",
        "training_step_slowdown_heatmap.pdf",
    ):
        assert (tmp_path / name).exists(), name
    assert all(Path(output).exists() for output in outputs)


def _layout_summary(vary: dict[str, list]) -> list[dict]:
    """One successful row per combination of `vary`, labelled like a real sweep run."""
    from itertools import product

    rows = []
    for idx, combo in enumerate(product(*vary.values())):
        overrides = [f"{key}={value}" for key, value in zip(vary, combo)]
        rows.append(
            {
                "ok": True,
                "label": " | ".join(["cfg.yaml", *overrides]),
                "training_step_time_avg_ms": 10.0 + idx,
                "training_step_time_std_ms": 0.5,
            }
        )
    return rows


def test_layout_plot_writes_one_fixed_name_pdf_with_one_panel_per_split_value(tmp_path: Path) -> None:
    import matplotlib.pyplot as plt

    from sim.config.models import PlotLayout
    from visualization.experiment_visualizer import SWEEP_LAYOUT_PLOT_NAME, visualize_sweep_layout

    vary = {
        "stall_regime.packet_stall_percent": [0.1, 1, 4],
        "ai_workload.flow_redundancy_extra_packets": [0, 2, 8],
        "stall_regime.packet_stall_delay_ms": [0.5, 2],
    }
    layout = PlotLayout(
        split="stall_regime.packet_stall_percent",
        x="ai_workload.flow_redundancy_extra_packets",
        lines="stall_regime.packet_stall_delay_ms",
    )
    saved_figures: list = []
    original_savefig = plt.Figure.savefig

    def _record_savefig(fig, *args, **kwargs):
        saved_figures.append(fig)
        return original_savefig(fig, *args, **kwargs)

    plt.Figure.savefig = _record_savefig
    try:
        outputs = visualize_sweep_layout(
            _layout_summary(vary),
            vary=tuple((key, tuple(values)) for key, values in vary.items()),
            layout=layout,
            out_dir=str(tmp_path),
            show=False,
        )
    finally:
        plt.Figure.savefig = original_savefig

    assert outputs == [str(tmp_path / SWEEP_LAYOUT_PLOT_NAME)]
    assert sorted(path.name for path in tmp_path.iterdir()) == [SWEEP_LAYOUT_PLOT_NAME]
    axes = saved_figures[0].axes
    assert [ax.get_title() for ax in axes] == ["p = 0.1 %", "p = 1 %", "p = 4 %"]
    assert [line.get_label() for line in axes[0].get_lines()] == ["d = 0.5 ms", "d = 2 ms"]
    assert [tick.get_text() for tick in axes[0].get_xticklabels()] == ["0", "2", "8"]


def test_layout_plot_without_layout_or_matching_runs_writes_nothing(tmp_path: Path) -> None:
    from sim.config.models import PlotLayout
    from visualization.experiment_visualizer import visualize_sweep_layout

    vary = (("stall_regime.packet_stall_percent", (0, 1)), ("ai_workload.flow_redundancy_extra_packets", (0, 2)))
    layout = PlotLayout(split=None, x="stall_regime.packet_stall_percent", lines="ai_workload.flow_redundancy_extra_packets")

    assert visualize_sweep_layout([], vary=vary, layout=None, out_dir=str(tmp_path), show=False) == []
    assert visualize_sweep_layout([{"ok": True, "label": "ok"}], vary=vary, layout=layout, out_dir=str(tmp_path), show=False) == []
    assert list(tmp_path.iterdir()) == []
