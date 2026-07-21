from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from ai_factory.traffic.flow import Flow


@dataclass(frozen=True)
class Bucket:
    bucket_id: int
    # Ordered list of flow bundles (e.g., collectives) to emit for this bucket.
    flows: list[Flow]


@dataclass(frozen=True)
class Phase:
    phase_id: int
    name: str


@dataclass(frozen=True)
class ComputePhase(Phase):
    duration_s: float


@dataclass(frozen=True)
class CommPhase(Phase):
    buckets: list[Bucket] = field(default_factory=list)


@dataclass(frozen=True, init=False)
class JobCollective:
    collective_id: int
    phases: list[Phase]

    def __init__(self, *, collective_id: int | None = None, step_id: int | None = None, phases: list[Phase]) -> None:
        resolved_collective_id = collective_id if collective_id is not None else step_id
        if resolved_collective_id is None:
            raise TypeError("Provide collective_id (preferred) or legacy step_id")
        object.__setattr__(self, "collective_id", int(resolved_collective_id))
        object.__setattr__(self, "phases", list(phases))

    @property
    def step_id(self) -> int:
        return self.collective_id


@dataclass(frozen=True, init=False)
class Job:
    job_id: int
    name: str
    collectives: list[JobCollective]
    # Optional: stable list of participants for metrics/placement.
    participants: list[str]

    def __init__(
        self,
        *,
        job_id: int,
        name: str,
        collectives: list[JobCollective] | None = None,
        steps: list[JobCollective] | None = None,
        participants: list[str],
    ) -> None:
        resolved_collectives = collectives if collectives is not None else steps
        if resolved_collectives is None:
            raise TypeError("Provide collectives (preferred) or legacy steps")
        object.__setattr__(self, "job_id", int(job_id))
        object.__setattr__(self, "name", str(name))
        object.__setattr__(self, "collectives", list(resolved_collectives))
        object.__setattr__(self, "participants", list(participants))

    @property
    def steps(self) -> list[JobCollective]:
        return self.collectives


@dataclass(slots=True)
class PhaseMetrics:
    phase_id: int
    name: str
    start_time: float
    end_time: float


@dataclass(slots=True, init=False)
class BucketMetrics:
    job_id: int
    collective_id: int
    phase_id: int
    phase_name: str
    bucket_id: int
    start_time: float
    end_time: float
    flow_count: int
    transmitted_bytes: int
    useful_bytes: int

    def __init__(
        self,
        *,
        job_id: int,
        collective_id: int | None = None,
        step_id: int | None = None,
        phase_id: int,
        phase_name: str,
        bucket_id: int,
        start_time: float,
        end_time: float,
        flow_count: int,
        transmitted_bytes: int,
        useful_bytes: int,
    ) -> None:
        resolved_collective_id = collective_id if collective_id is not None else step_id
        if resolved_collective_id is None:
            raise TypeError("Provide collective_id (preferred) or legacy step_id")
        self.job_id = int(job_id)
        self.collective_id = int(resolved_collective_id)
        self.phase_id = int(phase_id)
        self.phase_name = str(phase_name)
        self.bucket_id = int(bucket_id)
        self.start_time = float(start_time)
        self.end_time = float(end_time)
        self.flow_count = int(flow_count)
        self.transmitted_bytes = int(transmitted_bytes)
        self.useful_bytes = int(useful_bytes)

    @property
    def step_id(self) -> int:
        return self.collective_id


@dataclass(slots=True, init=False)
class FlowMetrics:
    flow_id: int
    job_id: int
    collective_id: int
    phase_id: int
    bucket_id: int | None
    tag: str
    src_node_id: str
    dst_node_id: str
    start_time: float
    end_time: float
    transmitted_bytes: int
    useful_bytes: int

    def __init__(
        self,
        *,
        flow_id: int,
        job_id: int,
        collective_id: int | None = None,
        step_id: int | None = None,
        phase_id: int,
        bucket_id: int | None,
        tag: str,
        src_node_id: str,
        dst_node_id: str,
        start_time: float,
        end_time: float,
        transmitted_bytes: int,
        useful_bytes: int,
    ) -> None:
        resolved_collective_id = collective_id if collective_id is not None else step_id
        if resolved_collective_id is None:
            raise TypeError("Provide collective_id (preferred) or legacy step_id")
        self.flow_id = int(flow_id)
        self.job_id = int(job_id)
        self.collective_id = int(resolved_collective_id)
        self.phase_id = int(phase_id)
        self.bucket_id = bucket_id
        self.tag = str(tag)
        self.src_node_id = str(src_node_id)
        self.dst_node_id = str(dst_node_id)
        self.start_time = float(start_time)
        self.end_time = float(end_time)
        self.transmitted_bytes = int(transmitted_bytes)
        self.useful_bytes = int(useful_bytes)

    @property
    def step_id(self) -> int:
        return self.collective_id


@dataclass(slots=True, init=False)
class CollectiveMetrics:
    collective_id: int
    start_time: float
    end_time: float
    phases: list[PhaseMetrics] = field(default_factory=list)

    def __init__(
        self,
        *,
        collective_id: int | None = None,
        step_id: int | None = None,
        start_time: float,
        end_time: float,
        phases: list[PhaseMetrics] | None = None,
    ) -> None:
        resolved_collective_id = collective_id if collective_id is not None else step_id
        if resolved_collective_id is None:
            raise TypeError("Provide collective_id (preferred) or legacy step_id")
        self.collective_id = int(resolved_collective_id)
        self.start_time = float(start_time)
        self.end_time = float(end_time)
        self.phases = list(phases or [])

    @property
    def step_id(self) -> int:
        return self.collective_id


@dataclass(slots=True, init=False)
class JobMetrics:
    job_id: int
    start_time: float
    end_time: Optional[float] = None
    collectives: list[CollectiveMetrics] = field(default_factory=list)
    bucket_metrics: list[BucketMetrics] = field(default_factory=list)

    def __init__(
        self,
        *,
        job_id: int,
        start_time: float,
        end_time: Optional[float] = None,
        collectives: list[CollectiveMetrics] | None = None,
        steps: list[CollectiveMetrics] | None = None,
        bucket_metrics: list[BucketMetrics] | None = None,
    ) -> None:
        resolved_collectives = collectives if collectives is not None else steps
        self.job_id = int(job_id)
        self.start_time = float(start_time)
        self.end_time = float(end_time) if end_time is not None else None
        self.collectives = list(resolved_collectives or [])
        self.bucket_metrics = list(bucket_metrics or [])

    @property
    def steps(self) -> list[CollectiveMetrics]:
        return self.collectives


JobStep = JobCollective
StepMetrics = CollectiveMetrics


FlowCompleteCallback = Callable[[int], None]


