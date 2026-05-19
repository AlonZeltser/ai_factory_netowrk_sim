import datetime
import logging
import os
from typing import Any, Dict, List, Optional, Tuple


def visualize_send_timeline(
    packet_timeline: List[Tuple[float, int]],
    total_time: float,
    routing_mode: str = "",
    link_failure_percent: float | None = None,
    out_dir: str = "results",
    num_bins: int = 200,
    show: bool = False,
) -> Optional[str]:
    """Create a histogram showing the distribution of sends over the simulation timeline.

    This visualization shows how messaging activity is distributed across time,
    highlighting bursts and uneven distribution patterns.

    Args:
        packet_timeline: list of (birth_time, size_bytes) tuples for each packet
        total_time: total simulation time in seconds
        routing_mode: routing mode string for the title (e.g., 'ecmp', 'adaptive')
        out_dir: output directory for the PNG file
        num_bins: number of time bins for the histogram

    Returns:
        Path to saved file, or None if visualization failed.
    """
    if not packet_timeline:
        logging.warning("No packet timeline data to visualize")
        return None

    try:
        import matplotlib
        if not show:
            matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        logging.warning("matplotlib not available, skipping timeline visualization")
        return None

    try:
        # Extract times and sizes
        times = np.array([t for t, _ in packet_timeline])
        sizes = np.array([s for _, s in packet_timeline])

        # Create time bins
        if total_time <= 0:
            total_time = max(times) if len(times) > 0 else 1.0
        bin_edges = np.linspace(0, total_time, num_bins + 1)

        # Calculate bytes sent per bin
        bytes_per_bin = np.zeros(num_bins)
        packets_per_bin = np.zeros(num_bins)
        for t, s in packet_timeline:
            bin_idx = min(int(t / total_time * num_bins), num_bins - 1)
            bytes_per_bin[bin_idx] += s
            packets_per_bin[bin_idx] += 1

        # Convert to MB for readability
        mb_per_bin = bytes_per_bin / (1024 * 1024)

        # Create figure with two subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

        # Time axis in microseconds for better readability
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2 * 1e6  # convert to µs
        bin_width = (bin_edges[1] - bin_edges[0]) * 1e6

        title_parts = ["Messaging Distribution Over Time"]
        if routing_mode:
            title_parts.append(routing_mode.upper())
        if link_failure_percent is not None:
            title_parts.append(f"link failure={float(link_failure_percent):.3f}%")

        # Top plot: Data volume (MB)
        colors1 = plt.cm.Blues(np.linspace(0.4, 0.9, num_bins))
        ax1.bar(bin_centers, mb_per_bin, width=bin_width * 0.9, color=colors1, edgecolor='navy', linewidth=0.5)
        ax1.set_ylabel('Data Sent (MB)', fontsize=11)
        ax1.set_title(" | ".join(title_parts), fontsize=14, fontweight='bold')
        ax1.grid(axis='y', alpha=0.3)

        # Add average line
        avg_mb = np.mean(mb_per_bin)
        ax1.axhline(y=avg_mb, color='red', linestyle='--', linewidth=1.5, label=f'Avg: {avg_mb:.3f} MB')
        ax1.legend(loc='upper right')

        # Bottom plot: Packet count
        colors2 = plt.cm.Greens(np.linspace(0.4, 0.9, num_bins))
        ax2.bar(bin_centers, packets_per_bin, width=bin_width * 0.9, color=colors2, edgecolor='darkgreen', linewidth=0.5)
        ax2.set_xlabel('Time (µs)', fontsize=11)
        ax2.set_ylabel('Packets Sent', fontsize=11)
        ax2.grid(axis='y', alpha=0.3)

        # Add average line
        avg_packets = np.mean(packets_per_bin)
        ax2.axhline(y=avg_packets, color='red', linestyle='--', linewidth=1.5, label=f'Avg: {avg_packets:.1f} packets')
        ax2.legend(loc='upper right')

        # Add statistics text
        total_mb = sum(mb_per_bin)
        total_packets = len(packet_timeline)
        max_mb = max(mb_per_bin)
        min_mb = min(mb_per_bin[mb_per_bin > 0]) if any(mb_per_bin > 0) else 0
        stats_text = (f"Total: {total_mb:.2f} MB | {total_packets:,} packets | "
                      f"Duration: {total_time*1e6:.2f} µs | Peak: {max_mb:.3f} MB/bin")
        fig.text(0.5, 0.02, stats_text, ha='center', fontsize=10, style='italic')

        plt.tight_layout()
        plt.subplots_adjust(bottom=0.1)

        # Save figure
        os.makedirs(out_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"send_timeline_{routing_mode}_{timestamp}.png" if routing_mode else f"send_timeline_{timestamp}.png"
        filepath = os.path.join(out_dir, filename)
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        if show:
            plt.show()
        else:
            plt.close(fig)

        logging.info(f"Send timeline graph saved to: {filepath}")
        return filepath

    except Exception as e:
        logging.exception(f"Failed to create send timeline visualization: {e}")
        return None


def _metric_attr(metric: Any, key: str, default: Any = None) -> Any:
    if isinstance(metric, dict):
        return metric.get(key, default)
    return getattr(metric, key, default)


def _ecdf_points(values: list[float]) -> tuple[list[float], list[float]]:
    if not values:
        return [], []
    xs = sorted(values)
    ys = [(i + 1) / len(xs) for i in range(len(xs))]
    return xs, ys


def visualize_ai_factory_comm_distributions(
    bucket_metrics: List[Any],
    flow_metrics: List[Any],
    *,
    routing_mode: str = "",
    link_failure_percent: float | None = None,
    redundancy_percent: float | None = None,
    out_dir: str = "results",
    show: bool = False,
) -> Optional[str]:
    """Visualize communication timing distributions for AI-factory workloads.

    Buckets are workload-level communication groups. Flows are the lower-level send units
    emitted inside a bucket; in the ring collectives they correspond to chunk-like neighbor sends.
    """
    if not bucket_metrics and not flow_metrics:
        logging.warning("No AI-factory communication metrics to visualize")
        return None

    try:
        import matplotlib
        if not show:
            matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        logging.warning("matplotlib not available, skipping AI-factory communication visualization")
        return None

    try:
        bucket_durations_ms = [
            (float(_metric_attr(m, "end_time", 0.0)) - float(_metric_attr(m, "start_time", 0.0))) * 1000.0
            for m in bucket_metrics
            if _metric_attr(m, "end_time", -1.0) is not None and float(_metric_attr(m, "end_time", -1.0)) >= 0.0
        ]
        flow_durations_ms = [
            (float(_metric_attr(m, "end_time", 0.0)) - float(_metric_attr(m, "start_time", 0.0))) * 1000.0
            for m in flow_metrics
            if _metric_attr(m, "end_time", -1.0) is not None and float(_metric_attr(m, "end_time", -1.0)) >= 0.0
        ]
        bucket_phase_names = [str(_metric_attr(m, "phase_name", "bucket")) for m in bucket_metrics]
        flow_useful_bytes = [int(_metric_attr(m, "useful_bytes", 0)) for m in flow_metrics]
        flow_transmitted_bytes = [int(_metric_attr(m, "transmitted_bytes", 0)) for m in flow_metrics]

        fig, axes = plt.subplots(2, 2, figsize=(13, 9))
        title_parts = ["AI-factory communication timing distribution"]
        if routing_mode:
            title_parts.append(f"routing={routing_mode}")
        if link_failure_percent is not None:
            title_parts.append(f"link failure={float(link_failure_percent):.3f}%")
        if redundancy_percent is not None:
            title_parts.append(f"redundancy={redundancy_percent:.3f}%")
        fig.suptitle(" | ".join(title_parts), fontsize=14, fontweight="bold")

        ax = axes[0, 0]
        if bucket_durations_ms:
            ax.hist(bucket_durations_ms, bins=min(30, max(8, len(bucket_durations_ms))), color="#4C78A8", edgecolor="navy", alpha=0.85)
            ax.set_xlabel("Bucket duration (ms)")
            ax.set_ylabel("Count")
            ax.set_title("Bucket completion durations")
            ax.grid(axis="y", alpha=0.3)
        else:
            ax.text(0.5, 0.5, "No bucket metrics", ha="center", va="center")
            ax.set_axis_off()

        ax = axes[0, 1]
        if bucket_durations_ms:
            unique_phases = []
            grouped: dict[str, list[float]] = {}
            for name, duration in zip(bucket_phase_names, bucket_durations_ms):
                if name not in grouped:
                    grouped[name] = []
                    unique_phases.append(name)
                grouped[name].append(duration)
            ax.boxplot([grouped[name] for name in unique_phases], tick_labels=unique_phases, patch_artist=True)
            ax.set_ylabel("Bucket duration (ms)")
            ax.set_title("Bucket durations by phase")
            ax.tick_params(axis="x", rotation=25)
            ax.grid(axis="y", alpha=0.3)
        else:
            ax.text(0.5, 0.5, "No bucket metrics", ha="center", va="center")
            ax.set_axis_off()

        ax = axes[1, 0]
        if flow_durations_ms:
            ax.hist(flow_durations_ms, bins=min(40, max(10, len(flow_durations_ms))), color="#59A14F", edgecolor="darkgreen", alpha=0.85)
            ax.set_xlabel("Chunk / flow duration (ms)")
            ax.set_ylabel("Count")
            ax.set_title("Chunk-like flow completion durations")
            ax.grid(axis="y", alpha=0.3)
        else:
            ax.text(0.5, 0.5, "No flow metrics", ha="center", va="center")
            ax.set_axis_off()

        ax = axes[1, 1]
        if flow_durations_ms:
            xs, ys = _ecdf_points(flow_durations_ms)
            ax.plot(xs, ys, color="#E15759", linewidth=2.0, label="flow duration ECDF")
            if any(tx > ux for tx, ux in zip(flow_transmitted_bytes, flow_useful_bytes)):
                avg_overhead = np.mean([
                    ((tx / ux) - 1.0) * 100.0
                    for tx, ux in zip(flow_transmitted_bytes, flow_useful_bytes)
                    if ux > 0
                ])
                ax.text(0.98, 0.02, f"avg redundancy overhead: {avg_overhead:.2f}%", transform=ax.transAxes, ha="right", va="bottom")
            ax.set_xlabel("Chunk / flow duration (ms)")
            ax.set_ylabel("ECDF")
            ax.set_ylim(0.0, 1.02)
            ax.set_title("Chunk / flow duration ECDF")
            ax.grid(alpha=0.3)
            ax.legend(loc="lower right")
        else:
            ax.text(0.5, 0.5, "No flow metrics", ha="center", va="center")
            ax.set_axis_off()

        fig.text(
            0.5,
            0.01,
            "Buckets are workload-level communication groups; chunk/flow timings are lower-level sends emitted inside those buckets.",
            ha="center",
            fontsize=10,
            style="italic",
        )
        plt.tight_layout(rect=(0, 0.03, 1, 0.95))

        os.makedirs(out_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ai_factory_comm_distribution_{routing_mode}_{timestamp}.png" if routing_mode else f"ai_factory_comm_distribution_{timestamp}.png"
        filepath = os.path.join(out_dir, filename)
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        if show:
            plt.show()
        else:
            plt.close(fig)

        logging.info(f"AI-factory communication distribution graph saved to: {filepath}")
        return filepath
    except Exception as e:
        logging.exception(f"Failed to create AI-factory communication visualization: {e}")
        return None


def _summary_float(row: Dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _summary_spread(
    row: Dict[str, Any],
    *,
    avg_key: str,
    std_key: str,
    min_key: str,
    max_key: str,
) -> tuple[float, float, str | None]:
    avg = _summary_float(row, avg_key)
    if avg is None:
        return 0.0, 0.0, None
    std = _summary_float(row, std_key)
    if std is not None and std > 0.0:
        return std, std, "std"
    min_v = _summary_float(row, min_key)
    max_v = _summary_float(row, max_key)
    if min_v is not None and max_v is not None:
        return max(0.0, avg - min_v), max(0.0, max_v - avg), "min-max"
    return 0.0, 0.0, None


def _save_or_show(fig, filepath: str, *, show: bool) -> None:
    fig.savefig(filepath, dpi=150, bbox_inches='tight')
    if show:
        import matplotlib.pyplot as plt
        plt.show()
    else:
        import matplotlib.pyplot as plt
        plt.close(fig)


def _choose_sweep_x_axis(rows: List[Dict[str, Any]]) -> tuple[str, str, str, str]:
    candidates = [
        ("packet_stall_percent", "Packet stall percent", "packet_stall", "packet stall"),
        ("link_failure_percent", "Link failure percent", "failure", "link failure"),
    ]
    for key, label, stem, title_suffix in candidates:
        values = {
            value
            for row in rows
            if (value := _summary_float(row, key)) is not None
        }
        if len(values) > 1:
            return key, label, stem, title_suffix
    return candidates[-1]


def visualize_sweep_time_comparison(
    summary: List[Dict[str, Any]],
    *,
    out_dir: str = "results",
    show: bool = False,
) -> list[str]:
    """Create comparison plots across the varying impairment percentage with one line per redundancy level."""
    rows = [row for row in summary if row.get("ok")]
    if not rows:
        logging.warning("No successful sweep rows available for comparison visualization")
        return []

    try:
        import matplotlib
        if not show:
            matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        logging.warning("matplotlib not available, skipping sweep comparison visualization")
        return []

    metrics = [
        {
            "avg": "flow_time_avg_ms",
            "std": "flow_time_std_ms",
            "min": "flow_time_min_ms",
            "max": "flow_time_max_ms",
            "title": "Flow time vs impairment",
            "ylabel": "Average flow time (ms)",
            "stem": "flow_time",
        },
        {
            "avg": "bucket_time_avg_ms",
            "std": "bucket_time_std_ms",
            "min": "bucket_time_min_ms",
            "max": "bucket_time_max_ms",
            "title": "Bucket time vs impairment",
            "ylabel": "Average bucket time (ms)",
            "stem": "bucket_time",
        },
        {
            "avg": "step_time_avg_ms",
            "std": "step_time_std_ms",
            "min": "step_time_min_ms",
            "max": "step_time_max_ms",
            "title": "Step time vs impairment",
            "ylabel": "Average step time (ms)",
            "stem": "step_time",
        },
        {
            "avg": "job_time_avg_ms",
            "std": "job_time_std_ms",
            "min": "job_time_min_ms",
            "max": "job_time_max_ms",
            "title": "Job time vs impairment",
            "ylabel": "Average job time (ms)",
            "stem": "job_time",
        },
    ]

    saved_paths: list[str] = []
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    x_key, x_label, file_suffix, title_suffix = _choose_sweep_x_axis(rows)

    for metric in metrics:
        grouped: dict[float, list[dict[str, float]]] = {}
        for row in rows:
            redundancy = _summary_float(row, "chunk_redundancy_percent")
            x_value = _summary_float(row, x_key)
            metric_value = _summary_float(row, metric["avg"])
            if redundancy is None or x_value is None or metric_value is None:
                continue
            yerr_low, yerr_high, spread_mode = _summary_spread(
                row,
                avg_key=metric["avg"],
                std_key=metric["std"],
                min_key=metric["min"],
                max_key=metric["max"],
            )
            grouped.setdefault(redundancy, []).append(
                {
                    "x": x_value,
                    "y": metric_value,
                    "yerr_low": yerr_low,
                    "yerr_high": yerr_high,
                    "spread_mode": spread_mode or "none",
                }
            )

        if not grouped:
            continue

        fig, ax = plt.subplots(figsize=(11, 7))
        
        # Distinct marker styles for color-blind accessibility
        markers = ['o', 's', '^', 'v', 'D', 'p', '*', 'h', '+', 'x', '<', '>', '|', '_']
        line_styles = ['-', '--', '-.', ':']
        colors_accessible = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        
        spread_suffix_global = ""
        all_modes = set()
        for redundancy in sorted(grouped):
            points = sorted(grouped[redundancy], key=lambda item: item["x"])
            all_modes.update(p["spread_mode"] for p in points if p["spread_mode"] != "none")
        
        if "std" in all_modes:
            spread_suffix_global = " (avg±std)"
        elif "min-max" in all_modes:
            spread_suffix_global = " (avg with min-max)"
        
        for idx, redundancy in enumerate(sorted(grouped)):
            points = sorted(grouped[redundancy], key=lambda item: item["x"])
            x_vals = [p["x"] for p in points]
            y_vals = [p["y"] for p in points]
            yerr_low = [p["yerr_low"] for p in points]
            yerr_high = [p["yerr_high"] for p in points]
            
            marker = markers[idx % len(markers)]
            linestyle = line_styles[idx % len(line_styles)]
            color = colors_accessible[idx % len(colors_accessible)]
            
            ax.errorbar(
                x_vals,
                y_vals,
                yerr=[yerr_low, yerr_high],
                marker=marker,
                markersize=10,
                linewidth=2.5,
                linestyle=linestyle,
                capsize=5,
                capthick=2,
                color=color,
                elinewidth=1.5,
                label=f"redundancy={redundancy:.3f}%",
            )

        ax.set_title(f"{metric['title'].replace('impairment', title_suffix)}{spread_suffix_global}", fontsize=14, fontweight='bold')
        ax.set_xlabel(x_label, fontsize=12)
        ax.set_ylabel(metric["ylabel"], fontsize=12)
        ax.grid(alpha=0.3, linestyle='--', linewidth=0.7)
        ax.legend(loc='best', fontsize=11, framealpha=0.95, edgecolor='black', fancybox=True)

        filepath = os.path.join(out_dir, f"{metric['stem']}_vs_{file_suffix}_{timestamp}.png")
        _save_or_show(fig, filepath, show=show)
        logging.info("Sweep comparison graph saved to: %s", filepath)
        saved_paths.append(filepath)

    return saved_paths


def visualize_experiment_results(results: List[Dict[str, Dict[str, Any]]],
                                 out_dir: str = "results",
                                 show: bool = False) -> None:
    """Visualize experiment results including send timeline distribution.

    Args:
        results: list of run-result dicts.
        out_dir: output directory for visualization files.
    """
    for result in results:
        packet_timeline = result.get('packet_timeline', [])
        bucket_metrics = result.get('ai_factory_bucket_metrics', [])
        flow_metrics = result.get('ai_factory_flow_metrics', [])
        params = result.get('parameters summary', {})
        stats = result.get('run statistics', {})
        routing_mode = params.get('routing_mode', '')
        link_failure_percent = params.get('link_failure_percent')
        total_time = stats.get('total run time (simulator time in seconds)', 0)
        redundancy_percent = params.get('chunk_redundancy_percent')

        if packet_timeline:
            visualize_send_timeline(
                packet_timeline,
                total_time,
                routing_mode,
                link_failure_percent=(float(link_failure_percent) if link_failure_percent is not None else None),
                out_dir=out_dir,
                show=show,
            )
        if bucket_metrics or flow_metrics:
            visualize_ai_factory_comm_distributions(
                bucket_metrics,
                flow_metrics,
                routing_mode=routing_mode,
                link_failure_percent=(float(link_failure_percent) if link_failure_percent is not None else None),
                redundancy_percent=(float(redundancy_percent) if redundancy_percent is not None else None),
                out_dir=out_dir,
                show=show,
            )


__all__ = [
    "visualize_experiment_results",
    "visualize_send_timeline",
    "visualize_ai_factory_comm_distributions",
    "visualize_sweep_time_comparison",
]
