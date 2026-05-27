from __future__ import annotations

import logging

from ai_factory.core.entities import ComputePhase, Job, JobStep
from ai_factory.core.runner import FlowInjector, JobRunner
from ai_factory.traffic.flow import Flow
from des.des import DiscreteEventSimulator


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

