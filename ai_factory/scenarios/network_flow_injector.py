from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from network.core.packet import Protocol

from ai_factory.core.entities import FlowMetrics
from ai_factory.core.runner import FlowInjector
from ai_factory.traffic.flow import Flow


@dataclass
class _FlowDeliveryState:
    dst_ip: str
    useful_packet_count: int
    gross_packet_count: int
    delivered_packet_count: int
    latest_valuable_arrival_time: float
    latest_valuable_packet_start_time: float | None
    latest_valuable_packet_end_time: float | None
    latest_valuable_packet_egress_positions: list[int]
    all_observed_egress_positions: list[int]


class NetworkFlowInjector(FlowInjector):
    """Adapter: Flow -> Host.send_message + completion callback.

    Keeps the AI-factory layer packet-agnostic.
    """

    def __init__(self, network):
        self._network = network
        self._callbacks: dict[int, Callable[[int], None]] = {}
        self._stats: dict[int, _FlowDeliveryState] = {}
        self._flows: dict[int, Flow] = {}
        self._start_times: dict[int, float] = {}
        self._deep_flow_chain_log = bool(self._network.entities.get("deep_flow_chain_log"))

        # Wrap hosts' on_message to detect per-flow completion.
        for host in self._network.hosts.values():
            original = host.on_message

            def wrapped(packet, *, _orig=original):
                _orig(packet)

                flow_id = int(packet.transport_header.flow_id)
                stat = self._stats.get(flow_id)
                if stat is None:
                    return

                # Count bytes only at the final destination host.
                if packet.routing_header.five_tuple.dst_ip != stat.dst_ip:
                    return

                stat.delivered_packet_count += 1
                if self._deep_flow_chain_log and stat.delivered_packet_count <= stat.useful_packet_count:
                    egress_positions = list(packet.tracking_info.egress_queue_positions)
                    stat.all_observed_egress_positions.extend(egress_positions)
                    arrival_time = float(self._network.simulator.get_current_time())
                    if arrival_time >= stat.latest_valuable_arrival_time:
                        stat.latest_valuable_arrival_time = arrival_time
                        stat.latest_valuable_packet_start_time = float(packet.tracking_info.birth_time)
                        stat.latest_valuable_packet_end_time = arrival_time
                        stat.latest_valuable_packet_egress_positions = egress_positions

                if stat.delivered_packet_count >= stat.useful_packet_count:
                    flow = self._flows.pop(flow_id, None)
                    start_time = self._start_times.pop(flow_id, None)
                    cb = self._callbacks.pop(flow_id, None)
                    self._stats.pop(flow_id, None)
                    if flow is not None and start_time is not None:
                        completion_time = float(self._network.simulator.get_current_time())
                        self._network.entities.setdefault("ai_factory_flow_metrics", []).append(
                            FlowMetrics(
                                flow_id=int(flow.flow_id),
                                job_id=int(flow.job_id),
                                step_id=int(flow.step_id),
                                phase_id=int(flow.phase_id),
                                bucket_id=flow.bucket_id,
                                tag=flow.tag,
                                src_node_id=flow.src_node_id,
                                dst_node_id=flow.dst_node_id,
                                start_time=float(start_time),
                                end_time=completion_time,
                                transmitted_bytes=int(flow.size_bytes),
                                useful_bytes=int(flow.useful_size_bytes),
                            )
                        )
                        if self._deep_flow_chain_log:
                            stall_counts = getattr(self._network.simulator.packet_stats, "packet_stall_triggered_count_by_flow_id", {})
                            packets_stalled = int(stall_counts.get(flow_id, 0)) if isinstance(stall_counts, dict) else 0
                            gross_packets = max(1, int(stat.gross_packet_count))
                            egress_values = stat.all_observed_egress_positions
                            avg_place = (float(sum(egress_values)) / float(len(egress_values))) if egress_values else 0.0
                            self._network.entities.setdefault("ai_factory_flow_chain_diagnostics", []).append(
                                {
                                    "flow_id": int(flow.flow_id),
                                    "job_id": int(flow.job_id),
                                    "step_id": int(flow.step_id),
                                    "phase_id": int(flow.phase_id),
                                    "bucket_id": flow.bucket_id,
                                    "tag": str(flow.tag),
                                    "op_tag": str(flow.tag).split("/", 1)[0],
                                    "ring_step": int(flow.metadata.get("ring_step", -1)) if "ring_step" in flow.metadata else None,
                                    "src_node_id": str(flow.src_node_id),
                                    "dst_node_id": str(flow.dst_node_id),
                                    "sim_start_time": float(start_time),
                                    "sim_end_time": completion_time,
                                    "sim_duration": completion_time - float(start_time),
                                    "packets_stalled": packets_stalled,
                                    "net_packets_in_flow": int(stat.useful_packet_count),
                                    "gross_packets_in_flow": int(stat.gross_packet_count),
                                    "stall_percentage": (float(packets_stalled) / float(gross_packets)) * 100.0,
                                    "max_place_in_egress": int(max(egress_values, default=0)),
                                    "avg_place_in_egress": avg_place,
                                    "latest_valuable_packet_start_time": stat.latest_valuable_packet_start_time,
                                    "latest_valuable_packet_end_time": stat.latest_valuable_packet_end_time,
                                    "latest_valuable_packet_egress_values": list(stat.latest_valuable_packet_egress_positions),
                                    "latest_valuable_packet_egress_sum": int(sum(stat.latest_valuable_packet_egress_positions)),
                                }
                            )
                    if cb is not None:
                        cb(flow_id)

            host.on_message = wrapped  # type: ignore[assignment]

    def inject(self, flow: Flow, *, on_complete: Callable[[int], None]):
        src = self._network.get_entity(flow.src_node_id)
        dst = self._network.get_entity(flow.dst_node_id)
        flow_id = int(flow.flow_id)

        self._callbacks[flow_id] = on_complete
        mtu = max(1, int(getattr(src, "mtu", 1500) or 1500))
        useful_packet_count = max(1, int(math.ceil(float(int(flow.useful_size_bytes)) / float(mtu))))
        gross_packet_count = max(1, int(math.ceil(float(int(flow.size_bytes)) / float(mtu))))
        self._stats[flow_id] = _FlowDeliveryState(
            dst_ip=dst.ip_address,
            useful_packet_count=useful_packet_count,
            gross_packet_count=gross_packet_count,
            delivered_packet_count=0,
            latest_valuable_arrival_time=-1.0,
            latest_valuable_packet_start_time=None,
            latest_valuable_packet_end_time=None,
            latest_valuable_packet_egress_positions=[],
            all_observed_egress_positions=[],
        )
        self._flows[flow_id] = flow
        self._start_times[flow_id] = float(self._network.simulator.get_current_time())

        src.send_message(
            session_id=flow_id,
            dst_ip_address=dst.ip_address,
            source_port=1000,
            dest_port=2000,
            size_bytes=int(flow.size_bytes),
            protocol=Protocol.TCP,
        )


