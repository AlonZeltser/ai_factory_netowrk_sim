"""Streaming packet statistics - computed without storing packets."""

from dataclasses import dataclass
from dataclasses import field
from typing import Any


@dataclass
class PacketStatistics:
    """Accumulates packet statistics incrementally without storing packet objects.

    This enables memory-efficient simulation runs with millions of packets.
    Statistics are updated as packets are created, delivered, or dropped.
    """

    total_count: int = 0
    delivered_count: int = 0
    dropped_count: int = 0
    packet_stall_marked_count: int = 0
    packet_stall_triggered_count: int = 0
    dropped_count_by_flow_id: dict[int, int] = field(default_factory=dict)
    packet_stall_triggered_count_by_flow_id: dict[int, int] = field(default_factory=dict)

    # Route length statistics
    route_length_sum: int = 0
    route_length_min: int = 999999
    route_length_max: int = 0

    def record_created(self) -> None:
        """Called when a packet is created."""
        self.total_count += 1

    def record_delivered(self, route_length: int) -> None:
        """Called when a packet is successfully delivered."""
        self.delivered_count += 1
        self.route_length_sum += route_length
        if route_length < self.route_length_min:
            self.route_length_min = route_length
        if route_length > self.route_length_max:
            self.route_length_max = route_length

    def record_dropped(self, packet: Any | None = None) -> None:
        """Called when a packet is dropped."""
        self.dropped_count += 1
        if packet is None:
            return
        try:
            flow_id = int(packet.transport_header.flow_id)
        except (AttributeError, TypeError, ValueError):
            return
        self.dropped_count_by_flow_id[flow_id] = self.dropped_count_by_flow_id.get(flow_id, 0) + 1

    def max_dropped_for_flow_ids(self, flow_ids: set[int]) -> int:
        """Return max dropped packet count among the provided flow IDs."""
        if not flow_ids:
            return 0
        return max((self.dropped_count_by_flow_id.get(fid, 0) for fid in flow_ids), default=0)

    def record_packet_stall_marked(self) -> None:
        """Called when a packet is tagged for a future switch stall."""
        self.packet_stall_marked_count += 1

    def record_packet_stall_triggered(self, packet: Any | None = None) -> None:
        """Called when a tagged packet actually hits its configured switch stall hop."""
        self.packet_stall_triggered_count += 1
        if packet is None:
            return
        try:
            flow_id = int(packet.transport_header.flow_id)
        except (AttributeError, TypeError, ValueError):
            return
        self.packet_stall_triggered_count_by_flow_id[flow_id] = self.packet_stall_triggered_count_by_flow_id.get(flow_id, 0) + 1

    @property
    def avg_route_length(self) -> float:
        """Average route length of delivered packets."""
        return (
            self.route_length_sum / self.delivered_count
            if self.delivered_count > 0
            else 0.0
        )

    @property
    def min_route_length(self) -> int:
        """Minimum route length of delivered packets."""
        return self.route_length_min if self.route_length_min != 999999 else 0

    @property
    def max_route_length(self) -> int:
        """Maximum route length of delivered packets."""
        return self.route_length_max
# packet_statistics.py placeholder
