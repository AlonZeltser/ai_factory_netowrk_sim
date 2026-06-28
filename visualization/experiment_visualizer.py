import csv
import datetime
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

import yaml


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
    redundancy_extra_packets: int | None = None,
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
        if redundancy_extra_packets is not None:
            title_parts.append(f"redundancy={int(redundancy_extra_packets)} pkt")
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
    std_key: str | None,
    min_key: str,
    max_key: str,
) -> dict[str, Any]:
    avg = _summary_float(row, avg_key)
    if avg is None:
        return {
            "std_low": 0.0,
            "std_high": 0.0,
            "min_value": None,
            "max_value": None,
            "has_std": False,
            "has_minmax": False,
        }
    std = _summary_float(row, std_key) if std_key else None
    min_v = _summary_float(row, min_key)
    max_v = _summary_float(row, max_key)
    has_std = std is not None and std > 0.0
    has_minmax = min_v is not None and max_v is not None
    return {
        "std_low": max(0.0, float(std)) if has_std else 0.0,
        "std_high": max(0.0, float(std)) if has_std else 0.0,
        "min_value": float(min_v) if has_minmax else None,
        "max_value": float(max_v) if has_minmax else None,
        "has_std": has_std,
        "has_minmax": has_minmax,
    }


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


def _natural_sort_key(value: str) -> tuple[Any, ...]:
    parts = re.split(r"(\d+)", str(value))
    return tuple(int(part) if part.isdigit() else part.lower() for part in parts)


