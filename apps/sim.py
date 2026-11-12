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

from sim.config.loader import dump_experiment_yaml, load_experiment_spec, load_sweep_spec, resolve_cli_path
from sim.config.models import ConfigError, SweepSpec
from sim.registry.topologies import build_network
from sim.runners.sweep_executor import write_sweep_summary
from sim.runners.deep_flow_log import write_sweep_deep_flow_logs
from sim.runners.experiment_runner import run_experiment, validate_experiment
from sim.runners.gantt_export import check_gantt_export_ready, export_gantt_pdfs
from sim.runners.sweep_runner import build_sweep_inputs, run_sweep
from visualization.experiment_visualizer import (
    visualize_summary_training_step_traffic_matrices,
    visualize_sweep_time_comparison,
    standard_plot_merged_keys,
    visualize_sweep_layout,
    visualize_sweep_time_comparison_from_yaml,
)


_CONSOLE_SUMMARY_OMIT_KEYS = {"packet_stall_triggered_count_by_flow_id", "deep_flow_chain_diagnostics"}


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

    run_p = sub.add_parser("run", help="Run one experiment")
    run_p.add_argument("--config", required=True, help="Path to an experiment YAML file, e.g. experiments/dp_single_bucket.yaml")

    validate_p = sub.add_parser("validate", help="Validate and print the resolved experiment and its sweep plan")
    validate_p.add_argument("--config", required=True, help="Path to an experiment YAML file, e.g. experiments/dp_single_bucket.yaml")

    sweep_p = sub.add_parser(
        "sweep",
        help="Run every combination of the config's sweep.vary values in parallel; all settings come from the config's sweep section",
    )
    sweep_p.add_argument("--config", required=True, help="Path to an experiment YAML file with a sweep section")

    list_p = sub.add_parser("list", help="List supported routing modes")
    list_p.add_argument("target", choices=["routing"])

    plot_summary_p = sub.add_parser("plot-summary", help="Generate aggregate comparison plots from an existing sweep summary YAML")
    plot_summary_p.add_argument("--summary", required=True, help="Path to a sweep summary YAML file")
    plot_summary_p.add_argument(
        "--config",
        required=True,
        help="Experiment YAML whose sweep section sets the plot settings (lower_zoom_percent, show_visualization_window, paper_style)",
    )
    plot_summary_p.add_argument("--out-dir", required=True, help="Directory for generated plot files")
    return parser


def _load_from_args(args: argparse.Namespace):
    return load_experiment_spec(config_path=args.config, overrides=[])


def _cmd_list(target: str) -> int:
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
        _check_gantt_settings(args.config, sweep)
    return 0


def _require_sweep_spec(config_path: str) -> SweepSpec:
    sweep = load_sweep_spec(config_path)
    if sweep is None:
        raise ConfigError(f"Config has no 'sweep' section: {config_path}")
    return sweep


def _check_gantt_settings(config_path: str, sweep: SweepSpec) -> None:
    """sweep.gantt_pdfs draws from the chain logs, so every run must write them."""
    if not sweep.gantt_pdfs:
        return
    for item in build_sweep_inputs(config_path=config_path, sweep=sweep):
        spec = load_experiment_spec(config_path=item.config_path, overrides=list(item.overrides))
        if not spec.run.deep_flow_chain_log:
            raise ConfigError(f"sweep.gantt_pdfs needs deep_flow_chain_log: true (run {item.label!r} has false)")


def _cmd_run(args: argparse.Namespace) -> int:
    spec = _load_from_args(args)
    results = run_experiment(spec)
    stats = results.get("run statistics", {})
    delivered = stats.get("delivered packets count")
    dropped = stats.get("dropped packets count")
    total = stats.get("total packets count")
    print(f"Run complete: packets total={total}, delivered={delivered}, dropped={dropped}")
    return 0


def _cmd_sweep(args: argparse.Namespace) -> int:
    sweep = _require_sweep_spec(args.config)
    _check_gantt_settings(args.config, sweep)
    if sweep.gantt_pdfs:
        check_gantt_export_ready()
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
    output_path = write_sweep_summary(summary, sweep.summary_out)
    print(f"Wrote sweep summary to {output_path}")
    sweep_out_dir = output_path.parent
    deep_log_paths = write_sweep_deep_flow_logs(summary, out_dir=str(sweep_out_dir / "deep_flow_chain_logs"))
    for path in deep_log_paths:
        print(f"Wrote deep flow chain log to {path}")
    if sweep.gantt_pdfs:
        gantt_paths = export_gantt_pdfs(
            summary,
            sweep=sweep,
            chain_log_root=sweep_out_dir / "deep_flow_chain_logs",
            out_dir=sweep_out_dir / "gantt_pdfs",
        )
        print(f"Wrote {len(gantt_paths)} Gantt PDFs to {sweep_out_dir / 'gantt_pdfs'}")
    if sweep.visualize_summary or sweep.plot_ring_heatmaps:
        out_dir = str(sweep_out_dir)
        paths: list[str] = []
        if sweep.visualize_summary:
            if not _standard_plots_would_merge(sweep):
                paths.extend(
                    visualize_sweep_time_comparison(
                        summary,
                        out_dir=out_dir,
                        show=sweep.show_visualization_window,
                        training_step_time_lower_zoom_percent=sweep.lower_zoom_percent,
                        paper_style=sweep.paper_style,
                    )
                )
            paths.extend(
                visualize_sweep_layout(
                    summary,
                    vary=sweep.vary,
                    layout=sweep.plot_layout,
                    out_dir=out_dir,
                    show=sweep.show_visualization_window,
                    lower_zoom_percent=sweep.lower_zoom_percent,
                )
            )
        if sweep.plot_ring_heatmaps:
            paths.extend(visualize_summary_training_step_traffic_matrices(summary, out_dir=out_dir, show=sweep.show_visualization_window))
        for path in paths:
            print(f"Wrote comparison plot to {path}")
    return 0 if all(item.get("ok") for item in summary) else 1


def _standard_plots_would_merge(sweep: SweepSpec) -> bool:
    """True (after printing why) when the sweep varies a key the standard comparison plots do not group by."""
    merged = standard_plot_merged_keys(sweep.vary)
    if merged:
        print(
            "Skipped the standard comparison plots: they group runs only by redundancy and the stall "
            f"(or link failure) percent, so runs that differ in {', '.join(merged)} would be merged"
        )
    return bool(merged)


def _cmd_plot_summary(args: argparse.Namespace) -> int:
    sweep = _require_sweep_spec(args.config)
    if _standard_plots_would_merge(sweep):
        return 1
    summary_path = resolve_cli_path(args.summary)
    paths = visualize_sweep_time_comparison_from_yaml(
        str(summary_path),
        out_dir=str(resolve_cli_path(args.out_dir)),
        show=sweep.show_visualization_window,
        training_step_time_lower_zoom_percent=sweep.lower_zoom_percent,
        include_training_step_traffic_matrices=True,
        paper_style=sweep.paper_style,
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


