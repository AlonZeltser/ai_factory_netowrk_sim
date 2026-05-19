from __future__ import annotations

import math
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


def apply_chunk_redundancy(flows: list[Flow], *, extra_percent: float) -> list[Flow]:
    if extra_percent <= 0.0:
        return flows

    multiplier = 1.0 + (float(extra_percent) / 100.0)
    out: list[Flow] = []
    for flow in flows:
        useful_bytes = int(flow.useful_size_bytes)
        redundant_bytes = max(useful_bytes, int(math.ceil(useful_bytes * multiplier)))
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
                size_bytes=redundant_bytes,
                completion_bytes=useful_bytes,
                start_time=float(flow.start_time),
                priority=flow.priority,
                deadline=flow.deadline,
                metadata={**dict(flow.metadata), "chunk_redundancy_percent": float(extra_percent)},
            )
        )
    return out


