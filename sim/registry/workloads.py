from __future__ import annotations

from ai_factory.core.entities import BUCKET_SCHEDULING_MODES
from ai_factory.scenarios.ai_factory_su_dp_heavy_scenario import AIFactorySUDpHeavyScenario
from network.scenarios.base import Scenario
from ..config.models import AIWorkloadSpec, ConfigError, ExperimentSpec


def _check_bucket_timing(workload: AIWorkloadSpec) -> None:
    if workload.prolog_compute_ms < 0:
        raise ConfigError(f"ai_workload.prolog_compute_ms must be >= 0, got {workload.prolog_compute_ms}")
    if workload.bucket_interval_ms < 0:
        raise ConfigError(f"ai_workload.bucket_interval_ms must be >= 0, got {workload.bucket_interval_ms}")
    if workload.bucket_scheduling not in BUCKET_SCHEDULING_MODES:
        valid = ", ".join(BUCKET_SCHEDULING_MODES)
        raise ConfigError(f"ai_workload.bucket_scheduling must be one of {valid}, got {workload.bucket_scheduling!r}")


def build_scenario(spec: ExperimentSpec) -> Scenario:
    """Build the DP-heavy training scenario described by the config."""
    workload = spec.ai_workload
    _check_bucket_timing(workload)
    return AIFactorySUDpHeavyScenario(
        steps=workload.steps,
        seed=workload.seed,
        num_buckets=workload.num_buckets,
        bucket_bytes_per_participant=workload.bucket_bytes_per_participant,
        gap_us=workload.gap_us,
        prolog_compute_ms=workload.prolog_compute_ms,
        bucket_interval_ms=workload.bucket_interval_ms,
        bucket_scheduling=workload.bucket_scheduling,
        optimizer_ms=workload.optimizer_ms,
        mtu=spec.routing.mtu,
        flow_redundancy_extra_packets=workload.flow_redundancy_extra_packets,
        single_ring_only=workload.single_ring_only,
    )
