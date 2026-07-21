from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class MetaSpec:
    name: str = ""
    description: str = ""

    @staticmethod
    def from_mapping(value: Any) -> "MetaSpec":
        if value is None:
            return MetaSpec()
        data = _require_mapping(value, "meta")
        return MetaSpec(
            name=str(data.get("name", "") or ""),
            description=str(data.get("description", "") or ""),
        )

    def to_mapping(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.name:
            out["name"] = self.name
        if self.description:
            out["description"] = self.description
        return out


@dataclass(frozen=True)
class RunSpec:
    seed: int | None = None
    file_debug: bool = False
    message_verbose: bool = False
    verbose_route: bool = False
    visualize: bool = False
    show_visualization_window: bool = False
    store_packets: bool = False
    collect_packet_timeline: bool = False
    deep_flow_chain_log: bool = False
    log_dir: str = "results/logs"
    results_dir: str = "results"

    @staticmethod
    def from_mapping(value: Any) -> "RunSpec":
        if value is None:
            raise ConfigError("Missing required section 'run'")
        data = _require_mapping(value, "run")
        seed = data.get("seed")
        store_packets = bool(_require_key(data, "store_packets", "run"))
        collect_packet_timeline = bool(_require_key(data, "collect_packet_timeline", "run"))
        if collect_packet_timeline:
            # Timeline extraction requires packet storage to be enabled.
            store_packets = True
        # Support legacy alias 'debug' for 'file_debug'
        if "file_debug" not in data and "debug" not in data:
            raise ConfigError("Missing required key 'run.file_debug'")
        return RunSpec(
            seed=(int(seed) if seed is not None else None),
            file_debug=bool(data.get("file_debug", data.get("debug"))),
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
        out: dict[str, Any] = {
            "file_debug": self.file_debug,
            "message_verbose": self.message_verbose,
            "verbose_route": self.verbose_route,
            "visualize": self.visualize,
            "show_visualization_window": self.show_visualization_window,
            "store_packets": self.store_packets,
            "collect_packet_timeline": self.collect_packet_timeline,
            "deep_flow_chain_log": self.deep_flow_chain_log,
        }
        if self.seed is not None:
            out["seed"] = self.seed
        if self.log_dir != "results/logs":
            out["log_dir"] = self.log_dir
        if self.results_dir != "results":
            out["results_dir"] = self.results_dir
        return out


@dataclass(frozen=True)
class RoutingSpec:
    mode: str = "ecmp"
    ecmp_flowlet_n_packets: int = 0

    @staticmethod
    def from_mapping(value: Any) -> "RoutingSpec":
        if value is None:
            raise ConfigError("Missing required section 'routing'")
        data = _require_mapping(value, "routing")
        # Support legacy alias 'flowlet_packets' for 'ecmp_flowlet_n_packets'
        if "ecmp_flowlet_n_packets" not in data and "flowlet_packets" not in data:
            raise ConfigError("Missing required key 'routing.ecmp_flowlet_n_packets'")
        return RoutingSpec(
            mode=str(_require_key(data, "mode", "routing")),
            ecmp_flowlet_n_packets=int(data.get("ecmp_flowlet_n_packets", data.get("flowlet_packets"))),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "ecmp_flowlet_n_packets": self.ecmp_flowlet_n_packets,
        }


@dataclass(frozen=True)
class TopologySpec:
    name: str
    profile: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_mapping(value: Any) -> "TopologySpec":
        data = _require_mapping(value, "topology")
        name = data.get("family", data.get("name", data.get("type")))
        if not name:
            if "params" in data or "profile" in data:
                name = "clos"
        if not name:
            raise ConfigError("Missing required key 'topology.name'")
        profile = str(data.get("profile", "") or "")
        params = data.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, Mapping):
            raise ConfigError("Expected mapping at 'topology.params'")
        return TopologySpec(name=str(name), profile=profile, params=dict(params))

    def to_mapping(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "family": self.name,
            "params": dict(self.params),
        }
        if self.profile:
            out["profile"] = self.profile
        return out


@dataclass(frozen=True)
class WorkloadSpec:
    name: str
    profile: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_mapping(value: Any) -> "WorkloadSpec":
        data = _require_mapping(value, "workload")
        name = data.get("kind", data.get("name"))
        if not name:
            raise ConfigError("Missing required key 'workload.name'")
        profile = str(data.get("profile", "") or "")
        params = data.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, Mapping):
            raise ConfigError("Expected mapping at 'workload.params'")
        return WorkloadSpec(name=str(name), profile=profile, params=dict(params))

    def to_mapping(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": self.name,
            "params": dict(self.params),
        }
        if self.profile:
            out["profile"] = self.profile
        return out


@dataclass(frozen=True)
class ExperimentSpec:
    meta: MetaSpec
    run: RunSpec
    topology: TopologySpec
    routing: RoutingSpec
    workload: WorkloadSpec
    source_preset: str = ""
    source_preset_path: str = ""
    source_config_path: str = ""

    @staticmethod
    def from_mapping(value: Any) -> "ExperimentSpec":
        data = _require_mapping(value, "/")
        kind = data.get("kind")
        if kind not in (None, "experiment"):
            raise ConfigError(f"Unsupported config kind: {kind!r}. Expected 'experiment'.")
        return ExperimentSpec(
            meta=MetaSpec.from_mapping(data.get("meta")),
            run=RunSpec.from_mapping(data.get("run")),
            topology=TopologySpec.from_mapping(data.get("topology")),
            routing=RoutingSpec.from_mapping(data.get("routing")),
            workload=WorkloadSpec.from_mapping(data.get("workload")),
        )

    @property
    def display_name(self) -> str:
        if self.meta.name:
            return self.meta.name
        return f"{self.topology.name}.{self.workload.name}.{self.routing.mode}"

    def to_mapping(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": "experiment"}
        meta = self.meta.to_mapping()
        if meta:
            out["meta"] = meta
        out["run"] = self.run.to_mapping()
        out["topology"] = self.topology.to_mapping()
        out["routing"] = self.routing.to_mapping()
        out["workload"] = self.workload.to_mapping()
        return out



