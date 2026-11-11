from __future__ import annotations

import logging

from ai_factory.core.entities import CommPhase, ComputePhase, GradientBucket, TrainingJob, TrainingStep
from ai_factory.core.runner import FlowInjector, TrainingJobRunner
from ai_factory.traffic.flow import Flow
from des.des import DiscreteEventSimulator
from sim.config.loader import load_experiment_spec
from sim.runners.experiment_runner import _log_experiment_parameters, _log_results_summary


class _NoopInjector(FlowInjector):
    def inject(self, flow: Flow, *, on_complete):  # pragma: no cover - not used in this test
        on_complete(flow.flow_id)


def test_training_step_finished_log_includes_step_duration(caplog) -> None:
    sim = DiscreteEventSimulator(store_packets=False, packet_stall_percent=0.0, packet_stall_delay_s=0.0, packet_stall_max_switch_hop=0, packet_stall_retransmit_priority=False)
    job = TrainingJob(
        job_id=1,
        name="log-test",
        steps=[
            TrainingStep(
                step_id=0,
                phases=[ComputePhase(phase_id=0, name="compute", duration_s=0.005)],
            )
        ],
        participants=["h0"],
    )

    runner = TrainingJobRunner(sim=sim, injector=_NoopInjector(), job=job)

    with caplog.at_level(logging.INFO):
        runner.run()
        sim.run()

    step_finished_lines = [rec.getMessage() for rec in caplog.records if "Training step finished" in rec.getMessage()]
    assert step_finished_lines
    assert "training_step=0" in step_finished_lines[0]
    assert "duration=" in step_finished_lines[0]
    assert "ms" in step_finished_lines[0]
    assert "max_per_flow_drops=0" in step_finished_lines[0]


def test_training_step_finished_log_includes_max_per_flow_drops_for_step_flows(caplog) -> None:
    sim = DiscreteEventSimulator(store_packets=False, packet_stall_percent=0.0, packet_stall_delay_s=0.0, packet_stall_max_switch_hop=0, packet_stall_retransmit_priority=False)
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
        completion_bytes=1000,
        metadata={},
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
        completion_bytes=1000,
        metadata={},
    )
    job = TrainingJob(
        job_id=1,
        name="log-test-drops",
        steps=[
            TrainingStep(
                step_id=0,
                phases=[
                    CommPhase(
                        phase_id=1,
                        name="comm",
                        buckets=[GradientBucket(bucket_id=0, flows=[flow_a, flow_b])],
                        bucket_scheduling="concurrent",
                    )
                ],
            )
        ],
        participants=["h1", "h2", "h3"],
    )
    sim.packet_stats.dropped_count_by_flow_id[101] = 2
    sim.packet_stats.dropped_count_by_flow_id[202] = 7

    runner = TrainingJobRunner(sim=sim, injector=_NoopInjector(), job=job)

    with caplog.at_level(logging.INFO):
        runner.run()
        sim.run()

    step_finished_lines = [rec.getMessage() for rec in caplog.records if "Training step finished" in rec.getMessage()]
    assert step_finished_lines
    assert "max_per_flow_drops=7" in step_finished_lines[0]


def test_results_summary_groups_network_and_ai_factory_statistics(caplog) -> None:
    results = {
        "topology summary": {"hosts count": 16},
        "parameters summary": {"packet_stall_percent": 1.0},
        "run statistics": {
            "min packet time (s)": 0.125,
            "max packet time (s)": 1.5,
            "avg packet time (s)": 0.625,
            "some new statistic": 3,
            "packet_stall_triggered_count_by_flow_id": {1: 2},
            "ai_factory_ring_flow_time_stats": {"ring_flow_count": 4, "ring_flow_time_avg_ms": 0.5},
        },
    }

    with caplog.at_level(logging.INFO):
        _log_results_summary(results)

    messages = [rec.getMessage() for rec in caplog.records]
    network = next(m for m in messages if m.startswith("Results - network summary:"))
    ai_factory = next(m for m in messages if m.startswith("Results - AI-factory summary:"))

    assert "  topology:\n    hosts count: 16" in network
    assert (
        "  packet time (s):\n"
        "    avg packet time (s): 0.625\n"
        "    min packet time (s): 0.125\n"
        "    max packet time (s): 1.5"
    ) in network
    # Unlisted statistics are still logged; the per-flow stall map and the parameters are not.
    assert "  other:\n    some new statistic: 3" in network
    assert "packet_stall_triggered_count_by_flow_id" not in network
    assert "packet_stall_percent" not in network + ai_factory
    assert "  ring flow time (ms, sender injection to last useful packet at receiver):\n    ring_flow_count: 4" in ai_factory


def test_experiment_parameters_are_logged_one_line_per_value_by_section(caplog) -> None:
    spec = load_experiment_spec(config_path="repo:tests/fixtures/dp_small.yaml", overrides=[])

    with caplog.at_level(logging.INFO):
        _log_experiment_parameters(spec)

    (message,) = [rec.getMessage() for rec in caplog.records]
    lines = message.split("\n")
    assert lines[0].startswith("Experiment parameters (config: ")
    assert "  name: test-dp-small" in lines
    assert "  ai_workload:" in lines
    assert "    flow_redundancy_extra_packets: 0" in lines
    assert "  stall_regime:" in lines
    assert "    packet_stall_percent: 0.01" in lines
    assert "  routing:" in lines
