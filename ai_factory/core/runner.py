from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Callable, List

from des.des import DiscreteEventSimulator

from ai_factory.core.entities import (
    Job,
    JobMetrics,
    StepMetrics,
    PhaseMetrics,
    BucketMetrics,
    ComputePhase,
    CommPhase,
    Bucket,
)
from ai_factory.core.schedule import BarrierBookkeeper, Join, schedule_timer
from ai_factory.traffic.flow import Flow

_logger = logging.getLogger(__name__)


def _compute_percentile(sorted_values: List[float], percentile: float) -> float:
    """Compute percentile from a sorted list of values.

    Args:
        sorted_values: A sorted list of numeric values.
        percentile: Percentile to compute (0-100).

    Returns:
        The percentile value.
    """
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    # Use linear interpolation between closest ranks
    rank = (percentile / 100.0) * (n - 1)
    lower_idx = int(rank)
    upper_idx = min(lower_idx + 1, n - 1)
    weight = rank - lower_idx
    return sorted_values[lower_idx] * (1 - weight) + sorted_values[upper_idx] * weight


def _compute_step_stats(steps: List[StepMetrics]) -> dict:
    """Compute step duration statistics in seconds.

    Returns:
        Dictionary with average, percentiles, and spread keys.
    """
    durations = [s.end_time - s.start_time for s in steps if s.end_time >= 0]
    if not durations:
        return {
            'avg': 0.0,
            'p95': 0.0,
            'p99': 0.0,
            'std': 0.0,
            'min': 0.0,
            'max': 0.0,
            'count': 0,
        }

    avg = sum(durations) / len(durations)
    sorted_durations = sorted(durations)
    p95 = _compute_percentile(sorted_durations, 95.0)
    p99 = _compute_percentile(sorted_durations, 99.0)
    var = sum((d - avg) ** 2 for d in durations) / len(durations)
    std = math.sqrt(var)

    return {
        'avg': avg,
        'p95': p95,
        'p99': p99,
        'std': std,
        'min': sorted_durations[0],
        'max': sorted_durations[-1],
        'count': len(sorted_durations),
    }


class FlowInjector:
    """Adapter interface: Flow -> network injection.

    Implementations must call `on_complete(flow_id)` once the flow is fully delivered.
    """

    def inject(self, flow: Flow, *, on_complete: Callable[[int], None]) -> None:
        raise NotImplementedError


def _sim_time_prefix(sim: DiscreteEventSimulator) -> str:
    """Format simulator time prefix for aligned logging."""
    return f"[sim_t={sim.get_current_time():012.6f}s]"


