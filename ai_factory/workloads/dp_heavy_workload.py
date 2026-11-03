from __future__ import annotations

from dataclasses import dataclass
import secrets

from ai_factory.core.entities import (
    BUCKET_SCHEDULING_MODES,
    CommPhase,
    ComputePhase,
    GradientBucket,
    TrainingJob,
    TrainingStep,
)
from ai_factory.core.ids import IdGenerator
from ai_factory.traffic.collective import CollectiveAlgorithm, CollectiveKind, expand_collective
from ai_factory.traffic.flow import apply_flow_redundancy


@dataclass(frozen=True)
class DPHeavyWorkloadConfig:
    steps: int
    # Compute time from step start until the first bucket's gradients are ready.
    prolog_compute_ms: float
    # Backward-compute time between the release of bucket b and bucket b+1.
    bucket_interval_ms: float
    # How released buckets share the network: "concurrent" or "serialized".
    bucket_scheduling: str
    num_buckets: int
    bucket_bytes_per_participant: int
    algorithm: CollectiveAlgorithm
    gap_us: float
    optimizer_ms: float
    seed: int
    mtu: int = 4096
    flow_redundancy_extra_packets: int = 0
    single_ring_only: bool = False

    def __post_init__(self) -> None:
        if self.prolog_compute_ms < 0:
            raise ValueError(f"prolog_compute_ms must be >= 0, got {self.prolog_compute_ms}")
        if self.bucket_interval_ms < 0:
            raise ValueError(f"bucket_interval_ms must be >= 0, got {self.bucket_interval_ms}")
        if self.bucket_scheduling not in BUCKET_SCHEDULING_MODES:
            raise ValueError(
                f"bucket_scheduling must be one of {', '.join(BUCKET_SCHEDULING_MODES)}, got {self.bucket_scheduling!r}"
            )


def build_dp_heavy_workload_job(
    *,
    participants: list[str],
    config: DPHeavyWorkloadConfig,
    job_name: str = "workload1-dp-heavy",
) -> TrainingJob:
    """Build Workload 1 (DP-heavy) as a TrainingJob -> TrainingStep -> GradientBucket hierarchy."""

    ids = IdGenerator(seed=config.seed)

    # Make job_id unique per process run even if the workload seed is fixed.
    # Keep it deterministic-ish but collision-resistant.
    job_id = (ids.next_int() ^ secrets.randbits(31)) & 0x7FFFFFFF

    steps: list[TrainingStep] = []
    for step_idx in range(int(config.steps)):
        phases: list = []
        step_ring_seed = ids.child(f"step{step_idx}/ring_order").seed

        phases.append(
            ComputePhase(
                phase_id=0,
                name="prolog_compute",
                duration_s=float(config.prolog_compute_ms) / 1000.0,
            )
        )

        comm_buckets: list[GradientBucket] = []
        for b in range(int(config.num_buckets)):
            bucket_id = b
            # Release time relative to the comm-phase start: bucket b's gradients are ready
            # b intervals of backward compute after bucket 0. The rest of backward overlaps
            # the comm phase, so the last bucket is released exactly when backward ends.
            start_time = (float(b) * float(config.bucket_interval_ms)) / 1000.0

            rs = expand_collective(
                kind=CollectiveKind.REDUCE_SCATTER,
                algorithm=config.algorithm,
                participants=participants,
                bytes_per_participant=int(config.bucket_bytes_per_participant),
                start_time=start_time,
                gap_us=float(config.gap_us),
                ids=ids.child(f"step{step_idx}/phase1/bucket{bucket_id}/rs"),
                job_id=job_id,
                step_id=step_idx,
                phase_id=1,
                bucket_id=bucket_id,
                ring_seed=step_ring_seed,
                write_to_log=b==0
            )
            ag_flows = []
            if not bool(config.single_ring_only):
                ag = expand_collective(
                    kind=CollectiveKind.ALL_GATHER,
                    algorithm=config.algorithm,
                    participants=participants,
                    bytes_per_participant=int(config.bucket_bytes_per_participant),
                    start_time=start_time,
                    gap_us=float(config.gap_us),
                    ids=ids.child(f"step{step_idx}/phase1/bucket{bucket_id}/ag"),
                    job_id=job_id,
                    step_id=step_idx,
                    phase_id=1,
                    bucket_id=bucket_id,
                    ring_seed=step_ring_seed,
                    write_to_log=b == 0
                )
                ag_flows = ag.flows

            comm_buckets.append(
                GradientBucket(
                    bucket_id=bucket_id,
                    flows=apply_flow_redundancy(
                        rs.flows + ag_flows,
                        extra_packets=int(config.flow_redundancy_extra_packets),
                        mtu=int(config.mtu),
                    ),
                )
            )

        phases.append(
            CommPhase(
                phase_id=1,
                name="gradient_sync",
                buckets=comm_buckets,
                bucket_scheduling=config.bucket_scheduling,
            )
        )

        phases.append(
            ComputePhase(
                phase_id=2,
                name="optimizer_compute",
                duration_s=float(config.optimizer_ms) / 1000.0,
            )
        )

        steps.append(TrainingStep(step_id=step_idx, phases=phases))

    return TrainingJob(job_id=job_id, name=job_name, steps=steps, participants=participants)
