from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml

from .models import ConfigError, ExperimentSpec, SweepSpec


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise ConfigError(f"Expected mapping in YAML file: {path}")
    return dict(data)


def _load_yaml_with_extends(path: Path, *, seen: tuple[Path, ...] = ()) -> dict[str, Any]:
    path = path.resolve()
    if path in seen:
        cycle = " -> ".join(str(p) for p in (*seen, path))
        raise ConfigError(f"Config extends cycle detected: {cycle}")

    data = _read_yaml(path)
    extends = data.pop("extends", None)
    if extends is None:
        return data

    refs = extends if isinstance(extends, list) else [extends]
    merged: dict[str, Any] = {}
    for ref in refs:
        if not isinstance(ref, str) or not ref.strip():
            raise ConfigError(f"Invalid extends reference in {path}: {ref!r}")
        ref_path = Path(ref)
        if not ref_path.is_absolute():
            ref_path = (path.parent / ref_path).resolve()
        if not ref_path.exists():
            raise FileNotFoundError(f"Extended config file not found: {ref_path}")
        merged = _deep_merge(merged, _load_yaml_with_extends(ref_path, seen=(*seen, path)))
    return _deep_merge(merged, data)


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(dict(merged[key]), dict(value))
        else:
            merged[key] = deepcopy(value)
    return merged


def _parse_override_value(raw: str) -> Any:
    try:
        return yaml.safe_load(raw)
    except Exception:
        return raw


def _apply_override(data: dict[str, Any], override: str) -> None:
    if "=" not in override:
        raise ConfigError(f"Override must have the form key=value, got: {override!r}")

    path, raw_value = override.split("=", 1)
    keys = [chunk.strip() for chunk in path.split(".") if chunk.strip()]
    if not keys:
        raise ConfigError(f"Override path is empty: {override!r}")

    value = _parse_override_value(raw_value)
    cursor: dict[str, Any] = data
    for key in keys[:-1]:
        next_value = cursor.get(key)
        if next_value is None:
            next_value = {}
            cursor[key] = next_value
        if not isinstance(next_value, dict):
            if not isinstance(next_value, Mapping):
                raise ConfigError(f"Cannot set nested override under non-mapping key '{key}'")
            next_value = dict(next_value)
            cursor[key] = next_value
        cursor = next_value
    cursor[keys[-1]] = value


def _load_config_file(config_path: str) -> tuple[Path, dict[str, Any]]:
    if not config_path:
        raise ConfigError("A config file path is required")

    config_file = Path(config_path)
    if not config_file.is_absolute():
        config_file = (_REPO_ROOT / config_file).resolve()
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    return config_file, _load_yaml_with_extends(config_file)


def load_sweep_spec(config_path: str) -> SweepSpec:
    """Read the optional `sweep:` section of an experiment file (after `extends`)."""
    _, data = _load_config_file(config_path)
    return SweepSpec.from_mapping(data.get("sweep"))


def load_experiment_spec(
    *,
    config_path: str,
    overrides: list[str] | None = None,
) -> ExperimentSpec:
    config_file, merged = _load_config_file(config_path)

    for override in overrides or []:
        _apply_override(merged, override)

    # The sweep plan is read separately by load_sweep_spec; a single run ignores it.
    merged.pop("sweep", None)
    return ExperimentSpec.from_mapping(merged, source_config_path=str(config_file))


def dump_experiment_yaml(spec: ExperimentSpec) -> str:
    return yaml.safe_dump(spec.to_mapping(), sort_keys=False, allow_unicode=True)