@dataclass
class JobRunner:
    """Event-driven state machine that advances Job -> Step -> Phase.

    - Compute phases schedule DES timers.
    - Comm phases inject flows and wait for completion events.
    """

    sim: DiscreteEventSimulator
    injector: FlowInjector
    job: Job

    metrics: JobMetrics | None = None

    def run(self) -> JobMetrics:
        self.metrics = JobMetrics(job_id=self.job.job_id, start_time=self.sim.get_current_time())
        self.sim.schedule_event(0.0, self._start_job)
        return self.metrics

    def _start_job(self) -> None:
        assert self.metrics is not None
        logging.info(
            f"{_sim_time_prefix(self.sim)} Job starting       job={self.job.name} id={self.job.job_id} participants={len(self.job.participants)} steps={len(self.job.steps)}"
        )
        self._run_step(step_index=0)

    def _run_step(self, *, step_index: int) -> None:
        assert self.metrics is not None
        if step_index >= len(self.job.steps):
            self.metrics.end_time = self.sim.get_current_time()
            # Compute and log step performance statistics
            step_stats = _compute_step_stats(self.metrics.steps)
            logging.info(
                f"{_sim_time_prefix(self.sim)} Job finished       job_id={self.job.job_id} "
                f"step_time_avg={step_stats['avg']*1000:.3f}ms "
                f"step_time_p95={step_stats['p95']*1000:.3f}ms "
                f"step_time_p99={step_stats['p99']*1000:.3f}ms"
            )
            return

        _logger.info(f"{_sim_time_prefix(self.sim)} Step starting      step={step_index}")
        step = self.job.steps[step_index]
        step_metrics = StepMetrics(step_id=step.step_id, start_time=self.sim.get_current_time(), end_time=-1.0)
        self.metrics.steps.append(step_metrics)
        self._run_phase(step_index=step_index, phase_index=0)

    def _run_phase(self, *, step_index: int, phase_index: int) -> None:
        assert self.metrics is not None
        step = self.job.steps[step_index]
        step_metrics = self.metrics.steps[-1]

        if phase_index >= len(step.phases):
            step_metrics.end_time = self.sim.get_current_time()
            step_duration_ms = (step_metrics.end_time - step_metrics.start_time) * 1000.0
            _logger.info(
                f"{_sim_time_prefix(self.sim)} Step finished      step={step_index} duration={step_duration_ms:.3f}ms"
            )
            self._run_step(step_index=step_index + 1)
            return

        phase = step.phases[phase_index]
        _logger.info(f"{_sim_time_prefix(self.sim)} Phase starting     step={step_index} phase={phase_index} name={phase.name}")
        phase_metrics = PhaseMetrics(
            phase_id=phase.phase_id,
            name=phase.name,
            start_time=self.sim.get_current_time(),
            end_time=-1.0,
        )
        step_metrics.phases.append(phase_metrics)

        def done_phase() -> None:
            phase_metrics.end_time = self.sim.get_current_time()
            _logger.info(f"{_sim_time_prefix(self.sim)} Phase finished     step={step_index} phase={phase_index} name={phase.name}")
            self._run_phase(step_index=step_index, phase_index=phase_index + 1)

        if isinstance(phase, ComputePhase):
            schedule_timer(self.sim, delay_s=phase.duration_s, cb=done_phase)
            return

        if isinstance(phase, CommPhase):
            self._run_comm_phase(step.step_id, phase, done_phase)
            return

        raise TypeError(f"Unknown phase type: {type(phase)}")

    def _run_comm_phase(self, step_id: int, phase: CommPhase, done_phase: Callable[[], None]) -> None:
        book = BarrierBookkeeper()
        assert self.metrics is not None

        if not phase.buckets:
            done_phase()
            return

        # Buckets in the comm phase launch together; the phase advances only after all
        # bucket joins complete. This keeps bucket timing independent while preserving
        # the step/phase barrier behavior.
        remaining_buckets = len(phase.buckets)

        def mark_bucket_finished() -> None:
            nonlocal remaining_buckets
            remaining_buckets -= 1
            if remaining_buckets == 0:
                done_phase()

        def launch_bucket(bucket_index: int) -> None:
            bucket: Bucket = phase.buckets[bucket_index]
            now = self.sim.get_current_time()
            bucket_start_offset = min((float(f.start_time) for f in bucket.flows), default=0.0)
            bucket_start_time = float(now + bucket_start_offset)

            if _logger.isEnabledFor(logging.DEBUG):
                _logger.debug(
                    f"{_sim_time_prefix(self.sim)} Bucket scheduled  phase={phase.name} bucket={bucket_index} "
                    f"start_offset_ms={bucket_start_offset * 1000.0:.3f} start_time={bucket_start_time:.6f}s"
                )

            if not bucket.flows:
                self.metrics.bucket_metrics.append(
                    BucketMetrics(
                        job_id=int(self.job.job_id),
                        step_id=int(step_id),
                        phase_id=int(phase.phase_id),
                        phase_name=phase.name,
                        bucket_id=int(bucket.bucket_id),
                        start_time=float(bucket_start_time),
                        end_time=float(now),
                        flow_count=0,
                        transmitted_bytes=0,
                        useful_bytes=0,
                    )
                )
                if _logger.isEnabledFor(logging.DEBUG):
                    _logger.debug(f"{_sim_time_prefix(self.sim)} Bucket finished    phase={phase.name} bucket={bucket_index} (empty)")
                mark_bucket_finished()
                return

            join_name = f"phase{phase.phase_id}/bucket{bucket.bucket_id}"
            bucket_metrics = BucketMetrics(
                job_id=int(self.job.job_id),
                step_id=int(step_id),
                phase_id=int(phase.phase_id),
                phase_name=phase.name,
                bucket_id=int(bucket.bucket_id),
                start_time=float(bucket_start_time),
                end_time=-1.0,
                flow_count=len(bucket.flows),
                transmitted_bytes=sum(int(f.size_bytes) for f in bucket.flows),
                useful_bytes=sum(int(f.useful_size_bytes) for f in bucket.flows),
            )
            self.metrics.bucket_metrics.append(bucket_metrics)

            def done_bucket() -> None:
                bucket_metrics.end_time = float(self.sim.get_current_time())
                duration_ms = (bucket_metrics.end_time - bucket_metrics.start_time) * 1000.0
                _logger.info(f"[{phase.name}] Bucket {bucket_index} finished: duration={duration_ms:.2f}ms")
                if _logger.isEnabledFor(logging.DEBUG):
                    _logger.debug(f"{_sim_time_prefix(self.sim)} Bucket finished    phase={phase.name} bucket={bucket_index}")
                mark_bucket_finished()

            join = Join(pending={f.flow_id for f in bucket.flows}, on_done=done_bucket)
            book.add_join(join_name, join)

            for f in bucket.flows:
                delay = max(0.0, float(f.start_time))

                def _inject(ff: Flow = f) -> None:
                    self.injector.inject(ff, on_complete=book.on_flow_complete)

                self.sim.schedule_event(delay, _inject)

        for bucket_index in range(len(phase.buckets)):
            launch_bucket(bucket_index)


