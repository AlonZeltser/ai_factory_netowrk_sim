from __future__ import annotations

from network.scenarios.base import Scenario

from ai_factory.core.runner import TrainingJobRunner
from ai_factory.scenarios.network_flow_injector import NetworkFlowInjector
from ai_factory.traffic.collective import CollectiveAlgorithm
from ai_factory.workloads.dp_heavy_workload import DPHeavyWorkloadConfig, build_dp_heavy_workload_job


class AIFactorySUDpHeavyScenario(Scenario):
    """Workload1 DP-heavy on the AI-Factory scale-unit topology."""

    def __init__(
        self,
        *,
        seed: int,
        num_buckets: int,
        bucket_bytes_per_participant: int,
        gap_us: float,
        t_fwd_bwd_ms: float,
        optimizer_ms: float,
        steps: int,
        mtu: int = 4096,
        flow_redundancy_extra_packets: int = 0,
        single_ring_only: bool = False,
    ):
        self.steps = int(steps)
        self.seed = seed
        self.num_buckets = num_buckets
        self.bucket_bytes_per_participant = bucket_bytes_per_participant
        self.gap_us = gap_us
        self.t_fwd_bwd_ms = t_fwd_bwd_ms
        self.optimizer_ms = optimizer_ms
        self.mtu = mtu
        self.flow_redundancy_extra_packets = flow_redundancy_extra_packets
        self.single_ring_only = single_ring_only

    def install(self, network) -> None:
        participants = sorted(network.hosts.keys())
        cfg = DPHeavyWorkloadConfig(
            steps=int(self.steps),
            num_buckets=int(self.num_buckets),
            bucket_bytes_per_participant=int(self.bucket_bytes_per_participant),
            algorithm=CollectiveAlgorithm.RING,
            gap_us=float(self.gap_us),
            seed=int(self.seed),
            t_fwd_bwd_ms=float(self.t_fwd_bwd_ms),
            optimizer_ms=float(self.optimizer_ms),
            mtu=int(self.mtu),
            flow_redundancy_extra_packets=int(self.flow_redundancy_extra_packets),
            single_ring_only=bool(self.single_ring_only),
        )
        training_job = build_dp_heavy_workload_job(participants=participants, config=cfg)

        injector = NetworkFlowInjector(network)
        runner = TrainingJobRunner(sim=network.simulator, injector=injector, job=training_job)
        metrics = runner.run()

        # Expose for downstream result collection.
        network.entities["ai_factory_training_job_metrics"] = metrics

    def parameters_summary(self):
        out = super().parameters_summary()
        out.update(
            {
                "steps": self.steps,
                "seed": self.seed,
                "num_buckets": self.num_buckets,
                "bucket_bytes_per_participant": self.bucket_bytes_per_participant,
                "gap_us": self.gap_us,
                "t_fwd_bwd_ms": self.t_fwd_bwd_ms,
                "optimizer_ms": self.optimizer_ms,
                "mtu": self.mtu,
                "flow_redundancy_extra_packets": self.flow_redundancy_extra_packets,
                "single_ring_only": self.single_ring_only,
            }
        )
        return out

