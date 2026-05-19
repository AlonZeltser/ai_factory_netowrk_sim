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


@dataclass(frozen=True)
class JobStep:
    step_id: int
    phases: list[Phase]


@dataclass(frozen=True)
class Job:
    job_id: int
    name: str
    steps: list[JobStep]
    # Optional: stable list of participants for metrics/placement.
    participants: list[str]


@dataclass
class PhaseMetrics:
    phase_id: int
    name: str
    start_time: float
    end_time: float


@dataclass
class BucketMetrics:
    job_id: int
    step_id: int
    phase_id: int
    phase_name: str
    bucket_id: int
    start_time: float
    end_time: float
    flow_count: int
    transmitted_bytes: int
    useful_bytes: int


@dataclass
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


@dataclass
class StepMetrics:
    step_id: int
    start_time: float
    end_time: float
    phases: list[PhaseMetrics] = field(default_factory=list)


@dataclass
class JobMetrics:
    job_id: int
    start_time: float
    end_time: Optional[float] = None
    steps: list[StepMetrics] = field(default_factory=list)
    bucket_metrics: list[BucketMetrics] = field(default_factory=list)


FlowCompleteCallback = Callable[[int], None]


