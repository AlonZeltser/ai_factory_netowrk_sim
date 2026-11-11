from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from ai_factory.traffic.flow import Flow


@dataclass(frozen=True)
class GradientBucket:
    bucket_id: int
    # Flows to emit for this gradient bucket (reduce-scatter, then all-gather).
    flows: list[Flow]


@dataclass(frozen=True)
class Phase:
    phase_id: int
    name: str


@dataclass(frozen=True)
class ComputePhase(Phase):
    duration_s: float


# How the gradient buckets of a comm phase share the network:
# - concurrent: each bucket starts at its own release time, independent of the others.
# - serialized: bucket b starts no earlier than the completion of bucket b-1 (NCCL-style queue).
BUCKET_SCHEDULING_MODES = ("concurrent", "serialized")


@dataclass(frozen=True)
class CommPhase(Phase):
    buckets: list[GradientBucket]
    # From ai_workload.bucket_scheduling.
    bucket_scheduling: str


@dataclass(frozen=True)
class TrainingStep:
    step_id: int
    phases: list[Phase]


@dataclass(frozen=True)
class TrainingJob:
    job_id: int
    name: str
    steps: list[TrainingStep]
    # Optional: stable list of participants for metrics/placement.
    participants: list[str]


@dataclass(slots=True)
class PhaseMetrics:
    phase_id: int
    name: str
    start_time: float
    end_time: float


@dataclass(slots=True)
class GradientBucketMetrics:
    job_id: int
    step_id: int
    phase_id: int
    phase_name: str
    bucket_id: int
    # When the bucket's gradients are ready (its earliest flow offset after the comm-phase start).
    release_time: float
    # When the bucket's first flow is injected; later than release_time if it waited in a queue.
    start_time: float
    end_time: float
    flow_count: int
    transmitted_bytes: int
    useful_bytes: int


@dataclass(slots=True)
class FlowMetrics:
    flow_id: int
    job_id: int
    step_id: int
    phase_id: int
    bucket_id: int | None
    tag: str
    src_node_id: str
    dst_node_id: str
    start_time: float
    end_time: float
    transmitted_bytes: int
    useful_bytes: int


@dataclass(slots=True)
class TrainingStepMetrics:
    step_id: int
    start_time: float
    end_time: float
    # Filled in by the runner as phases finish.
    phases: list[PhaseMetrics] = field(init=False, default_factory=list)


@dataclass(slots=True)
class TrainingJobMetrics:
    job_id: int
    start_time: float
    # Runner state: None until the job finishes; the lists fill in as the job runs.
    end_time: Optional[float] = field(init=False, default=None)
    steps: list[TrainingStepMetrics] = field(init=False, default_factory=list)
    bucket_metrics: list[GradientBucketMetrics] = field(init=False, default_factory=list)


FlowCompleteCallback = Callable[[int], None]
