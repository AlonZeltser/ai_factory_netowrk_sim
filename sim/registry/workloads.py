from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from ai_factory.scenarios.ai_factory_su_dp_heavy_scenario import AIFactorySUDpHeavyScenario
from ai_factory.scenarios.mice_flow_injector import MiceConfig
from network.scenarios.base import Scenario
from network.scenarios.none_scenario import NoneScenario
from ..config.models import ConfigError, ExperimentSpec, TopologySpec, WorkloadSpec
@dataclass(frozen=True)
class WorkloadRegistryItem:
    name: str
    description: str
    builder: Callable[[WorkloadSpec, TopologySpec], Scenario]
def _require_topology(topology: TopologySpec, *valid_names: str) -> None:
    if topology.name not in valid_names:
        valid = ", ".join(valid_names)
        raise ConfigError(f"Workload requires topology in {{{valid}}}, got {topology.name!r}")


def _require_no_profile(workload: WorkloadSpec) -> None:
    if str(workload.profile).strip():
        raise ConfigError(
            "workload.profile is no longer supported. Put workload defaults in YAML via extends and override workload.params directly."
        )


def _require_param(params: dict[str, Any], key: str) -> Any:
    if key not in params:
        raise ConfigError(f"Missing required key 'workload.params.{key}'")
    return params[key]


def _require_param_any(params: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in params:
            return params[key]
    aliases = " or ".join(f"'workload.params.{key}'" for key in keys)
    raise ConfigError(f"Missing required key {aliases}")


def _require_mice_param(mice: dict[str, object], key: str) -> Any:
    if key not in mice:
        raise ConfigError(f"Missing required key 'workload.params.mice.{key}'")
    return mice[key]


def _build_mice(params: dict[str, object], *, mtu_bytes: int) -> MiceConfig | None:
    mice = params.get("mice")
    if mice is None:
        return None
    if not isinstance(mice, dict):
        raise ConfigError("Expected mapping at 'workload.params.mice'")
    return MiceConfig(
        enabled=bool(_require_mice_param(mice, "enabled")),
        seed=int(_require_mice_param(mice, "seed")),
        start_delay_s=float(_require_mice_param(mice, "start_delay_s")),
        interarrival_s=float(_require_mice_param(mice, "interarrival_s")),
        min_packets=int(_require_mice_param(mice, "min_packets")),
        max_packets=int(_require_mice_param(mice, "max_packets")),
        # mtu_bytes is derived from topology params; optionally overridable in the mice config
        mtu_bytes=int(mice.get("mtu_bytes", mtu_bytes)),
        force_cross_rack=bool(_require_mice_param(mice, "force_cross_rack")),
    )
def _build_none(workload: WorkloadSpec, topology: TopologySpec) -> Scenario:
    return NoneScenario()
def _build_dp_heavy(workload: WorkloadSpec, topology: TopologySpec) -> Scenario:
    _require_topology(topology, "clos")
    _require_no_profile(workload)
    params = dict(workload.params)
    seed = int(_require_param(params, "seed"))
    mtu = int(topology.params.get("mtu", 4096))
    mice = _build_mice(params, mtu_bytes=mtu)
    return AIFactorySUDpHeavyScenario(
        collectives=int(_require_param_any(params, "collectives", "steps")),
        seed=seed,
        num_buckets=int(_require_param(params, "num_buckets")),
        bucket_bytes_per_participant=int(_require_param(params, "bucket_bytes_per_participant")),
        gap_us=float(_require_param(params, "gap_us")),
        t_fwd_bwd_ms=float(_require_param(params, "t_fwd_bwd_ms")),
        optimizer_ms=float(_require_param(params, "optimizer_ms")),
        mtu=mtu,
        chunk_redundancy_extra_packets=int(_require_param(params, "chunk_redundancy_extra_packets")),
        single_ring_only=bool(_require_param(params, "single_ring_only")),
        mice=mice,
    )

_REGISTRY: dict[str, WorkloadRegistryItem] = {
    "dp-heavy": WorkloadRegistryItem(
        name="dp-heavy",
        description="AI-factory DP-heavy workload for the AI scale-unit clos presets",
        builder=_build_dp_heavy,
    ),
    "none": WorkloadRegistryItem(
        name="none",
        description="Topology-only run with no traffic workload",
        builder=_build_none,
    ),
}
def iter_workload_items() -> Iterable[WorkloadRegistryItem]:
    return (_REGISTRY[name] for name in sorted(_REGISTRY))
def get_workload_item(name: str) -> WorkloadRegistryItem:
    key = str(name).strip().lower()
    item = _REGISTRY.get(key)
    if item is None:
        valid = ", ".join(sorted(_REGISTRY))
        raise ConfigError(f"Unknown workload '{name}'. Valid: {valid}")
    return item
def build_scenario(spec: ExperimentSpec) -> Scenario:
    item = get_workload_item(spec.workload.name)
    return item.builder(spec.workload, spec.topology)
