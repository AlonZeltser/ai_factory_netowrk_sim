from __future__ import annotations

from itertools import product
from typing import Any

from sim.config.models import SweepSpec
from sim.runners.sweep_executor import SweepInput, run_sweep_inputs


def _format_override_value(value: Any) -> str:
    # Overrides are parsed back with yaml.safe_load, so booleans must be lowercase.
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_sweep_inputs(*, config_path: str, sweep: SweepSpec) -> list[SweepInput]:
    """One sweep input per combination of `sweep.vary` values, in file order."""
    keys = [key for key, _ in sweep.vary]
    value_lists = [[_format_override_value(v) for v in values] for _, values in sweep.vary]
    inputs: list[SweepInput] = []
    for combo in product(*value_lists):
        overrides = tuple(f"{key}={value}" for key, value in zip(keys, combo))
        inputs.append(
            SweepInput(
                label=" | ".join([config_path, *overrides]),
                config_path=config_path,
                overrides=overrides,
            )
        )
    return inputs


def run_sweep(*, config_path: str, sweep: SweepSpec) -> list[dict[str, Any]]:
    return run_sweep_inputs(
        build_sweep_inputs(config_path=config_path, sweep=sweep),
        stop_on_error=sweep.stop_on_error,
        use_processes=True,
        max_processes=sweep.max_processes,
    )
