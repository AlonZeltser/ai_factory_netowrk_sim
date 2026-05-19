from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml

from .models import ConfigError, ExperimentSpec
from ..registry.presets import get_preset_item


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
def _normalize_loaded_mapping(data: dict[str, Any], *, source_name: str | None = None) -> dict[str, Any]:
    if data.get("kind") == "experiment":
        return data

    topology = data.get("topology")
    workload = data.get("workload")
    if isinstance(topology, Mapping) and isinstance(workload, Mapping):
        return data

    raise ConfigError("Unsupported config format. Expected a unified experiment config.")


def load_experiment_spec(
    *,
    preset_name: str | None = None,
    config_path: str | None = None,
    overrides: list[str] | None = None,
) -> ExperimentSpec:
    if not preset_name and not config_path:
        raise ConfigError("Provide at least one of preset_name or config_path")

    merged: dict[str, Any] = {}
    preset_file_path = ""
    loaded_config_path = ""
    if preset_name:
        preset_item = get_preset_item(preset_name)
        preset_data = _load_yaml_with_extends(preset_item.file_path)
        preset_data["__source__"] = str(preset_item.file_path)
        merged = _normalize_loaded_mapping(preset_data, source_name=preset_item.name.replace("/", "-"))
        preset_file_path = str(preset_item.file_path)

    if config_path:
        config_file = Path(config_path)
        if not config_file.is_absolute():
            config_file = (_REPO_ROOT / config_file).resolve()
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")
        config_data = _load_yaml_with_extends(config_file)
        config_data["__source__"] = str(config_file)
        merged = _deep_merge(merged, _normalize_loaded_mapping(config_data, source_name=config_file.stem))
        loaded_config_path = str(config_file)

    for override in overrides or []:
        _apply_override(merged, override)

    merged.pop("__source__", None)
    spec = ExperimentSpec.from_mapping(merged)
    return ExperimentSpec(
        meta=spec.meta,
        run=spec.run,
        topology=spec.topology,
        routing=spec.routing,
        workload=spec.workload,
        source_preset=(preset_name or ""),
        source_preset_path=preset_file_path,
        source_config_path=loaded_config_path,
    )


def dump_experiment_yaml(spec: ExperimentSpec) -> str:
    return yaml.safe_dump(spec.to_mapping(), sort_keys=False, allow_unicode=True)




