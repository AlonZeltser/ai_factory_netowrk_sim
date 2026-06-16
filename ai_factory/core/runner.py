from __future__ import annotations

from collections import defaultdict
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


def _collect_step_flow_ids(step) -> set[int]:
    flow_ids: set[int] = set()
    for phase in step.phases:
        if not isinstance(phase, CommPhase):
            continue
        for bucket in phase.buckets:
            for flow in bucket.flows:
                flow_ids.add(int(flow.flow_id))
    return flow_ids


def _ring_op_prefix(tag: str) -> str | None:
    if "/ring_step_" not in tag:
        return None
    return tag.split("/ring_step_", 1)[0]


def _build_bucket_dependency_graph(
    flows: list[Flow],
) -> tuple[dict[int, list[int]], dict[int, int], dict[int, Flow]]:
    """Return dependents, pending counts, and an id->flow lookup for a bucket.

    Ring flows use a causal chain: step s depends on the matching sender's
    predecessor at step s-1 within the same collective operation.

    DP-heavy double-ring semantics are also enforced: all-gather step 0 for
    sender X depends on reduce-scatter's final arrival into X.
    Non-ring flows are treated as dependency-free.
    """

    flow_by_id = {int(flow.flow_id): flow for flow in flows}
    dependents: dict[int, list[int]] = defaultdict(list)
    pending: dict[int, int] = {flow_id: 0 for flow_id in flow_by_id}

    predecessor_by_key: dict[tuple[str, int, str], int] = {}
    max_step_by_op: dict[str, int] = {}
    for flow in flows:
        op_prefix = _ring_op_prefix(flow.tag)
        ring_step = flow.metadata.get("ring_step")
        if op_prefix is None or ring_step is None:
            continue
        step_idx = int(ring_step)
        predecessor_by_key[(op_prefix, step_idx, flow.dst_node_id)] = int(flow.flow_id)
        max_step_by_op[op_prefix] = max(step_idx, max_step_by_op.get(op_prefix, -1))

    for flow in flows:
        op_prefix = _ring_op_prefix(flow.tag)
        ring_step = flow.metadata.get("ring_step")
        if op_prefix is None or ring_step is None:
            continue

        step_idx = int(ring_step)
        if step_idx <= 0:
            continue

        pred_id = predecessor_by_key.get((op_prefix, step_idx - 1, flow.src_node_id))
        if pred_id is None:
            # Fail open so malformed metadata does not deadlock the run.
            continue

        pending[int(flow.flow_id)] = pending.get(int(flow.flow_id), 0) + 1
        dependents[pred_id].append(int(flow.flow_id))

    rs_last_step = max_step_by_op.get("reduce_scatter")
    if rs_last_step is not None:
        for flow in flows:
            op_prefix = _ring_op_prefix(flow.tag)
            ring_step = flow.metadata.get("ring_step")
            if op_prefix != "all_gather" or ring_step is None or int(ring_step) != 0:
                continue

            rs_pred_id = predecessor_by_key.get(("reduce_scatter", rs_last_step, flow.src_node_id))
            if rs_pred_id is None:
                continue

            pending[int(flow.flow_id)] = pending.get(int(flow.flow_id), 0) + 1
            dependents[rs_pred_id].append(int(flow.flow_id))

    return dependents, pending, flow_by_id


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

    def _max_per_flow_drops_for_step(self, step_flow_ids: set[int]) -> int:
        packet_stats = getattr(self.sim, "packet_stats", None)
        if packet_stats is None or not step_flow_ids:
            return 0
        max_fn = getattr(packet_stats, "max_dropped_for_flow_ids", None)
        if callable(max_fn):
            value = max_fn(step_flow_ids)
            if isinstance(value, (int, float)):
                return int(value)
        return 0

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
        step_flow_ids = _collect_step_flow_ids(step)
        step_metrics = StepMetrics(step_id=step.step_id, start_time=self.sim.get_current_time(), end_time=-1.0)
        self.metrics.steps.append(step_metrics)
        self._run_phase(step_index=step_index, phase_index=0, step_flow_ids=step_flow_ids)

    def _run_phase(self, *, step_index: int, phase_index: int, step_flow_ids: set[int]) -> None:
        assert self.metrics is not None
        step = self.job.steps[step_index]
        step_metrics = self.metrics.steps[-1]

        if phase_index >= len(step.phases):
            step_metrics.end_time = self.sim.get_current_time()
            step_duration_ms = (step_metrics.end_time - step_metrics.start_time) * 1000.0
            max_per_flow_drops = self._max_per_flow_drops_for_step(step_flow_ids)
            _logger.info(
                f"{_sim_time_prefix(self.sim)} Step finished      step={step_index} duration={step_duration_ms:.3f}ms max_per_flow_drops={max_per_flow_drops}"
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
            self._run_phase(step_index=step_index, phase_index=phase_index + 1, step_flow_ids=step_flow_ids)

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
            bucket_launch_origin = float(now)
            bucket_start_offset = min((float(f.start_time) for f in bucket.flows), default=0.0)
            bucket_start_time = float(now + bucket_start_offset)
            dependency_graph, pending_prereqs, flow_by_id = _build_bucket_dependency_graph(bucket.flows)
            injected_flow_ids: set[int] = set()

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

            def schedule_injection(flow: Flow) -> None:
                flow_id = int(flow.flow_id)
                if flow_id in injected_flow_ids:
                    return
                injected_flow_ids.add(flow_id)

                launch_time = bucket_launch_origin + max(0.0, float(flow.start_time))
                delay = max(0.0, launch_time - self.sim.get_current_time())

                def _inject(ff: Flow = flow) -> None:
                    self.injector.inject(ff, on_complete=on_flow_complete)

                self.sim.schedule_event(delay, _inject)

            def on_flow_complete(flow_id: int) -> None:
                book.on_flow_complete(flow_id)

                for dependent_id in dependency_graph.get(flow_id, []):
                    pending_prereqs[dependent_id] = max(0, pending_prereqs.get(dependent_id, 0) - 1)
                    if pending_prereqs[dependent_id] == 0:
                        dependent_flow = flow_by_id.get(dependent_id)
                        if dependent_flow is not None:
                            schedule_injection(dependent_flow)

            for f in bucket.flows:
                if pending_prereqs.get(int(f.flow_id), 0) == 0:
                    schedule_injection(f)

        for bucket_index in range(len(phase.buckets)):
            launch_bucket(bucket_index)


