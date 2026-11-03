from __future__ import annotations

import pytest

from ai_factory.core.entities import CommPhase, ComputePhase
from ai_factory.traffic.collective import CollectiveAlgorithm
from ai_factory.workloads.dp_heavy_workload import DPHeavyWorkloadConfig, build_dp_heavy_workload_job
from sim.config.loader import load_experiment_spec
from sim.config.models import ConfigError
from sim.registry.workloads import build_scenario
from sim.runners.batch_runner import BatchInput, _run_batch_item
from sim.runners.experiment_runner import run_experiment

DP_SMALL = "tests/fixtures/dp_small.yaml"
PARTICIPANTS = [f"leaf{leaf}_srv{srv}" for leaf in range(2) for srv in range(2)]

# 4 hosts (2 leaves x 2 servers), 3 buckets all released at once, no stalls.
FOUR_HOST_OVERRIDES = [
    "topology.params.leaf_count=2",
    "topology.params.spine_count=2",
    "topology.params.fabric.servers_per_leaf=2",
    "topology.params.fabric.packet_stall_percent=0.0",
    "workload.params.steps=1",
    "workload.params.num_buckets=3",
    "workload.params.bucket_interval_ms=0.0",
]


def _config(**overrides) -> DPHeavyWorkloadConfig:
    values = dict(
        steps=2,
        prolog_compute_ms=1.0,
        bucket_interval_ms=1.0,
        bucket_scheduling="concurrent",
        num_buckets=3,
        bucket_bytes_per_participant=4096,
        algorithm=CollectiveAlgorithm.RING,
        gap_us=5.0,
        optimizer_ms=1.0,
        seed=11,
    )
    values.update(overrides)
    return DPHeavyWorkloadConfig(**values)


def test_prolog_sets_phase_zero_and_interval_spaces_bucket_releases() -> None:
    job = build_dp_heavy_workload_job(
        participants=PARTICIPANTS,
        config=_config(prolog_compute_ms=7.0, bucket_interval_ms=2.5, num_buckets=4),
    )

    for step in job.steps:
        prolog = step.phases[0]
        assert isinstance(prolog, ComputePhase)
        assert prolog.name == "prolog_compute"
        assert prolog.duration_s == pytest.approx(0.007)

        comm_phase = step.phases[1]
        assert isinstance(comm_phase, CommPhase)
        assert len(comm_phase.buckets) == 4
        for b, bucket in enumerate(comm_phase.buckets):
            earliest = min(flow.start_time for flow in bucket.flows)
            assert earliest == pytest.approx(b * 0.0025)


def _bucket_metrics(scheduling: str) -> list:
    spec = load_experiment_spec(
        config_path=DP_SMALL,
        overrides=FOUR_HOST_OVERRIDES + [f"workload.params.bucket_scheduling={scheduling}"],
    )
    results = run_experiment(spec)
    metrics = sorted(results["ai_factory_gradient_bucket_metrics"], key=lambda m: m.bucket_id)
    assert len(metrics) == 3
    return metrics


def _summary(scheduling: str) -> dict:
    row = _run_batch_item(
        BatchInput(
            label=scheduling,
            config_path=DP_SMALL,
            overrides=tuple(FOUR_HOST_OVERRIDES + [f"workload.params.bucket_scheduling={scheduling}"]),
        )
    )
    assert row["ok"]
    return row


def test_serialized_buckets_run_one_after_another() -> None:
    metrics = _bucket_metrics("serialized")

    for prev, cur in zip(metrics, metrics[1:]):
        assert cur.start_time >= prev.end_time
        # All buckets are released together, so later ones have to wait in the queue.
        assert cur.start_time > cur.release_time

    summary = _summary("serialized")
    assert summary["gradient_bucket_wait_time_max_ms"] > 0.0


def test_concurrent_buckets_overlap_and_never_wait() -> None:
    metrics = _bucket_metrics("concurrent")

    assert max(m.start_time for m in metrics) < min(m.end_time for m in metrics)
    for m in metrics:
        assert m.start_time == m.release_time

    summary = _summary("concurrent")
    assert summary["gradient_bucket_wait_time_avg_ms"] == 0.0
    assert summary["gradient_bucket_wait_time_max_ms"] == 0.0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        # The old single timing key was removed; it must fail loudly, not be ignored.
        (["workload.params.t_fwd_bwd_ms=1.0"], "Unknown key.*t_fwd_bwd_ms"),
        (["workload.params.prolog_compute_ms=-1.0"], "prolog_compute_ms must be >= 0"),
        (["workload.params.bucket_interval_ms=-0.5"], "bucket_interval_ms must be >= 0"),
        (["workload.params.bucket_scheduling=parallel"], "bucket_scheduling must be one of"),
    ],
)
def test_invalid_bucket_timing_config_is_rejected(overrides: list[str], message: str) -> None:
    spec = load_experiment_spec(config_path=DP_SMALL, overrides=overrides)

    with pytest.raises(ConfigError, match=message):
        build_scenario(spec)


def test_workload_config_rejects_invalid_values_directly() -> None:
    with pytest.raises(ValueError, match="bucket_scheduling"):
        _config(bucket_scheduling="parallel")
    with pytest.raises(ValueError, match="bucket_interval_ms"):
        _config(bucket_interval_ms=-1.0)
