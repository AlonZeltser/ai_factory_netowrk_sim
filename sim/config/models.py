from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


class ConfigError(ValueError):
    """Raised when a unified experiment configuration is invalid."""


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"Expected mapping at '{path}', got {type(value).__name__}")
    return dict(value)


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
    log_dir: str = "results/logs"
    results_dir: str = "results"

    @staticmethod
    def from_mapping(value: Any) -> "RunSpec":
        if value is None:
            return RunSpec()
        data = _require_mapping(value, "run")
        seed = data.get("seed")
        return RunSpec(
            seed=(int(seed) if seed is not None else None),
            file_debug=bool(data.get("file_debug", data.get("debug", False))),
            message_verbose=bool(data.get("message_verbose", False)),
            verbose_route=bool(data.get("verbose_route", False)),
            visualize=bool(data.get("visualize", False)),
            show_visualization_window=bool(data.get("show_visualization_window", False)),
            log_dir=str(data.get("log_dir", "results/logs")),
            results_dir=str(data.get("results_dir", "results")),
        )

    def to_mapping(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "file_debug": self.file_debug,
            "message_verbose": self.message_verbose,
            "verbose_route": self.verbose_route,
            "visualize": self.visualize,
            "show_visualization_window": self.show_visualization_window,
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
            return RoutingSpec()
        data = _require_mapping(value, "routing")
        return RoutingSpec(
            mode=str(data.get("mode", "ecmp")),
            ecmp_flowlet_n_packets=int(data.get("ecmp_flowlet_n_packets", data.get("flowlet_packets", 0))),
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



