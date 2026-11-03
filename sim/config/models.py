from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class ConfigError(ValueError):
    """Raised when a unified experiment configuration is invalid."""


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"Expected mapping at '{path}', got {type(value).__name__}")
    return dict(value)


def _require_key(data: dict[str, Any], key: str, section: str) -> Any:
    if key not in data:
        raise ConfigError(f"Missing required key '{section}.{key}'")
    return data[key]


def reject_unknown_keys(data: Mapping[str, Any], allowed: tuple[str, ...], section: str) -> None:
    """Fail on keys the config section does not define, so typos and removed keys never pass silently."""
    unknown = sorted(str(key) for key in data if key not in allowed)
    if unknown:
        raise ConfigError(
            f"Unknown key(s) in '{section}': {', '.join(unknown)}. Allowed: {', '.join(sorted(allowed))}"
        )


# Keys each section accepts.
_EXPERIMENT_KEYS = ("kind", "meta", "run", "topology", "routing", "workload")
_META_KEYS = ("name", "description")
_RUN_KEYS = (
    "seed",
    "file_debug",
    "message_verbose",
    "verbose_route",
    "visualize",
    "show_visualization_window",
    "store_packets",
    "collect_packet_timeline",
    "deep_flow_chain_log",
    "log_dir",
    "results_dir",
)
_ROUTING_KEYS = ("mode", "ecmp_flowlet_n_packets")
_TOPOLOGY_KEYS = ("family", "params")
_WORKLOAD_KEYS = ("kind", "params")


def _require_section(data: dict[str, Any], key: str) -> dict[str, Any]:
    if key not in data:
        raise ConfigError(f"Missing required section '{key}'")
    return _require_mapping(data[key], key)


def _require_str(data: dict[str, Any], key: str, section: str, *, allow_empty: bool) -> str:
    value = _require_key(data, key, section)
    if not isinstance(value, str):
        raise ConfigError(f"'{section}.{key}' must be a string, got {value!r}")
    if not allow_empty and not value.strip():
        raise ConfigError(f"'{section}.{key}' must not be empty")
    return value


def _require_params(data: dict[str, Any], section: str) -> dict[str, Any]:
    return _require_mapping(_require_key(data, "params", section), f"{section}.params")


@dataclass(frozen=True)
class MetaSpec:
    name: str
    description: str

    @staticmethod
    def from_mapping(data: dict[str, Any]) -> "MetaSpec":
        reject_unknown_keys(data, _META_KEYS, "meta")
        return MetaSpec(
            name=_require_str(data, "name", "meta", allow_empty=False),
            description=_require_str(data, "description", "meta", allow_empty=True),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description}


@dataclass(frozen=True)
class RunSpec:
    # None means the global random generator is left unseeded (runs are not reproducible).
    seed: int | None
    file_debug: bool
    message_verbose: bool
    verbose_route: bool
    visualize: bool
    show_visualization_window: bool
    store_packets: bool
    collect_packet_timeline: bool
    deep_flow_chain_log: bool
    log_dir: str
    results_dir: str

    @staticmethod
    def from_mapping(data: dict[str, Any]) -> "RunSpec":
        reject_unknown_keys(data, _RUN_KEYS, "run")
        seed = _require_key(data, "seed", "run")
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise ConfigError(f"'run.seed' must be an integer or null, got {seed!r}")
        store_packets = bool(_require_key(data, "store_packets", "run"))
        collect_packet_timeline = bool(_require_key(data, "collect_packet_timeline", "run"))
        if collect_packet_timeline and not store_packets:
            raise ConfigError("'run.collect_packet_timeline: true' requires 'run.store_packets: true'")
        return RunSpec(
            seed=seed,
            file_debug=bool(_require_key(data, "file_debug", "run")),
            message_verbose=bool(_require_key(data, "message_verbose", "run")),
            verbose_route=bool(_require_key(data, "verbose_route", "run")),
            visualize=bool(_require_key(data, "visualize", "run")),
            show_visualization_window=bool(_require_key(data, "show_visualization_window", "run")),
            store_packets=store_packets,
            collect_packet_timeline=collect_packet_timeline,
            deep_flow_chain_log=bool(_require_key(data, "deep_flow_chain_log", "run")),
            log_dir=str(_require_key(data, "log_dir", "run")),
            results_dir=str(_require_key(data, "results_dir", "run")),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "file_debug": self.file_debug,
            "message_verbose": self.message_verbose,
            "verbose_route": self.verbose_route,
            "visualize": self.visualize,
            "show_visualization_window": self.show_visualization_window,
            "store_packets": self.store_packets,
            "collect_packet_timeline": self.collect_packet_timeline,
            "deep_flow_chain_log": self.deep_flow_chain_log,
            "log_dir": self.log_dir,
            "results_dir": self.results_dir,
        }


