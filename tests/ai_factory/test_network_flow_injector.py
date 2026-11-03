from __future__ import annotations

from network.core.packet import FiveTupleExt, Packet, PacketL3, PacketTrackingInfo, PacketTransport, Protocol

from ai_factory.scenarios.network_flow_injector import NetworkFlowInjector
from ai_factory.traffic.flow import Flow


class _PacketStats:
    packet_stall_triggered_count_by_flow_id: dict[int, int] = {}


class _Simulator:
    def __init__(self) -> None:
        self.time = 0.0
        self.packet_stats = _PacketStats()

    def get_current_time(self) -> float:
        return self.time


class _Host:
    def __init__(self, name: str, ip_address: str, mtu: int) -> None:
        self.name = name
        self.ip_address = ip_address
        self.mtu = mtu
        self.sent_messages: list[dict] = []

    def on_message(self, packet: Packet) -> None:
        packet.delivered = True
        packet.arrival_time = 0.0

    def send_message(self, **kwargs) -> None:
        self.sent_messages.append(kwargs)


class _Network:
    def __init__(self) -> None:
        self.simulator = _Simulator()
        self.entities: dict = {"deep_flow_chain_log": True}
        self.src = _Host("src", "10.0.0.1", mtu=100)
        self.dst = _Host("dst", "10.0.0.2", mtu=100)
        self.hosts = {"src": self.src, "dst": self.dst}

    def get_entity(self, node_id: str) -> _Host:
        return self.hosts[node_id]


def _packet(
    *,
    flow_id: int,
    flow_seq: int,
    src_ip: str,
    dst_ip: str,
    birth_time: float,
    is_retransmit: bool,
) -> Packet:
    return Packet(
        routing_header=PacketL3(
            five_tuple=FiveTupleExt(src_ip, dst_ip, 1000, 2000, Protocol.TCP, 0),
            seq_number=flow_seq,
            size_bytes=100,
            ttl=64,
        ),
        transport_header=PacketTransport(flow_id=flow_id, flow_count=4, flow_seq=flow_seq),
        tracking_info=PacketTrackingInfo(
            global_id=flow_seq,
            birth_time=birth_time,
            egress_queue_positions=[flow_seq + 1],
            is_retransmit=is_retransmit,
            initial_ttl=0,
            route_length=0,
            verbose_route=None,
        ),
    )


def test_redundant_packets_count_toward_flow_completion_after_any_n_arrivals() -> None:
    network = _Network()
    injector = NetworkFlowInjector(network)
    completed: list[int] = []
    flow = Flow(
        flow_id=7,
        job_id=1,
        step_id=0,
        phase_id=1,
        bucket_id=0,
        tag="reduce_scatter/ring_step_0",
        src_node_id="src",
        dst_node_id="dst",
        size_bytes=400,
        completion_bytes=200,
        start_time=0.0,
        metadata={},
    )

    injector.inject(flow, on_complete=lambda flow_id: completed.append(flow_id))

    network.simulator.time = 1.0
    network.dst.on_message(_packet(flow_id=7, flow_seq=2, src_ip=network.src.ip_address, dst_ip=network.dst.ip_address, birth_time=0.0, is_retransmit=False))
    assert completed == []

    network.simulator.time = 2.0
    network.dst.on_message(_packet(flow_id=7, flow_seq=3, src_ip=network.src.ip_address, dst_ip=network.dst.ip_address, birth_time=0.0, is_retransmit=False))

    assert completed == [7]
    metrics = network.entities["ai_factory_flow_metrics"]
    assert len(metrics) == 1
    assert metrics[0].end_time == 2.0
    assert metrics[0].transmitted_bytes == 400
    assert metrics[0].useful_bytes == 200
    diagnostics = network.entities["ai_factory_flow_chain_diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["net_packets_in_flow"] == 2
    assert diagnostics[0]["gross_packets_in_flow"] == 4
    assert diagnostics[0]["latest_valuable_packet_end_time"] == 2.0

    network.simulator.time = 3.0
    network.dst.on_message(_packet(flow_id=7, flow_seq=0, src_ip=network.src.ip_address, dst_ip=network.dst.ip_address, birth_time=0.0, is_retransmit=False))
    assert completed == [7]
    assert len(network.entities["ai_factory_flow_metrics"]) == 1


def test_retransmit_packets_are_excluded_from_deep_flow_egress_diagnostics() -> None:
    network = _Network()
    injector = NetworkFlowInjector(network)
    completed: list[int] = []
    flow = Flow(
        flow_id=8,
        job_id=1,
        step_id=0,
        phase_id=1,
        bucket_id=0,
        tag="reduce_scatter/ring_step_0",
        src_node_id="src",
        dst_node_id="dst",
        size_bytes=400,
        completion_bytes=200,
        start_time=0.0,
        metadata={},
    )

    injector.inject(flow, on_complete=lambda flow_id: completed.append(flow_id))

    network.simulator.time = 1.0
    network.dst.on_message(
        _packet(
            flow_id=8,
            flow_seq=0,
            src_ip=network.src.ip_address,
            dst_ip=network.dst.ip_address,
            is_retransmit=True,
            birth_time=0.0,
        )
    )
    assert completed == []

    network.simulator.time = 2.0
    network.dst.on_message(_packet(flow_id=8, flow_seq=2, src_ip=network.src.ip_address, dst_ip=network.dst.ip_address, birth_time=0.0, is_retransmit=False))
    assert completed == [8]

    diagnostics = network.entities["ai_factory_flow_chain_diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["max_place_in_egress"] == 3
    assert diagnostics[0]["avg_place_in_egress"] == 3.0
    assert diagnostics[0]["latest_valuable_packet_egress_values"] == [3]
    assert diagnostics[0]["latest_valuable_packet_egress_sum"] == 3


