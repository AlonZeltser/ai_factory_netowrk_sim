from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_repo_root_str = str(_REPO_ROOT)
# When launched as a script, sys.path[0] is usually the `apps/` directory, which also
# contains this file (`sim.py`). If that directory appears before the repository root,
# `import sim...` can recursively resolve back to `apps/sim.py` instead of the real
# `sim/` package directory. Always put the repository root first.
sys.path = [_repo_root_str] + [p for p in sys.path if p != _repo_root_str]

# When this file is launched directly from some IDE debugger configurations,
# a non-package module named `sim` may already exist in sys.modules.
# That breaks imports like `from sim.config ...` with:
#   ModuleNotFoundError: No module named 'sim.config'; 'sim' is not a package
_loaded_sim = sys.modules.get("sim")
if _loaded_sim is not None and not hasattr(_loaded_sim, "__path__"):
    del sys.modules["sim"]

from sim.config.loader import dump_experiment_yaml, load_experiment_spec, load_sweep_spec
from sim.config.models import ConfigError, SweepSpec
from sim.registry.topologies import build_network
from sim.registry.workloads import iter_workload_items
from sim.runners.batch_runner import collect_batch_inputs, run_batch, write_batch_summary
from sim.runners.deep_flow_log import write_sweep_deep_flow_logs
from sim.runners.experiment_runner import run_experiment, validate_experiment
from sim.runners.sweep_runner import build_sweep_inputs, run_sweep
from visualization.experiment_visualizer import (
    visualize_summary_training_step_traffic_matrices,
    visualize_sweep_time_comparison,
    visualize_sweep_time_comparison_from_yaml,
)


_CONSOLE_SUMMARY_OMIT_KEYS = {"packet_stall_triggered_count_by_flow_id"}


def _sanitize_for_console(value):
    if isinstance(value, dict):
        return {
            key: _sanitize_for_console(item)
            for key, item in value.items()
            if key not in _CONSOLE_SUMMARY_OMIT_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_for_console(item) for item in value]
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified simulator CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_config_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config", required=True, help="Path to an experiment YAML file, e.g. experiments/dp_single_bucket.yaml")
        p.add_argument("--set", dest="overrides", action="append", default=[], help="Override config values, e.g. routing.mode=adaptive")
        p.add_argument("--store-packets", action="store_true", default=False, help="Store packet objects for diagnostics (higher memory usage)")
        p.add_argument("--collect-packet-timeline", action="store_true", default=False, help="Collect packet timeline in results (implies --store-packets)")

    run_p = sub.add_parser("run", help="Run one experiment")
    add_config_options(run_p)

    validate_p = sub.add_parser("validate", help="Validate and print the resolved experiment and its sweep plan")
    add_config_options(validate_p)

    batch_p = sub.add_parser("batch", help="Run multiple experiment configs sequentially")
    batch_p.add_argument("--config", dest="configs", action="append", default=[], help="Config file to include in the batch (repeatable)")
    batch_p.add_argument("--directory", help="Directory containing .yaml/.yml experiment files")
    batch_p.add_argument("--summary-out", help="Optional YAML path for the batch summary")
    batch_p.add_argument("--stop-on-error", action="store_true", default=False, help="Stop immediately if any run fails")
    batch_p.add_argument("--visualize-summary", action="store_true", default=False, help="Generate aggregate comparison plots from the batch summary")
    batch_p.add_argument("--show-visualization-window", action="store_true", default=False, help="Open aggregate comparison plots in an interactive window")

    sweep_p = sub.add_parser(
        "sweep",
        help="Run every combination of the config's sweep.vary values in parallel; all settings come from the config's sweep section",
    )
    sweep_p.add_argument("--config", required=True, help="Path to an experiment YAML file with a sweep section")

    list_p = sub.add_parser("list", help="List supported workloads/routing modes")
    list_p.add_argument("target", choices=["workloads", "routing"])

    plot_summary_p = sub.add_parser("plot-summary", help="Generate aggregate comparison plots from an existing sweep/batch summary YAML")
    plot_summary_p.add_argument("--summary", required=True, help="Path to a sweep/batch summary YAML file")
    plot_summary_p.add_argument(
        "--config",
        required=True,
        help="Experiment YAML whose sweep section sets the plot settings (lower_zoom_percent, show_visualization_window)",
    )
    plot_summary_p.add_argument("--out-dir", help="Directory for generated plot files (defaults to summary parent or ./results)")
    return parser


def _load_from_args(args: argparse.Namespace):
    return load_experiment_spec(config_path=args.config, overrides=_effective_overrides(args))


def _effective_overrides(args: argparse.Namespace) -> list[str]:
    overrides = list(getattr(args, "overrides", []) or [])
    if getattr(args, "store_packets", False):
        overrides.append("run.store_packets=true")
    if getattr(args, "collect_packet_timeline", False):
        overrides.append("run.store_packets=true")
        overrides.append("run.collect_packet_timeline=true")
    return overrides


def _cmd_list(target: str) -> int:
    if target == "workloads":
        for item in iter_workload_items():
            print(f"{item.name:16} {item.description}")
        return 0
    if target == "routing":
        print("ecmp             Stable hash-based ECMP selection")
        print("adaptive         Queue-aware selection among equal-cost ports")
        print("flowlet          ECMP alias with flowlet-style rehashing via ecmp_flowlet_n_packets")
        return 0
    raise ConfigError(f"Unsupported list target: {target}")


