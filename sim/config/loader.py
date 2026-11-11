from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml

from .models import ConfigError, ExperimentSpec, SweepSpec


_REPO_ROOT = Path(__file__).resolve().parents[2]

# Prefix that anchors a path at the repository root, e.g. `repo:results/logs`.
REPO_PREFIX = "repo:"

# Config keys whose values are paths, as (section, key); section None means a top-level key.
# Inside a YAML file they are resolved relative to that file.
_PATH_KEYS: tuple[tuple[str | None, str], ...] = (
    (None, "log_dir"),
    (None, "results_dir"),
    ("sweep", "summary_out"),
)


def resolve_path(raw: str, *, base_dir: Path) -> Path:
    """Resolve a config or CLI path to an absolute path.

    - `repo:<rel>` is relative to the repository root.
    - An absolute path is kept as is.
    - Any other path is relative to `base_dir`.
    """
    if raw.startswith(REPO_PREFIX):
        return (_REPO_ROOT / raw[len(REPO_PREFIX):]).resolve()
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def resolve_cli_path(raw: str) -> Path:
    """Resolve a path typed on the command line (or given by a GUI) against the current directory."""
    if not raw:
        raise ConfigError("A path is required")
    return resolve_path(raw, base_dir=Path.cwd())


def _resolve_path_keys(data: dict[str, Any], *, base_dir: Path) -> None:
    for section, key in _PATH_KEYS:
        block = data if section is None else data.get(section)
        if not isinstance(block, Mapping):
            continue
        value = block.get(key)
        if not isinstance(value, str) or not value.strip():
            # Missing, empty or non-string values are reported by the model validation.
            continue
        if section is None:
            data[key] = str(resolve_path(value, base_dir=base_dir))
        else:
            block = dict(block)
            block[key] = str(resolve_path(value, base_dir=base_dir))
            data[section] = block


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise ConfigError(f"Expected mapping in YAML file: {path}")
    return dict(data)


def _load_yaml_with_extends(path: Path, *, seen: tuple[Path, ...]) -> dict[str, Any]:
    path = path.resolve()
    if path in seen:
        cycle = " -> ".join(str(p) for p in (*seen, path))
        raise ConfigError(f"Config extends cycle detected: {cycle}")

    data = _read_yaml(path)
    # Resolve this file's own paths now: after merging it is unknown which file a value came from.
    _resolve_path_keys(data, base_dir=path.parent)
    extends = data.pop("extends", None)
    if extends is None:
        return data

    refs = extends if isinstance(extends, list) else [extends]
    merged: dict[str, Any] = {}
    for ref in refs:
        if not isinstance(ref, str) or not ref.strip():
            raise ConfigError(f"Invalid extends reference in {path}: {ref!r}")
        ref_path = resolve_path(ref, base_dir=path.parent)
        if not ref_path.exists():
            raise FileNotFoundError(f"Extended config file not found: {ref_path} (referenced from {path})")
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

    config_file = resolve_cli_path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    return config_file, _load_yaml_with_extends(config_file, seen=())


def load_sweep_spec(config_path: str) -> SweepSpec | None:
    """Read the `sweep:` section of an experiment file (after `extends`); None when the file has none."""
    _, data = _load_config_file(config_path)
    if "sweep" not in data:
        return None
    return SweepSpec.from_mapping(data["sweep"])


def load_experiment_spec(
    *,
    config_path: str,
    overrides: list[str],
) -> ExperimentSpec:
    config_file, merged = _load_config_file(config_path)

    for override in overrides:
        _apply_override(merged, override)
    # A path set by an override is relative to the top-level config file, like a path written in it.
    _resolve_path_keys(merged, base_dir=config_file.parent)

    # The sweep plan is read separately by load_sweep_spec; a single run ignores it.
    merged.pop("sweep", None)
    return ExperimentSpec.from_mapping(merged, source_config_path=str(config_file))


def dump_experiment_yaml(spec: ExperimentSpec) -> str:
    return yaml.safe_dump(spec.to_mapping(), sort_keys=False, allow_unicode=True)




