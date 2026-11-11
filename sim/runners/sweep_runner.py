from __future__ import annotations

from itertools import product
from typing import Any

from sim.config.loader import resolve_cli_path
from sim.config.models import SweepSpec
from sim.runners.sweep_executor import SweepInput, run_sweep_inputs


_LABEL_SEPARATOR = " | "


def format_override_value(value: Any) -> str:
    # Overrides are parsed back with yaml.safe_load, so booleans must be lowercase.
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_sweep_inputs(*, config_path: str, sweep: SweepSpec) -> list[SweepInput]:
    """One sweep input per combination of `sweep.vary` values, in file order."""
    # Workers get an absolute path so they do not depend on the current directory.
    config_file = str(resolve_cli_path(config_path))
    keys = [key for key, _ in sweep.vary]
    value_lists = [[format_override_value(v) for v in values] for _, values in sweep.vary]
    inputs: list[SweepInput] = []
    for combo in product(*value_lists):
        overrides = tuple(f"{key}={value}" for key, value in zip(keys, combo))
        inputs.append(
            SweepInput(
                label=_LABEL_SEPARATOR.join([config_path, *overrides]),
                config_path=config_file,
                overrides=overrides,
                sample_chain_log_steps=sweep.gantt_pdfs,
            )
        )
    return inputs


def label_vary_values(label: str) -> dict[str, str]:
    """The `key=value` overrides of a run label made by build_sweep_inputs, values as written in the label."""
    _config_path, *overrides = label.split(_LABEL_SEPARATOR)
    return dict(override.split("=", 1) for override in overrides)


def run_sweep(*, config_path: str, sweep: SweepSpec) -> list[dict[str, Any]]:
    return run_sweep_inputs(
        build_sweep_inputs(config_path=config_path, sweep=sweep),
        stop_on_error=sweep.stop_on_error,
        use_processes=True,
        max_processes=sweep.max_processes,
    )