def _cmd_validate(args: argparse.Namespace) -> int:
    spec = _load_from_args(args)
    summary = validate_experiment(spec)
    print("Validation OK")
    print(yaml.safe_dump(summary, sort_keys=False))
    print(dump_experiment_yaml(spec))
    sweep = load_sweep_spec(args.config)
    if sweep is None:
        print("No sweep plan (the config has no sweep section)")
    else:
        print(f"Sweep plan: {sweep.combination_count()} combinations")
        for key, values in sweep.vary:
            print(f"  {key}: {list(values)}")
    return 0


def _require_sweep_spec(config_path: str) -> SweepSpec:
    sweep = load_sweep_spec(config_path)
    if sweep is None:
        raise ConfigError(f"Config has no 'sweep' section: {config_path}")
    return sweep


def _cmd_run(args: argparse.Namespace) -> int:
    spec = _load_from_args(args)
    results = run_experiment(spec)
    stats = results.get("run statistics", {})
    delivered = stats.get("delivered packets count")
    dropped = stats.get("dropped packets count")
    total = stats.get("total packets count")
    print(f"Run complete: packets total={total}, delivered={delivered}, dropped={dropped}")
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    summary = run_batch(
        collect_batch_inputs(configs=args.configs, directory=args.directory),
        stop_on_error=args.stop_on_error,
        use_processes=False,
        max_processes=None,
    )
    print(yaml.safe_dump(_sanitize_for_console(summary), sort_keys=False))
    output_path = None
    if args.summary_out:
        output_path = write_batch_summary(summary, args.summary_out)
        print(f"Wrote batch summary to {output_path}")
    if args.visualize_summary:
        out_dir = str(output_path.parent if output_path is not None else (_REPO_ROOT / "results").resolve())
        paths = visualize_sweep_time_comparison(summary, out_dir=out_dir, show=args.show_visualization_window, training_step_time_lower_zoom_percent=15.0)
        paths.extend(visualize_summary_training_step_traffic_matrices(summary, out_dir=out_dir, show=args.show_visualization_window))
        for path in paths:
            print(f"Wrote comparison plot to {path}")
    return 0 if all(item.get("ok") for item in summary) else 1


def _cmd_sweep(args: argparse.Namespace) -> int:
    sweep = _require_sweep_spec(args.config)
    if sweep.plot_topology_once:
        first_input = build_sweep_inputs(config_path=args.config, sweep=sweep)[0]
        topo_spec = load_experiment_spec(
            config_path=first_input.config_path,
            overrides=list(first_input.overrides),
        )
        topo_network = build_network(topo_spec)
        topo_network.create(True)

    summary = run_sweep(config_path=args.config, sweep=sweep)
    print(yaml.safe_dump(_sanitize_for_console(summary), sort_keys=False))
    output_path = write_batch_summary(summary, sweep.summary_out)
    print(f"Wrote sweep summary to {output_path}")
    sweep_out_dir = output_path.parent
    deep_log_paths = write_sweep_deep_flow_logs(summary, out_dir=str(sweep_out_dir / "deep_flow_chain_logs"))
    for path in deep_log_paths:
        print(f"Wrote deep flow chain log to {path}")
    if sweep.visualize_summary or sweep.plot_ring_heatmaps:
        out_dir = str(sweep_out_dir)
        paths: list[str] = []
        if sweep.visualize_summary:
            paths.extend(
                visualize_sweep_time_comparison(
                    summary,
                    out_dir=out_dir,
                    show=sweep.show_visualization_window,
                    training_step_time_lower_zoom_percent=sweep.lower_zoom_percent,
                )
            )
        if sweep.plot_ring_heatmaps:
            paths.extend(visualize_summary_training_step_traffic_matrices(summary, out_dir=out_dir, show=sweep.show_visualization_window))
        for path in paths:
            print(f"Wrote comparison plot to {path}")
    return 0 if all(item.get("ok") for item in summary) else 1


def _cmd_plot_summary(args: argparse.Namespace) -> int:
    sweep = _require_sweep_spec(args.config)
    summary_path = Path(args.summary)
    if not summary_path.is_absolute():
        summary_path = (_REPO_ROOT / summary_path).resolve()
    out_dir = args.out_dir
    if not out_dir:
        out_dir = str(summary_path.parent if summary_path.exists() else (_REPO_ROOT / "results").resolve())
    paths = visualize_sweep_time_comparison_from_yaml(
        str(summary_path),
        out_dir=out_dir,
        show=sweep.show_visualization_window,
        training_step_time_lower_zoom_percent=sweep.lower_zoom_percent,
        include_training_step_traffic_matrices=True,
    )
    if not paths:
        print("No comparison plots were generated from the provided summary.")
        return 1
    for path in paths:
        print(f"Wrote comparison plot to {path}")
    return 0


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "list":
            return _cmd_list(args.target)
        if args.command == "validate":
            return _cmd_validate(args)
        if args.command == "run":
            return _cmd_run(args)
        if args.command == "batch":
            return _cmd_batch(args)
        if args.command == "sweep":
            return _cmd_sweep(args)
        if args.command == "plot-summary":
            return _cmd_plot_summary(args)
        raise ConfigError(f"Unsupported command: {args.command}")
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


