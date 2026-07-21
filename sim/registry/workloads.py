from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Iterable, cast
from ai_factory.scenarios.ai_factory_su_dp_heavy_scenario import AIFactorySUDpHeavyScenario
from ai_factory.scenarios.mice_flow_injector import MiceConfig
from ai_factory.scenarios.mixed_scenario import AllocationMode, MixedScenario, StagePlacementMode
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


def _allocation_mode(params: dict[str, object]) -> AllocationMode:
    raw = str(_require_param(params, "allocation_mode"))
    if raw not in {"rack_balanced", "contiguous"}:
        raise ConfigError("workload.params.allocation_mode must be 'rack_balanced' or 'contiguous'")
    return cast(AllocationMode, raw)


def _stage_placement_mode(params: dict[str, object]) -> StagePlacementMode:
    raw = str(_require_param(params, "stage_placement_mode"))
    if raw not in {"topology_aware", "topology_unaware"}:
        raise ConfigError("workload.params.stage_placement_mode must be 'topology_aware' or 'topology_unaware'")
    return cast(StagePlacementMode, raw)


def _build_mixed(workload: WorkloadSpec, topology: TopologySpec) -> Scenario:
    _require_topology(topology, "clos")
    _require_no_profile(workload)
    params = dict(workload.params)
    seed = int(_require_param(params, "seed"))
    mtu = int(topology.params.get("mtu", 4096))
    mice = _build_mice(params, mtu_bytes=mtu)
    jobs = _require_param(params, "jobs")
    if jobs is None:
        jobs = {}
    if not isinstance(jobs, dict):
        raise ConfigError("Expected mapping at 'workload.params.jobs'")
    tp_cfg = jobs.get("tp_heavy", {}) or {}
    pp_cfg = jobs.get("pp_dp", {}) or {}
    if not isinstance(tp_cfg, dict) or not isinstance(pp_cfg, dict):
        raise ConfigError("Expected mappings at 'workload.params.jobs.tp_heavy' and 'workload.params.jobs.pp_dp'")
    return MixedScenario(
        collectives=int(_require_param_any(params, "collectives", "steps")),
        tp_heavy_collectives=(int(tp_cfg["collectives"]) if "collectives" in tp_cfg else (int(tp_cfg["steps"]) if "steps" in tp_cfg else None)),
        pp_dp_collectives=(int(pp_cfg["collectives"]) if "collectives" in pp_cfg else (int(pp_cfg["steps"]) if "steps" in pp_cfg else None)),
        seed=seed,
        traffic_scale=float(_require_param(params, "traffic_scale")),
        chunk_redundancy_extra_packets=int(_require_param(params, "chunk_redundancy_extra_packets")),
        allocation_mode=_allocation_mode(params),
        stage_placement_mode=_stage_placement_mode(params),
        tp_heavy_fwd_compute_ms=float(_require_param(params, "tp_heavy_fwd_compute_ms")),
        tp_heavy_micro_collectives=int(_require_param(params, "tp_heavy_micro_collectives")),
        tp_heavy_micro_collective_bytes_per_participant=int(_require_param(params, "tp_heavy_micro_collective_bytes_per_participant")),
        tp_heavy_micro_compute_gap_ms=float(_require_param(params, "tp_heavy_micro_compute_gap_ms")),
        tp_heavy_final_sync_bytes_per_participant=int(_require_param(params, "tp_heavy_final_sync_bytes_per_participant")),
        tp_heavy_tail_compute_ms=float(_require_param(params, "tp_heavy_tail_compute_ms")),
        tp_heavy_gap_us=float(_require_param(params, "tp_heavy_gap_us")),
        pp_dp_microbatch_count=int(_require_param(params, "pp_dp_microbatch_count")),
        pp_dp_microbatch_gap_us=float(_require_param(params, "pp_dp_microbatch_gap_us")),
        pp_dp_activation_bytes_per_microbatch=int(_require_param(params, "pp_dp_activation_bytes_per_microbatch")),
        pp_dp_grad_bytes_per_microbatch=int(_require_param(params, "pp_dp_grad_bytes_per_microbatch")),
        pp_dp_dp_sync_bytes_per_participant=int(_require_param(params, "pp_dp_dp_sync_bytes_per_participant")),
        pp_dp_tail_compute_ms=float(_require_param(params, "pp_dp_tail_compute_ms")),
        record_first_collective_flow_signatures=bool(_require_param_any(params, "record_first_collective_flow_signatures", "record_first_step_flow_signatures")),
        mice=mice,
    )
_REGISTRY: dict[str, WorkloadRegistryItem] = {
    "dp-heavy": WorkloadRegistryItem(
        name="dp-heavy",
        description="AI-factory DP-heavy workload for the AI scale-unit clos presets",
        builder=_build_dp_heavy,
    ),
    "mixed": WorkloadRegistryItem(
        name="mixed",
        description="Concurrent TP-heavy and PP+DP workload for the AI scale-unit clos presets",
        builder=_build_mixed,
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