@dataclass(frozen=True)
class RoutingSpec:
    mode: str
    ecmp_flowlet_n_packets: int

    @staticmethod
    def from_mapping(data: dict[str, Any]) -> "RoutingSpec":
        reject_unknown_keys(data, _ROUTING_KEYS, "routing")
        return RoutingSpec(
            mode=str(_require_key(data, "mode", "routing")),
            ecmp_flowlet_n_packets=int(_require_key(data, "ecmp_flowlet_n_packets", "routing")),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "ecmp_flowlet_n_packets": self.ecmp_flowlet_n_packets,
        }


@dataclass(frozen=True)
class TopologySpec:
    # Topology family, from the `topology.family` key.
    name: str
    params: dict[str, Any]

    @staticmethod
    def from_mapping(data: dict[str, Any]) -> "TopologySpec":
        reject_unknown_keys(data, _TOPOLOGY_KEYS, "topology")
        return TopologySpec(
            name=_require_str(data, "family", "topology", allow_empty=False),
            params=_require_params(data, "topology"),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {"family": self.name, "params": dict(self.params)}


@dataclass(frozen=True)
class WorkloadSpec:
    # Workload kind, from the `workload.kind` key.
    name: str
    params: dict[str, Any]

    @staticmethod
    def from_mapping(data: dict[str, Any]) -> "WorkloadSpec":
        reject_unknown_keys(data, _WORKLOAD_KEYS, "workload")
        return WorkloadSpec(
            name=_require_str(data, "kind", "workload", allow_empty=False),
            params=_require_params(data, "workload"),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {"kind": self.name, "params": dict(self.params)}


@dataclass(frozen=True)
class ExperimentSpec:
    meta: MetaSpec
    run: RunSpec
    topology: TopologySpec
    routing: RoutingSpec
    workload: WorkloadSpec
    source_config_path: str

    @staticmethod
    def from_mapping(value: Any, *, source_config_path: str) -> "ExperimentSpec":
        data = _require_mapping(value, "/")
        reject_unknown_keys(data, _EXPERIMENT_KEYS, "/")
        kind = _require_key(data, "kind", "/")
        if kind != "experiment":
            raise ConfigError(f"Unsupported config kind: {kind!r}. Expected 'experiment'.")
        return ExperimentSpec(
            meta=MetaSpec.from_mapping(_require_section(data, "meta")),
            run=RunSpec.from_mapping(_require_section(data, "run")),
            topology=TopologySpec.from_mapping(_require_section(data, "topology")),
            routing=RoutingSpec.from_mapping(_require_section(data, "routing")),
            workload=WorkloadSpec.from_mapping(_require_section(data, "workload")),
            source_config_path=source_config_path,
        )

    @property
    def display_name(self) -> str:
        return self.meta.name

    def to_mapping(self) -> dict[str, Any]:
        return {
            "kind": "experiment",
            "meta": self.meta.to_mapping(),
            "run": self.run.to_mapping(),
            "topology": self.topology.to_mapping(),
            "routing": self.routing.to_mapping(),
            "workload": self.workload.to_mapping(),
        }


_SWEEP_KEYS = ("vary", "summary_out", "visualize_summary", "plot_ring_heatmaps")
_SCALAR_TYPES = (str, int, float, bool)


@dataclass(frozen=True)
class SweepSpec:
    """Optional `sweep:` section of an experiment file.

    `vary` maps a dotted config key to the list of values to try; the sweep runs
    every combination. The other fields mirror the matching `sweep` CLI flags.
    """

    vary: tuple[tuple[str, tuple[Any, ...]], ...] = ()
    summary_out: str = ""
    visualize_summary: bool = False
    plot_ring_heatmaps: bool = False

    @staticmethod
    def from_mapping(value: Any) -> "SweepSpec":
        if value is None:
            return SweepSpec()
        data = _require_mapping(value, "sweep")
        reject_unknown_keys(data, _SWEEP_KEYS, "sweep")

        vary_raw = data.get("vary") or {}
        vary_map = _require_mapping(vary_raw, "sweep.vary")
        vary: list[tuple[str, tuple[Any, ...]]] = []
        for key, values in vary_map.items():
            if not isinstance(key, str) or not key.strip():
                raise ConfigError(f"Invalid key in 'sweep.vary': {key!r}")
            if not isinstance(values, list) or not values:
                raise ConfigError(f"'sweep.vary.{key}' must be a non-empty list of values")
            for v in values:
                if not isinstance(v, _SCALAR_TYPES):
                    raise ConfigError(f"'sweep.vary.{key}' values must be plain scalars, got {v!r}")
            vary.append((key.strip(), tuple(values)))

        return SweepSpec(
            vary=tuple(vary),
            summary_out=str(data.get("summary_out") or ""),
            visualize_summary=bool(data.get("visualize_summary", False)),
            plot_ring_heatmaps=bool(data.get("plot_ring_heatmaps", False)),
        )

    def combination_count(self) -> int:
        count = 1
        for _, values in self.vary:
            count *= len(values)
        return count if self.vary else 0