def _normalize_summary_step_matrix(row: Dict[str, Any]) -> list[dict[str, Any]]:
    matrices = row.get("step_traffic_matrices")
    if not isinstance(matrices, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in matrices:
        if not isinstance(item, dict):
            continue
        nodes = item.get("nodes")
        matrix = item.get("matrix_bytes")
        step_id = item.get("step_id")
        if not isinstance(nodes, list) or not isinstance(matrix, list):
            continue
        try:
            step_id_int = int(step_id)
        except (TypeError, ValueError):
            continue
        node_labels = [str(node) for node in nodes]
        if not node_labels:
            continue
        if len(matrix) != len(node_labels):
            continue

        normalized_matrix: list[list[int]] = []
        valid = True
        for row_values in matrix:
            if not isinstance(row_values, list) or len(row_values) != len(node_labels):
                valid = False
                break
            try:
                normalized_matrix.append([max(0, int(value)) for value in row_values])
            except (TypeError, ValueError):
                valid = False
                break
        if not valid:
            continue

        normalized.append(
            {
                "step_id": step_id_int,
                "nodes": node_labels,
                "matrix_bytes": normalized_matrix,
            }
        )

    return sorted(normalized, key=lambda item: item["step_id"])


def visualize_summary_step_traffic_matrices(
    summary: List[Dict[str, Any]],
    *,
    out_dir: str = "results",
    show: bool = False,
) -> list[str]:
    """Create per-step traffic-matrix heatmaps for each successful summary row that carries step flow data."""
    rows = [row for row in summary if row.get("ok")]
    if not rows:
        return []

    try:
        import matplotlib
        if not show:
            matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        logging.warning("matplotlib not available, skipping summary traffic matrix visualization")
        return []

    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_paths: list[str] = []

    for row_idx, row in enumerate(rows):
        matrices = _normalize_summary_step_matrix(row)
        if not matrices:
            continue

        label = str(row.get("label") or f"summary_{row_idx}")
        safe_label = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("_") or f"summary_{row_idx}"
        routing_mode = row.get("routing_mode")
        redundancy = _summary_float(row, "chunk_redundancy_extra_packets")
        x_key, x_label, _, _ = _choose_sweep_x_axis([row])
        x_value = _summary_float(row, x_key)

        for matrix_info in matrices:
            nodes = sorted(matrix_info["nodes"], key=_natural_sort_key)
            source_nodes = matrix_info["nodes"]
            source_index = {node: idx for idx, node in enumerate(source_nodes)}
            display_matrix = [
                [matrix_info["matrix_bytes"][source_index[src]][source_index[dst]] for dst in nodes]
                for src in nodes
            ]
            data = np.array(display_matrix, dtype=float)
            fig_width = max(8.0, min(18.0, 2.0 + 0.6 * len(nodes)))
            fig_height = max(7.0, min(18.0, 2.5 + 0.6 * len(nodes)))
            fig, ax = plt.subplots(figsize=(fig_width, fig_height))

            vmax = float(data.max()) if data.size else 0.0
            im = ax.imshow(data, cmap="YlOrRd", vmin=0.0, vmax=vmax if vmax > 0 else 1.0)
            cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label("Transmitted bytes", rotation=90)

            ax.set_xticks(range(len(nodes)))
            ax.set_yticks(range(len(nodes)))
            ax.set_xticklabels(nodes, rotation=45, ha="right")
            ax.set_yticklabels(nodes)
            ax.set_xlabel("Destination host")
            ax.set_ylabel("Source host")

            title_parts = [f"Step {matrix_info['step_id']} traffic matrix"]
            if routing_mode:
                title_parts.append(f"routing={routing_mode}")
            if redundancy is not None:
                title_parts.append(f"redundancy={int(redundancy)} pkt")
            if x_value is not None:
                title_parts.append(f"{x_label}={x_value:.3f}")
            ax.set_title(" | ".join(title_parts), fontsize=13, fontweight="bold")

            max_value = int(data.max()) if data.size else 0
            text_threshold = max_value * 0.55 if max_value > 0 else 0
            for i in range(len(nodes)):
                for j in range(len(nodes)):
                    cell_value = int(data[i, j])
                    text_color = "white" if cell_value > text_threshold else "black"
                    ax.text(j, i, f"{cell_value:,}", ha="center", va="center", color=text_color, fontsize=8)

            fig.text(0.5, 0.01, f"run={label}", ha="center", fontsize=9, style="italic")
            plt.tight_layout(rect=(0, 0.03, 1, 0.97))

            filepath = os.path.join(
                out_dir,
                f"step_traffic_matrix_{safe_label}_step_{matrix_info['step_id']:03d}_{timestamp}.png",
            )
            _save_or_show(fig, filepath, show=show)
            logging.info("Summary traffic matrix graph saved to: %s", filepath)
            saved_paths.append(filepath)

    return saved_paths


def _plot_sweep_metric_series(
    ax,
    series: list[tuple[float, list[dict[str, float]]]],
    *,
    include_legend: bool,
) -> str:
    markers = ['o', 's', '^', 'v', 'D', 'p', '*', 'h', '+', 'x', '<', '>', '|', '_']
    line_styles = ['-', '--', '-.', ':']
    colors_accessible = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

    has_std = False
    has_minmax = False
    for _, points in series:
        has_std = has_std or any(bool(p.get("has_std")) for p in points)
        has_minmax = has_minmax or any(bool(p.get("has_minmax")) for p in points)

    spread_suffix = ""
    if has_std and has_minmax:
        spread_suffix = " (avg with ±std and min-max)"
    elif has_std:
        spread_suffix = " (avg with ±std)"
    elif has_minmax:
        spread_suffix = " (avg with min-max)"

    ax.set_facecolor('#EAEAF2')
    ax.grid(True, color='white', linewidth=1.1, alpha=0.95)
    for spine in ax.spines.values():
        spine.set_visible(False)

    for idx, (redundancy, points) in enumerate(series):
        x_vals = [p["x"] for p in points]
        y_vals = [p["y"] for p in points]
        color = colors_accessible[idx % len(colors_accessible)]

        if any(bool(p.get("has_minmax")) for p in points):
            min_vals = [p["min_value"] if p.get("has_minmax") else p["y"] for p in points]
            max_vals = [p["max_value"] if p.get("has_minmax") else p["y"] for p in points]
            ax.fill_between(
                x_vals,
                min_vals,
                max_vals,
                color=color,
                alpha=0.12,
                linewidth=0.0,
                zorder=1,
            )

        if any(bool(p.get("has_std")) for p in points):
            std_low = [p["y"] - p["std_low"] if p.get("has_std") else p["y"] for p in points]
            std_high = [p["y"] + p["std_high"] if p.get("has_std") else p["y"] for p in points]
            ax.fill_between(
                x_vals,
                std_low,
                std_high,
                color=color,
                alpha=0.24,
                linewidth=0.0,
                zorder=2,
            )

        ax.plot(
            x_vals,
            y_vals,
            marker=markers[idx % len(markers)],
            markersize=10,
            linewidth=2.5,
            linestyle=line_styles[idx % len(line_styles)],
            color=color,
            markerfacecolor='white',
            markeredgewidth=1.8,
            label=f"redundancy={int(redundancy)} pkt",
            zorder=3,
        )

    if include_legend:
        ax.legend(loc='best', fontsize=11, framealpha=0.95, edgecolor='black', fancybox=True)

    return spread_suffix


def _summary_stall_triggered_percent(row: Dict[str, Any]) -> float | None:
    # Preferred metric for packet-stall sweeps.
    stall_percent = _summary_float(row, "packet_stall_triggered_percent")
    if stall_percent is not None:
        return stall_percent
    stalls_triggered = _summary_float(row, "packet_stall_triggered_count")
    total_packets = _summary_float(row, "total_packets")
    if stalls_triggered is not None and total_packets is not None and total_packets > 0:
        return (stalls_triggered / total_packets) * 100.0

    # Backward-compatible fallback for older summaries that only contain drop fields.
    dropped_percent = _summary_float(row, "dropped_packets_percent")
    if dropped_percent is not None:
        return dropped_percent
    dropped_packets = _summary_float(row, "dropped_packets")
    if dropped_packets is None or total_packets is None or total_packets <= 0:
        return None
    return (dropped_packets / total_packets) * 100.0


def _normalize_histogram(raw_hist: Any) -> dict[int, int]:
    if not isinstance(raw_hist, dict):
        return {}
    out: dict[int, int] = {}
    for stall_count_raw, flow_count_raw in raw_hist.items():
        try:
            stall_count = int(stall_count_raw)
            flow_count = int(flow_count_raw)
        except (TypeError, ValueError):
            continue
        if stall_count < 0 or flow_count < 0:
            continue
        out[stall_count] = out.get(stall_count, 0) + flow_count
    return out


def _write_stall_distribution_csv(
    rows: List[Dict[str, Any]],
    *,
    out_dir: str,
    file_suffix: str,
    timestamp: str,
    x_key: str,
) -> str | None:
    flat_rows: list[dict[str, Any]] = []
    for row in rows:
        redundancy = _summary_float(row, "chunk_redundancy_extra_packets")
        x_value = _summary_float(row, x_key)
        if redundancy is None or x_value is None:
            continue
        histogram = _normalize_histogram(row.get("stalls_per_flow_histogram"))
        if not histogram:
            continue
        total_flows = int(sum(histogram.values()))
        if total_flows <= 0:
            continue
        for stall_count, flow_count in sorted(histogram.items()):
            flat_rows.append(
                {
                    "label": str(row.get("label", "")),
                    "routing_mode": str(row.get("routing_mode", "")),
                    "chunk_redundancy_extra_packets": redundancy,
                    "x_value": x_value,
                    "stall_count": stall_count,
                    "flow_count": flow_count,
                    "training_flow_count": total_flows,
                    "flow_fraction_percent": (float(flow_count) / float(total_flows)) * 100.0,
                }
            )

    if not flat_rows:
        return None

    csv_path = os.path.join(out_dir, f"stalls_distribution_vs_{file_suffix}_{timestamp}.csv")
    fieldnames = [
        "label",
        "routing_mode",
        "chunk_redundancy_extra_packets",
        "x_value",
        "stall_count",
        "flow_count",
        "training_flow_count",
        "flow_fraction_percent",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_rows)
    return csv_path


def _write_step_time_points_csv(
    grouped_rows: dict[float, list[dict[str, Any]]],
    *,
    out_dir: str,
    file_suffix: str,
    timestamp: str,
) -> str | None:
    flat_rows: list[dict[str, Any]] = []
    for redundancy, points in sorted(grouped_rows.items()):
        for point in sorted(points, key=lambda item: item["x"]):
            flat_rows.append(
                {
                    "label": str(point.get("label", "")),
                    "routing_mode": str(point.get("routing_mode", "")),
                    "chunk_redundancy_extra_packets": redundancy,
                    "x_value": point["x"],
                    "step_time_avg_ms": point["y"],
                    "step_time_min_ms": point.get("step_time_min_ms"),
                    "step_time_max_ms": point.get("step_time_max_ms"),
                    "flow_time_avg_ms": point.get("flow_time_avg_ms"),
                    "flow_time_min_ms": point.get("flow_time_min_ms"),
                    "flow_time_max_ms": point.get("flow_time_max_ms"),
                    "bucket_time_avg_ms": point.get("bucket_time_avg_ms"),
                    "bucket_time_min_ms": point.get("bucket_time_min_ms"),
                    "bucket_time_max_ms": point.get("bucket_time_max_ms"),
                    "total_packets": point.get("total_packets"),
                    "packet_stall_marked_count": point.get("packet_stall_marked_count"),
                    "packet_stall_triggered_count": point.get("packet_stall_triggered_count"),
                    "packet_stall_triggered_percent": point.get("packet_stall_triggered_percent"),
                    "avg_stalls_per_flow": point.get("avg_stalls_per_flow"),
                    "max_stalls_per_flow": point.get("max_stalls_per_flow"),
                    "bucket_bottleneck_stalls": point.get("bucket_bottleneck_stalls"),
                    "total_redundant_packets": point.get("total_redundant_packets"),
                    "total_redundant_bytes": point.get("total_redundant_bytes"),
                    "avg_redundant_packets_per_flow": point.get("avg_redundant_packets_per_flow"),
                    "avg_packets_per_ring_flow": point.get("avg_packets_per_ring_flow"),
                    "avg_data_per_host_per_ring_bytes": point.get("avg_data_per_host_per_ring_bytes"),
                    "avg_data_per_step_per_ring_bytes": point.get("avg_data_per_step_per_ring_bytes"),
                    "avg_packets_in_ring_before_redundancy": point.get("avg_packets_in_ring_before_redundancy"),
                    "avg_packets_in_ring_after_redundancy": point.get("avg_packets_in_ring_after_redundancy"),
                    "packets_in_ring_flow_with_redundancy": point.get("packets_in_ring_flow_with_redundancy"),
                }
            )

    if not flat_rows:
        return None

    csv_path = os.path.join(out_dir, f"step_time_vs_{file_suffix}_{timestamp}.csv")
    fieldnames = [
        "label",
        "routing_mode",
        "chunk_redundancy_extra_packets",
        "x_value",
        "step_time_avg_ms",
        "step_time_min_ms",
        "step_time_max_ms",
        "flow_time_avg_ms",
        "flow_time_min_ms",
        "flow_time_max_ms",
        "bucket_time_avg_ms",
        "bucket_time_min_ms",
        "bucket_time_max_ms",
        "total_packets",
        "packet_stall_marked_count",
        "packet_stall_triggered_count",
        "packet_stall_triggered_percent",
        "avg_stalls_per_flow",
        "max_stalls_per_flow",
        "bucket_bottleneck_stalls",
        "total_redundant_packets",
        "total_redundant_bytes",
        "avg_redundant_packets_per_flow",
        "avg_packets_per_ring_flow",
        "avg_data_per_host_per_ring_bytes",
        "avg_data_per_step_per_ring_bytes",
        "avg_packets_in_ring_before_redundancy",
        "avg_packets_in_ring_after_redundancy",
        "packets_in_ring_flow_with_redundancy",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_rows)
    return csv_path


def visualize_sweep_time_comparison(
    summary: List[Dict[str, Any]],
    *,
    out_dir: str = "results",
    show: bool = False,
) -> list[str]:
    """Create aggregate and per-redundancy comparison plots across the varying impairment percentage."""
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
        grouped_rows: dict[float, list[dict[str, Any]]] = {}
        for row in rows:
            redundancy = _summary_float(row, "chunk_redundancy_extra_packets")
            x_value = _summary_float(row, x_key)
            metric_value = _summary_float(row, metric["avg"])
            if redundancy is None or x_value is None or metric_value is None:
                continue
            spread = _summary_spread(
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
                    **spread,
                }
            )
            total_packets = _summary_float(row, "total_packets")
            packet_stall_marked_count = _summary_float(row, "packet_stall_marked_count")
            packet_stall_triggered_count = _summary_float(row, "packet_stall_triggered_count")
            packet_stall_triggered_percent = _summary_stall_triggered_percent(row)
            avg_stalls_per_flow = _summary_float(row, "avg_stalls_per_flow")
            max_stalls_per_flow = _summary_float(row, "max_stalls_per_flow")
            bucket_bottleneck_stalls = _summary_float(row, "bucket_bottleneck_stalls")
            flow_time_avg_ms = _summary_float(row, "flow_time_avg_ms")
            flow_time_min_ms = _summary_float(row, "flow_time_min_ms")
            flow_time_max_ms = _summary_float(row, "flow_time_max_ms")
            bucket_time_avg_ms = _summary_float(row, "bucket_time_avg_ms")
            bucket_time_min_ms = _summary_float(row, "bucket_time_min_ms")
            bucket_time_max_ms = _summary_float(row, "bucket_time_max_ms")
            total_redundant_packets = _summary_float(row, "total_redundant_packets")
            total_redundant_bytes = _summary_float(row, "total_redundant_bytes")
            avg_redundant_packets_per_flow = _summary_float(row, "avg_redundant_packets_per_flow")
            avg_packets_per_ring_flow = _summary_float(row, "avg_packets_per_ring_flow")
            avg_data_per_host_per_ring_bytes = _summary_float(row, "avg_data_per_host_per_ring_bytes")
            avg_data_per_step_per_ring_bytes = _summary_float(row, "avg_data_per_step_per_ring_bytes")
            avg_packets_in_ring_before_redundancy = _summary_float(row, "avg_packets_in_ring_before_redundancy")
            avg_packets_in_ring_after_redundancy = _summary_float(row, "avg_packets_in_ring_after_redundancy")
            packets_in_ring_flow_with_redundancy = _summary_float(row, "packets_in_ring_flow_with_redundancy")
            grouped_rows.setdefault(redundancy, []).append(
                {
                    "x": x_value,
                    "y": metric_value,
                    "label": row.get("label"),
                    "routing_mode": row.get("routing_mode"),
                    "step_time_min_ms": _summary_float(row, "step_time_min_ms"),
                    "step_time_max_ms": _summary_float(row, "step_time_max_ms"),
                    "flow_time_avg_ms": flow_time_avg_ms if flow_time_avg_ms is not None else 0.0,
                    "flow_time_min_ms": flow_time_min_ms if flow_time_min_ms is not None else 0.0,
                    "flow_time_max_ms": flow_time_max_ms if flow_time_max_ms is not None else 0.0,
                    "bucket_time_avg_ms": bucket_time_avg_ms if bucket_time_avg_ms is not None else 0.0,
                    "bucket_time_min_ms": bucket_time_min_ms if bucket_time_min_ms is not None else 0.0,
                    "bucket_time_max_ms": bucket_time_max_ms if bucket_time_max_ms is not None else 0.0,
                    "total_packets": total_packets if total_packets is not None else 0,
                    "packet_stall_marked_count": packet_stall_marked_count if packet_stall_marked_count is not None else 0,
                    "packet_stall_triggered_count": packet_stall_triggered_count if packet_stall_triggered_count is not None else 0,
                    "packet_stall_triggered_percent": packet_stall_triggered_percent if packet_stall_triggered_percent is not None else 0.0,
                    "avg_stalls_per_flow": avg_stalls_per_flow if avg_stalls_per_flow is not None else 0.0,
                    "max_stalls_per_flow": max_stalls_per_flow if max_stalls_per_flow is not None else 0,
                    "bucket_bottleneck_stalls": bucket_bottleneck_stalls if bucket_bottleneck_stalls is not None else 0,
                    "total_redundant_packets": total_redundant_packets if total_redundant_packets is not None else 0,
                    "total_redundant_bytes": total_redundant_bytes if total_redundant_bytes is not None else 0,
                    "avg_redundant_packets_per_flow": avg_redundant_packets_per_flow if avg_redundant_packets_per_flow is not None else 0.0,
                    "avg_packets_per_ring_flow": avg_packets_per_ring_flow if avg_packets_per_ring_flow is not None else 0.0,
                    "avg_data_per_host_per_ring_bytes": avg_data_per_host_per_ring_bytes if avg_data_per_host_per_ring_bytes is not None else 0.0,
                    "avg_data_per_step_per_ring_bytes": avg_data_per_step_per_ring_bytes if avg_data_per_step_per_ring_bytes is not None else 0.0,
                    "avg_packets_in_ring_before_redundancy": avg_packets_in_ring_before_redundancy if avg_packets_in_ring_before_redundancy is not None else 0.0,
                    "avg_packets_in_ring_after_redundancy": avg_packets_in_ring_after_redundancy if avg_packets_in_ring_after_redundancy is not None else 0.0,
                    "packets_in_ring_flow_with_redundancy": packets_in_ring_flow_with_redundancy if packets_in_ring_flow_with_redundancy is not None else 0.0,
                }
            )

        if not grouped:
            continue

        sorted_series = [
            (redundancy, sorted(points, key=lambda item: item["x"]))
            for redundancy, points in sorted(grouped.items())
        ]

        fig, ax = plt.subplots(figsize=(11, 7))
        spread_suffix_global = _plot_sweep_metric_series(ax, sorted_series, include_legend=True)

        ax.set_title(f"{metric['title'].replace('impairment', title_suffix)}{spread_suffix_global}", fontsize=14, fontweight='bold')
        ax.set_xlabel(x_label, fontsize=12)
        ax.set_ylabel(metric["ylabel"], fontsize=12)
        ax.grid(alpha=0.3, linestyle='--', linewidth=0.7)

        filepath = os.path.join(out_dir, f"{metric['stem']}_vs_{file_suffix}_{timestamp}.png")
        _save_or_show(fig, filepath, show=show)
        logging.info("Sweep comparison graph saved to: %s", filepath)
        saved_paths.append(filepath)

        for redundancy, points in sorted_series:
            fig_single, ax_single = plt.subplots(figsize=(11, 7))
            spread_suffix_single = _plot_sweep_metric_series(
                ax_single,
                [(redundancy, points)],
                include_legend=False,
            )
            ax_single.set_title(
                f"{metric['title'].replace('impairment', title_suffix)} | redundancy={int(redundancy)} pkt{spread_suffix_single}",
                fontsize=14,
                fontweight='bold',
            )
            ax_single.set_xlabel(x_label, fontsize=12)
            ax_single.set_ylabel(metric["ylabel"], fontsize=12)
            ax_single.grid(alpha=0.3, linestyle='--', linewidth=0.7)

            filepath_single = os.path.join(
                out_dir,
                f"{metric['stem']}_vs_{file_suffix}_redundancy_{int(redundancy)}pkt_{timestamp}.png",
            )
            _save_or_show(fig_single, filepath_single, show=show)
            logging.info("Sweep comparison graph saved to: %s", filepath_single)
            saved_paths.append(filepath_single)

        if metric["stem"] == "step_time":
            csv_path = _write_step_time_points_csv(
                grouped_rows,
                out_dir=out_dir,
                file_suffix=file_suffix,
                timestamp=timestamp,
            )
            if csv_path:
                logging.info("Sweep step-time values saved to: %s", csv_path)
                saved_paths.append(csv_path)

    dist_csv_path = _write_stall_distribution_csv(
        rows,
        out_dir=out_dir,
        file_suffix=file_suffix,
        timestamp=timestamp,
        x_key=x_key,
    )
    if dist_csv_path:
        logging.info("Sweep stall-distribution values saved to: %s", dist_csv_path)
        saved_paths.append(dist_csv_path)

    return saved_paths


