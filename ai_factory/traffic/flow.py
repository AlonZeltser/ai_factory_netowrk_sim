from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Flow:
    """A bulk transfer request emitted by the AI-factory layer.

    Packet-agnostic: the network simulator decides packetization, routing, congestion, etc.
    """

    flow_id: int
    job_id: int
    step_id: int
    phase_id: int
    bucket_id: int | None
    tag: str

    src_node_id: str
    dst_node_id: str
    size_bytes: int
    start_time: float
    completion_bytes: int | None = None

    priority: int | None = None
    deadline: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def useful_size_bytes(self) -> int:
        return int(self.completion_bytes if self.completion_bytes is not None else self.size_bytes)

    def signature_tuple(self) -> tuple:
        return (self.src_node_id, self.dst_node_id, int(self.size_bytes), float(self.start_time), self.tag)


def apply_chunk_redundancy(flows: list[Flow], *, extra_packets: int, mtu: int) -> list[Flow]:
    """Add exactly `extra_packets` redundant packets on top of the useful payload.

    Validates that each flow's payload is a whole number of packets (size_bytes % mtu == 0).
    When extra_packets == 0 the original list is returned unchanged.
    """
    if extra_packets <= 0:
        return flows

    if mtu <= 0:
        raise ValueError(f"mtu must be > 0, got {mtu}")

    out: list[Flow] = []
    for flow in flows:
        useful_bytes = int(flow.useful_size_bytes)
        if useful_bytes % mtu != 0:
            raise ValueError(
                f"Flow {flow.flow_id} useful_size_bytes={useful_bytes} is not a whole number "
                f"of packets (mtu={mtu}). Remainder={useful_bytes % mtu}."
            )
        gross_bytes = useful_bytes + int(extra_packets) * int(mtu)
        out.append(
            Flow(
                flow_id=int(flow.flow_id),
                job_id=int(flow.job_id),
                step_id=int(flow.step_id),
                phase_id=int(flow.phase_id),
                bucket_id=flow.bucket_id,
                tag=flow.tag,
                src_node_id=flow.src_node_id,
                dst_node_id=flow.dst_node_id,
                size_bytes=gross_bytes,
                completion_bytes=useful_bytes,
                start_time=float(flow.start_time),
                priority=flow.priority,
                deadline=flow.deadline,
                metadata={**dict(flow.metadata), "chunk_redundancy_extra_packets": int(extra_packets)},
            )
        )
    return out


