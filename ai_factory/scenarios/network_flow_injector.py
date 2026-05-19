from __future__ import annotations

from typing import Callable

from network.core.packet import Protocol

from ai_factory.core.entities import FlowMetrics
from ai_factory.core.runner import FlowInjector
from ai_factory.traffic.flow import Flow


class NetworkFlowInjector(FlowInjector):
    """Adapter: Flow -> Host.send_message + completion callback.

    Keeps the AI-factory layer packet-agnostic.
    """

    def __init__(self, network):
        self._network = network
        self._callbacks: dict[int, Callable[[int], None]] = {}
        # flow_id -> (dst_ip, completion_bytes, received_bytes)
        self._stats: dict[int, tuple[str, int, int]] = {}
        self._flows: dict[int, Flow] = {}
        self._start_times: dict[int, float] = {}

        # Wrap hosts' on_message to detect per-flow completion.
        for host in self._network.hosts.values():
            original = host.on_message

            def wrapped(packet, *, _orig=original):
                _orig(packet)

                flow_id = int(packet.transport_header.flow_id)
                stat = self._stats.get(flow_id)
                if stat is None:
                    return

                dst_ip, expected, received = stat

                # Count bytes only at the final destination host.
                if packet.routing_header.five_tuple.dst_ip != dst_ip:
                    return

                received += int(packet.routing_header.size_bytes)
                if received >= expected:
                    flow = self._flows.pop(flow_id, None)
                    start_time = self._start_times.pop(flow_id, None)
                    cb = self._callbacks.pop(flow_id, None)
                    self._stats.pop(flow_id, None)
                    if flow is not None and start_time is not None:
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
                                end_time=float(self._network.simulator.get_current_time()),
                                transmitted_bytes=int(flow.size_bytes),
                                useful_bytes=int(flow.useful_size_bytes),
                            )
                        )
                    if cb is not None:
                        cb(flow_id)
                else:
                    self._stats[flow_id] = (dst_ip, expected, received)

            host.on_message = wrapped  # type: ignore[assignment]

    def inject(self, flow: Flow, *, on_complete: Callable[[int], None]):
        src = self._network.get_entity(flow.src_node_id)
        dst = self._network.get_entity(flow.dst_node_id)
        flow_id = int(flow.flow_id)

        self._callbacks[flow_id] = on_complete
        self._stats[flow_id] = (dst.ip_address, int(flow.useful_size_bytes), 0)
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


