from __future__ import annotations

import logging
import random
import time
from typing import Any

from log_setup import configure_run_logging
from ..config.models import ExperimentSpec
from ..registry.topologies import build_network
from ..registry.workloads import build_scenario


# Too large for the log (one entry per flow).
_RUN_STATS_LOG_OMIT_KEYS = {"packet_stall_triggered_count_by_flow_id"}

# Network-level run statistics, grouped for the end-of-run summary. Keys not listed here
# still get logged, under "other" (or under the AI-factory summary for `ai_factory_*` keys).
_NETWORK_STAT_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("simulation", ("total run time (simulator time in seconds)",)),
    (
        "packets",
        (
            "total packets count",
            "delivered packets count",
            "delivered packets percentage",
            "dropped packets count",
            "dropped packets percentage",
            "max per flow drops",
            "hosts received counts",
        ),
    ),
    ("packet time (s)", ("avg packet time (s)", "min packet time (s)", "max packet time (s)")),
    ("route length (hops)", ("avg route length", "min route length", "max route length")),
    (
        "links",
        (
            "links min delivery time",
            "links max delivery time",
            "links average delivery time (2 directions)",
            "link average utilization percentage",
            "link_min_bytes_transmitted",
            "link_max_bytes_transmitted",
        ),
    ),
    ("queues", ("global_max_port_peak_queue_len (packets)", "avg_node_peak_egress_queue_len (packets)")),
    ("packet stalls", ("packet_stall_marked_count", "packet_stall_triggered_count")),
)

# Titles for the AI-factory statistics blocks.
_AI_FACTORY_STAT_TITLES = {
    "ai_factory_training_job_stats": "training job",
    "ai_factory_ring_flow_time_stats": "ring flow time (ms, sender injection to last useful packet at receiver)",
}


def _format_tree(value: dict[str, Any], indent: int = 1) -> list[str]:
    """One line per leaf value; nested mappings become an indented title line."""
    lines: list[str] = []
    pad = "  " * indent
    for key, item in value.items():
        if isinstance(item, dict) and item:
            lines.append(f"{pad}{key}:")
            lines.extend(_format_tree(item, indent + 1))
        else:
            lines.append(f"{pad}{key}: {item}")
    return lines


def _log_block(title: str, tree: dict[str, Any]) -> None:
    logging.info("%s:\n%s", title, "\n".join(_format_tree(tree)) if tree else "  (empty)")


def _log_experiment_parameters(spec: ExperimentSpec) -> None:
    """Log every resolved config value (after `extends`), grouped by config section."""
    _log_block(f"Experiment parameters (config: {spec.source_config_path})", spec.to_mapping())


def _log_results_summary(results: dict[str, Any]) -> None:
    run_statistics = {
        key: value
        for key, value in results.get("run statistics", {}).items()
        if key not in _RUN_STATS_LOG_OMIT_KEYS
    }

    network: dict[str, Any] = {"topology": dict(results.get("topology summary", {}))}
    for group, keys in _NETWORK_STAT_GROUPS:
        block = {key: run_statistics.pop(key) for key in keys if key in run_statistics}
        if block:
            network[group] = block

    ai_factory: dict[str, Any] = {}
    for key in [k for k in run_statistics if k.startswith("ai_factory_")]:
        ai_factory[_AI_FACTORY_STAT_TITLES.get(key, key)] = run_statistics.pop(key)

    if run_statistics:
        network["other"] = run_statistics

    _log_block("Results - network summary", network)
    if ai_factory:
        _log_block("Results - AI-factory summary", ai_factory)


def validate_experiment(spec: ExperimentSpec) -> dict[str, str]:
    topology_item = spec.topology.name
    workload_item = spec.workload.name
    build_network(spec)
    build_scenario(spec)
    summary = {
        "name": spec.display_name,
        "topology": topology_item,
        "workload": workload_item,
        "routing_mode": spec.routing.mode,
    }
    if spec.source_config_path:
        summary["source_config_path"] = spec.source_config_path
    return summary


def run_experiment(spec: ExperimentSpec) -> dict[str, Any]:
    if spec.run.seed is not None:
        random.seed(int(spec.run.seed))

    logfile_path = configure_run_logging(
        spec.display_name,
        log_dir=spec.run.log_dir,
        file_level=logging.DEBUG if spec.run.file_debug else logging.INFO,
        force=True,
        console_level=logging.INFO,
    )
    logging.info("Logging to console and file: %s", logfile_path)
    logging.info("Resolved experiment: %s", spec.display_name)
    _log_experiment_parameters(spec)

    network = build_network(spec)
    network.entities["deep_flow_chain_log"] = bool(spec.run.deep_flow_chain_log)
    scenario = build_scenario(spec)

    network.create(spec.run.visualize)
    network.assign_scenario(scenario)

    logging.info("Starting simulation")
    start = time.perf_counter()
    network.run()
    elapsed = time.perf_counter() - start
    logging.info("Simulation run time: %.3f seconds", elapsed)

    results = network.get_results()
    _log_results_summary(results)

    if spec.run.visualize:
        from visualization.experiment_visualizer import visualize_experiment_results

        visualize_experiment_results(
            [results],
            out_dir=spec.run.results_dir,
            show=spec.run.show_visualization_window,
        )

    return results


def build_network_and_scenario(spec: ExperimentSpec):
    return build_network(spec), build_scenario(spec)



