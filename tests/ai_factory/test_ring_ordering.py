from __future__ import annotations

import re

from ai_factory.core.entities import CommPhase
from ai_factory.traffic.collective import CollectiveAlgorithm
from ai_factory.traffic.patterns.ring import build_ring_order
from ai_factory.workloads.dp_heavy_workload import DPHeavyWorkloadConfig, build_dp_heavy_workload_job


def _leaf_key(host_id: str) -> int:
    m = re.search(r"leaf(\d+)", host_id)
    assert m is not None
    return int(m.group(1))


def test_build_ring_order_keeps_hosts_chain_within_leaf() -> None:
    participants = [
        "su1_leaf2_srv1",
        "su1_leaf0_srv1",
        "su1_leaf1_srv0",
        "su1_leaf2_srv0",
        "su1_leaf0_srv0",
        "su1_leaf1_srv1",
    ]

    ring = build_ring_order(participants, seed=2026)

    by_leaf: dict[int, list[str]] = {}
    for host in ring.participants:
        by_leaf.setdefault(_leaf_key(host), []).append(host)

    for hosts in by_leaf.values():
        assert hosts == sorted(hosts)

    for leaf in sorted(by_leaf.keys()):
        idxs = [i for i, host in enumerate(ring.participants) if _leaf_key(host) == leaf]
        assert idxs == list(range(idxs[0], idxs[-1] + 1))


def test_dp_heavy_ring_order_is_step_stable_and_varies_across_steps() -> None:
    participants = [f"su1_leaf{leaf}_srv{srv}" for leaf in range(8) for srv in range(2)]
    cfg = DPHeavyWorkloadConfig(
        steps=2,
        t_fwd_bwd_ms=1.0,
        num_buckets=2,
        bucket_bytes_per_participant=8 * 1024,
        algorithm=CollectiveAlgorithm.RING,
        gap_us=10.0,
        optimizer_ms=1.0,
        seed=12345,
    )
    job = build_dp_heavy_workload_job(participants=participants, config=cfg)

    def first_step_pairs(*, step_id: int, bucket_id: int, op_prefix: str) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        comm_phase = job.steps[step_id].phases[1]
        assert isinstance(comm_phase, CommPhase)
        for flow in comm_phase.buckets[bucket_id].flows:
            if flow.tag.startswith(op_prefix) and flow.metadata.get("ring_step") == 0:
                pairs.append((flow.src_node_id, flow.dst_node_id))
        return sorted(pairs)

    step0_rs_b0 = first_step_pairs(step_id=0, bucket_id=0, op_prefix="reduce_scatter")
    step0_ag_b0 = first_step_pairs(step_id=0, bucket_id=0, op_prefix="all_gather")
    step0_rs_b1 = first_step_pairs(step_id=0, bucket_id=1, op_prefix="reduce_scatter")
    step0_ag_b1 = first_step_pairs(step_id=0, bucket_id=1, op_prefix="all_gather")

    assert step0_rs_b0 == step0_ag_b0
    assert step0_rs_b0 == step0_rs_b1
    assert step0_rs_b0 == step0_ag_b1

    step1_rs_b0 = first_step_pairs(step_id=1, bucket_id=0, op_prefix="reduce_scatter")
    assert step1_rs_b0 != step0_rs_b0


