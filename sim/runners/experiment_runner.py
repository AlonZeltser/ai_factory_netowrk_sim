from __future__ import annotations

import logging
import random
import time
from typing import Any

from log_setup import configure_run_logging
from ..config.models import ExperimentSpec
from ..registry.topologies import build_network
from ..registry.workloads import build_scenario


def _log_results_summary(results: dict[str, Any]) -> None:
    def _fmt_block(value: Any) -> str:
        return "\n".join(f"\t{k}: {v}" for k, v in value.items()) if isinstance(value, dict) and value else "(empty)"

    logging.info("Results summary - Topology:\n%s", _fmt_block(results.get("topology summary", {})))
    logging.info("Results summary - Parameters:\n%s", _fmt_block(results.get("parameters summary", {})))
    logging.info("Results summary - Run statistics:\n%s", _fmt_block(results.get("run statistics", {})))


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
    if spec.source_preset:
        summary["source_preset"] = spec.source_preset
    if spec.source_preset_path:
        summary["source_preset_path"] = spec.source_preset_path
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
    )
    logging.info("Logging to console and file: %s", logfile_path)
    logging.info("Resolved experiment: %s", spec.display_name)

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



