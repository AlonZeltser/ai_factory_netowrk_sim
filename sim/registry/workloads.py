from __future__ import annotations
from dataclasses import dataclass
import logging
from typing import Any, Callable, Iterable
from ai_factory.core.entities import BUCKET_SCHEDULING_MODES
from ai_factory.scenarios.ai_factory_su_dp_heavy_scenario import AIFactorySUDpHeavyScenario
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


_log = logging.getLogger(__name__)
_BUCKET_TIMING_KEYS = ("prolog_compute_ms", "bucket_interval_ms", "bucket_scheduling")


def _resolve_bucket_timing(params: dict[str, Any]) -> tuple[float, float, str]:
    """Return (prolog_compute_ms, bucket_interval_ms, bucket_scheduling) from workload params.

    The deprecated t_fwd_bwd_ms is still accepted on its own and maps to
    prolog = interval = t_fwd_bwd_ms with concurrent buckets (the original model).
    """
    if "t_fwd_bwd_ms" in params:
        mixed = [key for key in _BUCKET_TIMING_KEYS if key in params]
        if mixed:
            raise ConfigError(
                "workload.params.t_fwd_bwd_ms is deprecated and cannot be combined with "
                + ", ".join(f"workload.params.{key}" for key in mixed)
                + ". Remove t_fwd_bwd_ms and set prolog_compute_ms / bucket_interval_ms / bucket_scheduling."
            )
        legacy = float(params["t_fwd_bwd_ms"])
        _log.warning(
            "workload.params.t_fwd_bwd_ms is deprecated; using prolog_compute_ms=%s, bucket_interval_ms=%s, "
            "bucket_scheduling=concurrent",
            legacy,
            legacy,
        )
        prolog, interval, scheduling = legacy, legacy, "concurrent"
    else:
        prolog = float(_require_param(params, "prolog_compute_ms"))
        interval = float(_require_param(params, "bucket_interval_ms"))
        scheduling = str(_require_param(params, "bucket_scheduling"))

    if prolog < 0:
        raise ConfigError(f"workload.params.prolog_compute_ms must be >= 0, got {prolog}")
    if interval < 0:
        raise ConfigError(f"workload.params.bucket_interval_ms must be >= 0, got {interval}")
    if scheduling not in BUCKET_SCHEDULING_MODES:
        valid = ", ".join(BUCKET_SCHEDULING_MODES)
        raise ConfigError(f"workload.params.bucket_scheduling must be one of {valid}, got {scheduling!r}")
    return prolog, interval, scheduling


def _build_none(workload: WorkloadSpec, topology: TopologySpec) -> Scenario:
    return NoneScenario()
def _build_dp_heavy(workload: WorkloadSpec, topology: TopologySpec) -> Scenario:
    _require_topology(topology, "clos")
    _require_no_profile(workload)
    params = dict(workload.params)
    seed = int(_require_param(params, "seed"))
    mtu = int(topology.params.get("mtu", 4096))
    prolog_compute_ms, bucket_interval_ms, bucket_scheduling = _resolve_bucket_timing(params)
    return AIFactorySUDpHeavyScenario(
        steps=int(_require_param(params, "steps")),
        seed=seed,
        num_buckets=int(_require_param(params, "num_buckets")),
        bucket_bytes_per_participant=int(_require_param(params, "bucket_bytes_per_participant")),
        gap_us=float(_require_param(params, "gap_us")),
        prolog_compute_ms=prolog_compute_ms,
        bucket_interval_ms=bucket_interval_ms,
        bucket_scheduling=bucket_scheduling,
        optimizer_ms=float(_require_param(params, "optimizer_ms")),
        mtu=mtu,
        flow_redundancy_extra_packets=int(_require_param(params, "flow_redundancy_extra_packets")),
        single_ring_only=bool(_require_param(params, "single_ring_only")),
    )

_REGISTRY: dict[str, WorkloadRegistryItem] = {
    "dp-heavy": WorkloadRegistryItem(
        name="dp-heavy",
        description="AI-factory DP-heavy workload on the AI scale-unit clos topology",
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
