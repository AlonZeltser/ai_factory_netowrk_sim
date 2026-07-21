from __future__ import annotations

from dataclasses import dataclass
import secrets

from ai_factory.core.entities import Bucket, CommPhase, ComputePhase, Job, JobCollective
from ai_factory.core.ids import IdGenerator
from ai_factory.traffic.collective import CollectiveAlgorithm, CollectiveKind, expand_collective
from ai_factory.traffic.flow import apply_chunk_redundancy


@dataclass(frozen=True, init=False)
class DPHeavyWorkloadConfig:
    collectives: int
    t_fwd_bwd_ms: float
    num_buckets: int
    bucket_bytes_per_participant: int
    algorithm: CollectiveAlgorithm
    gap_us: float
    optimizer_ms: float
    seed: int
    mtu: int = 4096
    chunk_redundancy_extra_packets: int = 0
    single_ring_only: bool = False

    def __init__(
        self,
        *,
        collectives: int | None = None,
        steps: int | None = None,
        t_fwd_bwd_ms: float,
        num_buckets: int,
        bucket_bytes_per_participant: int,
        algorithm: CollectiveAlgorithm,
        gap_us: float,
        optimizer_ms: float,
        seed: int,
        mtu: int = 4096,
        chunk_redundancy_extra_packets: int = 0,
        single_ring_only: bool = False,
    ) -> None:
        resolved_collectives = collectives if collectives is not None else steps
        if resolved_collectives is None:
            raise TypeError("Provide collectives (preferred) or legacy steps")
        object.__setattr__(self, "collectives", int(resolved_collectives))
        object.__setattr__(self, "t_fwd_bwd_ms", float(t_fwd_bwd_ms))
        object.__setattr__(self, "num_buckets", int(num_buckets))
        object.__setattr__(self, "bucket_bytes_per_participant", int(bucket_bytes_per_participant))
        object.__setattr__(self, "algorithm", algorithm)
        object.__setattr__(self, "gap_us", float(gap_us))
        object.__setattr__(self, "optimizer_ms", float(optimizer_ms))
        object.__setattr__(self, "seed", int(seed))
        object.__setattr__(self, "mtu", int(mtu))
        object.__setattr__(self, "chunk_redundancy_extra_packets", int(chunk_redundancy_extra_packets))
        object.__setattr__(self, "single_ring_only", bool(single_ring_only))


def build_dp_heavy_workload_job(
    *,
    participants: list[str],
    config: DPHeavyWorkloadConfig,
    job_name: str = "workload1-dp-heavy",
) -> Job:
    """Build Workload 1 (DP-heavy) as a Job hierarchy."""

    ids = IdGenerator(seed=config.seed)

    # Make job_id unique per process run even if the workload seed is fixed.
    # Keep it deterministic-ish but collision-resistant.
    job_id = (ids.next_int() ^ secrets.randbits(31)) & 0x7FFFFFFF

    collectives: list[JobCollective] = []
    for collective_idx in range(int(config.collectives)):
        phases: list = []
        collective_ring_seed = ids.child(f"collective{collective_idx}/ring_order").seed

        phases.append(
            ComputePhase(
                phase_id=0,
                name="fwd_bwd_compute",
                duration_s=float(config.t_fwd_bwd_ms) / 1000.0,
            )
        )

        comm_buckets: list[Bucket] = []
        for b in range(int(config.num_buckets)):
            bucket_id = b
            # Bucket start times are relative to the comm-phase start.
            # Bucket 0 is the prolog; later buckets tick at the same interval as
            # the forward/backward delay used by the compute phase.
            start_time = (float(b) * float(config.t_fwd_bwd_ms)) / 1000.0

            rs = expand_collective(
                kind=CollectiveKind.REDUCE_SCATTER,
                algorithm=config.algorithm,
                participants=participants,
                bytes_per_participant=int(config.bucket_bytes_per_participant),
                start_time=start_time,
                gap_us=float(config.gap_us),
                ids=ids.child(f"collective{collective_idx}/phase1/bucket{bucket_id}/rs"),
                job_id=job_id,
                collective_id=collective_idx,
                phase_id=1,
                bucket_id=bucket_id,
                ring_seed=collective_ring_seed,
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
                    ids=ids.child(f"collective{collective_idx}/phase1/bucket{bucket_id}/ag"),
                    job_id=job_id,
                    collective_id=collective_idx,
                    phase_id=1,
                    bucket_id=bucket_id,
                    ring_seed=collective_ring_seed,
                    write_to_log=b == 0
                )
                ag_flows = ag.flows

            comm_buckets.append(
                Bucket(
                    bucket_id=bucket_id,
                    flows=apply_chunk_redundancy(
                        rs.flows + ag_flows,
                        extra_packets=int(config.chunk_redundancy_extra_packets),
                        mtu=int(config.mtu),
                    ),
                )
            )

        phases.append(CommPhase(phase_id=1, name="gradient_sync", buckets=comm_buckets))

        phases.append(
            ComputePhase(
                phase_id=2,
                name="optimizer_compute",
                duration_s=float(config.optimizer_ms) / 1000.0,
            )
        )

        collectives.append(JobCollective(collective_id=collective_idx, phases=phases))

    return Job(job_id=job_id, name=job_name, collectives=collectives, participants=participants)
