from __future__ import annotations

from ai_factory.core.entities import CommPhase
from ai_factory.traffic.collective import CollectiveAlgorithm
from ai_factory.traffic.flow import Flow, apply_chunk_redundancy
from ai_factory.workloads.mixed_workload import (
    MixedScenarioPpDpConfig,
    MixedScenarioTpHeavyConfig,
    build_mixed_scenario_pp_dp,
    build_mixed_scenario_tp_heavy,
)
from ai_factory.workloads.dp_heavy_workload import DPHeavyWorkloadConfig, build_dp_heavy_workload_job


def test_apply_chunk_redundancy_preserves_useful_bytes() -> None:
    mtu = 100
    flows = [
        Flow(
            flow_id=1,
            job_id=1,
            step_id=0,
            phase_id=0,
            bucket_id=0,
            tag="test",
            src_node_id="h1",
            dst_node_id="h2",
            size_bytes=800,
            start_time=0.0,
        )
    ]

    redundant = apply_chunk_redundancy(flows, extra_packets=2, mtu=mtu)

    assert len(redundant) == 1
    assert redundant[0].size_bytes == 1000  # 800 + 2*100
    assert redundant[0].useful_size_bytes == 800
    assert redundant[0].metadata["chunk_redundancy_extra_packets"] == 2


def test_dp_heavy_job_marks_comm_flows_complete_after_useful_bytes() -> None:
    job = build_dp_heavy_workload_job(
        participants=["h1", "h2", "h3", "h4"],
        config=DPHeavyWorkloadConfig(
            steps=1,
            t_fwd_bwd_ms=1.0,
            num_buckets=1,
            bucket_bytes_per_participant=1024,
            algorithm=CollectiveAlgorithm.RING,
            gap_us=0.0,
            optimizer_ms=1.0,
            seed=7,
            mtu=256,
            chunk_redundancy_extra_packets=1,
        ),
    )

    comm_phase = job.steps[0].phases[1]
    assert isinstance(comm_phase, CommPhase)
    assert comm_phase.buckets
    assert any(flow.size_bytes > flow.useful_size_bytes for flow in comm_phase.buckets[0].flows)
    assert all(flow.useful_size_bytes > 0 for flow in comm_phase.buckets[0].flows)


def test_dp_heavy_single_ring_only_skips_all_gather_flows() -> None:
    job = build_dp_heavy_workload_job(
        participants=["h1", "h2", "h3", "h4"],
        config=DPHeavyWorkloadConfig(
            steps=1,
            t_fwd_bwd_ms=1.0,
            num_buckets=1,
            bucket_bytes_per_participant=1024,
            algorithm=CollectiveAlgorithm.RING,
            gap_us=0.0,
            optimizer_ms=1.0,
            seed=7,
            single_ring_only=True,
        ),
    )

    comm_phase = job.steps[0].phases[1]
    assert isinstance(comm_phase, CommPhase)
    tags = [flow.tag for flow in comm_phase.buckets[0].flows]
    assert tags
    assert all(tag.startswith("reduce_scatter/") for tag in tags)


def test_mixed_jobs_apply_chunk_redundancy_to_tp_and_pp_flows() -> None:
    tp_job = build_mixed_scenario_tp_heavy(
        participants=["h1", "h2", "h3", "h4"],
        config=MixedScenarioTpHeavyConfig(
            steps=1,
            seed=11,
            traffic_scale=1.0,
            fwd_compute_ms=1.0,
            micro_collectives=1,
            micro_collective_bytes_per_participant=2048,
            micro_compute_gap_ms=0.1,
            final_sync_bytes_per_participant=4096,
            tail_compute_ms=0.2,
            gap_us=0.0,
            algorithm=CollectiveAlgorithm.RING,
            mtu=512,
            chunk_redundancy_extra_packets=2,
        ),
    )
    tp_comm_phases = [phase for phase in tp_job.steps[0].phases if isinstance(phase, CommPhase)]
    assert tp_comm_phases
    assert any(flow.size_bytes > flow.useful_size_bytes for phase in tp_comm_phases for bucket in phase.buckets for flow in bucket.flows)

    pp_job = build_mixed_scenario_pp_dp(
        participants=["p0", "p1", "p2", "p3"],
        stage_nodes=[["p0"], ["p1"], ["p2"], ["p3"]],
        config=MixedScenarioPpDpConfig(
            steps=1,
            seed=13,
            traffic_scale=1.0,
            microbatch_count=1,
            microbatch_gap_us=1.0,
            activation_bytes_per_microbatch=2048,
            grad_bytes_per_microbatch=1024,
            dp_sync_bytes_per_participant=4096,
            tail_compute_ms=0.2,
            mtu=512,
            chunk_redundancy_extra_packets=2,
        ),
    )
    pp_comm_phases = [phase for phase in pp_job.steps[0].phases if isinstance(phase, CommPhase)]
    assert pp_comm_phases
    assert any(flow.size_bytes > flow.useful_size_bytes for phase in pp_comm_phases for bucket in phase.buckets for flow in bucket.flows)

