from __future__ import annotations

from itertools import product
from typing import Any

from sim.config.models import ConfigError
from sim.runners.batch_runner import BatchInput, run_batch


class SweepConfigError(ConfigError):
    pass


def parse_vary_spec(spec: str) -> tuple[str, list[str]]:
    if "=" not in spec:
        raise SweepConfigError(f"Sweep variation must have the form key=v1,v2,..., got: {spec!r}")
    key, raw_values = spec.split("=", 1)
    key = key.strip()
    values = [part.strip() for part in raw_values.split(",") if part.strip()]
    if not key or not values:
        raise SweepConfigError(f"Invalid sweep variation: {spec!r}")
    return key, values


def build_sweep_inputs(
    *,
    preset_name: str | None = None,
    config_path: str | None = None,
    base_overrides: list[str] | None = None,
    vary_specs: list[str] | None = None,
) -> list[BatchInput]:
    if not preset_name and not config_path:
        raise SweepConfigError("Sweep requires --preset or --config")
    parsed = [parse_vary_spec(spec) for spec in (vary_specs or [])]
    if not parsed:
        raise SweepConfigError("Sweep requires at least one --vary key=v1,v2 specification")

    keys = [key for key, _ in parsed]
    values_product = list(product(*[values for _, values in parsed]))
    inputs: list[BatchInput] = []
    static_overrides = tuple(base_overrides or [])
    for combo in values_product:
        vary_overrides = tuple(f"{key}={value}" for key, value in zip(keys, combo))
        overrides = static_overrides + vary_overrides
        label_parts = [preset_name or config_path or "sweep"] + [f"{key}={value}" for key, value in zip(keys, combo)]
        inputs.append(
            BatchInput(
                label=" | ".join(label_parts),
                preset_name=preset_name,
                config_path=config_path,
                overrides=overrides,
            )
        )
    return inputs


def run_sweep(
    *,
    preset_name: str | None = None,
    config_path: str | None = None,
    base_overrides: list[str] | None = None,
    vary_specs: list[str] | None = None,
    stop_on_error: bool = False,
    max_processes: int | None = None,
) -> list[dict[str, Any]]:
    return run_batch(
        build_sweep_inputs(
            preset_name=preset_name,
            config_path=config_path,
            base_overrides=base_overrides,
            vary_specs=vary_specs,
        ),
        stop_on_error=stop_on_error,
        use_processes=True,
        max_processes=max_processes,
    )