def visualize_sweep_time_comparison_from_yaml(
    summary_yaml_path: str,
    *,
    out_dir: str = "results",
    show: bool = False,
) -> list[str]:
    """Load a sweep summary YAML file and create aggregate comparison plots and step traffic matrices."""
    path = Path(summary_yaml_path)
    if not path.is_absolute():
        path = path.resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Sweep summary YAML not found: {path}")

    summary = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(summary, list):
        raise ValueError(f"Sweep summary YAML must contain a top-level list, got: {type(summary).__name__}")
    if not all(isinstance(row, dict) for row in summary):
        raise ValueError("Sweep summary YAML list must contain mapping entries")

    return visualize_sweep_time_comparison(summary, out_dir=out_dir, show=show) + visualize_summary_step_traffic_matrices(summary, out_dir=out_dir, show=show)


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
        redundancy_extra_packets = params.get('chunk_redundancy_extra_packets')

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
                redundancy_extra_packets=(int(redundancy_extra_packets) if redundancy_extra_packets is not None else None),
                out_dir=out_dir,
                show=show,
            )


__all__ = [
    "visualize_experiment_results",
    "visualize_send_timeline",
    "visualize_ai_factory_comm_distributions",
    "visualize_sweep_time_comparison",
    "visualize_summary_step_traffic_matrices",
    "visualize_sweep_time_comparison_from_yaml",
]
