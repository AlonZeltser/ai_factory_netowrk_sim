from __future__ import annotations

import logging

from ai_factory.core.entities import Bucket, CommPhase, ComputePhase, Job, JobStep
from ai_factory.core.runner import FlowInjector, JobRunner
from ai_factory.traffic.flow import Flow
from des.des import DiscreteEventSimulator
from sim.runners.experiment_runner import _log_results_summary


class _NoopInjector(FlowInjector):
    def inject(self, flow: Flow, *, on_complete):  # pragma: no cover - not used in this test
        on_complete(flow.flow_id)


def test_step_finished_log_includes_step_duration(caplog) -> None:
    sim = DiscreteEventSimulator()
    job = Job(
        job_id=1,
        name="log-test",
        steps=[
            JobStep(
                step_id=0,
                phases=[ComputePhase(phase_id=0, name="compute", duration_s=0.005)],
            )
        ],
        participants=["h0"],
    )

    runner = JobRunner(sim=sim, injector=_NoopInjector(), job=job)

    with caplog.at_level(logging.INFO):
        runner.run()
        sim.run()

    step_finished_lines = [rec.getMessage() for rec in caplog.records if "Step finished" in rec.getMessage()]
    assert step_finished_lines
    assert "step=0" in step_finished_lines[0]
    assert "duration=" in step_finished_lines[0]
    assert "ms" in step_finished_lines[0]
    assert "max_per_flow_drops=0" in step_finished_lines[0]


def test_step_finished_log_includes_max_per_flow_drops_for_step_flows(caplog) -> None:
    sim = DiscreteEventSimulator()
    flow_a = Flow(
        flow_id=101,
        job_id=1,
        step_id=0,
        phase_id=1,
        bucket_id=0,
        tag="test",
        src_node_id="h1",
        dst_node_id="h2",
        size_bytes=1000,
        start_time=0.0,
    )
    flow_b = Flow(
        flow_id=202,
        job_id=1,
        step_id=0,
        phase_id=1,
        bucket_id=0,
        tag="test",
        src_node_id="h2",
        dst_node_id="h3",
        size_bytes=1000,
        start_time=0.0,
    )
    job = Job(
        job_id=1,
        name="log-test-drops",
        steps=[
            JobStep(
                step_id=0,
                phases=[
                    CommPhase(
                        phase_id=1,
                        name="comm",
                        buckets=[Bucket(bucket_id=0, flows=[flow_a, flow_b])],
                    )
                ],
            )
        ],
        participants=["h1", "h2", "h3"],
    )
    sim.packet_stats.dropped_count_by_flow_id[101] = 2
    sim.packet_stats.dropped_count_by_flow_id[202] = 7

    runner = JobRunner(sim=sim, injector=_NoopInjector(), job=job)

    with caplog.at_level(logging.INFO):
        runner.run()
        sim.run()

    step_finished_lines = [rec.getMessage() for rec in caplog.records if "Step finished" in rec.getMessage()]
    assert step_finished_lines
    assert "max_per_flow_drops=7" in step_finished_lines[0]


def test_results_summary_logs_packet_time_statistics(caplog) -> None:
    results = {
        "topology summary": {},
        "parameters summary": {},
        "run statistics": {
            "min packet time (s)": 0.125,
            "max packet time (s)": 1.5,
            "avg packet time (s)": 0.625,
        },
    }

    with caplog.at_level(logging.INFO):
        _log_results_summary(results)

    packet_time_lines = [rec.getMessage() for rec in caplog.records if "Packet time statistics" in rec.getMessage()]
    assert packet_time_lines
    assert "min=0.125000" in packet_time_lines[0]
    assert "max=1.500000" in packet_time_lines[0]
    assert "avg=0.625000" in packet_time_lines[0]


