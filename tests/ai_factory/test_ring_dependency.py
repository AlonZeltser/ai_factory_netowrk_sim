from __future__ import annotations

from ai_factory.core.entities import CommPhase
from ai_factory.core.runner import FlowInjector, JobRunner
from ai_factory.traffic.collective import CollectiveAlgorithm
from ai_factory.traffic.flow import Flow
from ai_factory.workloads.dp_heavy_workload import DPHeavyWorkloadConfig, build_dp_heavy_workload_job
from des.des import DiscreteEventSimulator


class _TimedCompletionInjector(FlowInjector):
    def __init__(self, sim: DiscreteEventSimulator):
        self.sim = sim
        self.inject_times: dict[int, float] = {}
        self.complete_times: dict[int, float] = {}

    def inject(self, flow: Flow, *, on_complete):
        flow_id = int(flow.flow_id)
        self.inject_times[flow_id] = self.sim.get_current_time()

        ring_step = int(flow.metadata.get("ring_step", 0))
        delay = 1.0 if ring_step == 0 else 0.1

        def _complete(ff: Flow = flow) -> None:
            self.complete_times[int(ff.flow_id)] = self.sim.get_current_time()
            on_complete(int(ff.flow_id))

        self.sim.schedule_event(delay, _complete)


def _op_prefix(tag: str) -> str:
    return tag.split("/ring_step_", 1)[0]


def test_ring_steps_launch_only_after_prerequisite_flow_completion() -> None:
    participants = ["h0", "h1", "h2"]
    job = build_dp_heavy_workload_job(
        participants=participants,
        config=DPHeavyWorkloadConfig(
            steps=1,
            t_fwd_bwd_ms=1.0,
            num_buckets=1,
            bucket_bytes_per_participant=1024,
            algorithm=CollectiveAlgorithm.RING,
            gap_us=0.0,
            optimizer_ms=1.0,
            seed=7,
        ),
    )

    sim = DiscreteEventSimulator()
    injector = _TimedCompletionInjector(sim)
    runner = JobRunner(sim=sim, injector=injector, job=job)

    runner.run()
    sim.run()

    assert runner.metrics is not None
    assert runner.metrics.end_time is not None

    comm_phase = job.steps[0].phases[1]
    assert isinstance(comm_phase, CommPhase)
    bucket = comm_phase.buckets[0]

    predecessor_by_key: dict[tuple[str, int, str], Flow] = {}
    for flow in bucket.flows:
        if "/ring_step_" not in flow.tag:
            continue
        predecessor_by_key[(_op_prefix(flow.tag), int(flow.metadata["ring_step"]), flow.dst_node_id)] = flow

    for flow in bucket.flows:
        ring_step = int(flow.metadata.get("ring_step", 0))
        if ring_step <= 0:
            continue

        op_prefix = _op_prefix(flow.tag)
        predecessor = predecessor_by_key[(op_prefix, ring_step - 1, flow.src_node_id)]

        assert injector.inject_times[int(flow.flow_id)] >= injector.complete_times[int(predecessor.flow_id)]


def test_all_gather_step_zero_waits_for_reduce_scatter_last_arrival() -> None:
    participants = ["h0", "h1", "h2", "h3"]
    job = build_dp_heavy_workload_job(
        participants=participants,
        config=DPHeavyWorkloadConfig(
            steps=1,
            t_fwd_bwd_ms=1.0,
            num_buckets=1,
            bucket_bytes_per_participant=2048,
            algorithm=CollectiveAlgorithm.RING,
            gap_us=0.0,
            optimizer_ms=1.0,
            seed=19,
        ),
    )

    sim = DiscreteEventSimulator()
    injector = _TimedCompletionInjector(sim)
    runner = JobRunner(sim=sim, injector=injector, job=job)

    runner.run()
    sim.run()

    comm_phase = job.steps[0].phases[1]
    assert isinstance(comm_phase, CommPhase)
    bucket = comm_phase.buckets[0]

    predecessor_by_key: dict[tuple[str, int, str], Flow] = {}
    rs_max_step = -1
    for flow in bucket.flows:
        if "/ring_step_" not in flow.tag:
            continue
        step_idx = int(flow.metadata["ring_step"])
        predecessor_by_key[(_op_prefix(flow.tag), step_idx, flow.dst_node_id)] = flow
        if _op_prefix(flow.tag) == "reduce_scatter":
            rs_max_step = max(rs_max_step, step_idx)

    assert rs_max_step >= 0

    for flow in bucket.flows:
        if not flow.tag.startswith("all_gather/"):
            continue
        if int(flow.metadata.get("ring_step", -1)) != 0:
            continue
        rs_predecessor = predecessor_by_key[("reduce_scatter", rs_max_step, flow.src_node_id)]
        assert injector.inject_times[int(flow.flow_id)] >= injector.complete_times[int(rs_predecessor.flow_id)]



