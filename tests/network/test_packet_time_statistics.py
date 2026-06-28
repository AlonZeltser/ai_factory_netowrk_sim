from __future__ import annotations

from des.des import DiscreteEventSimulator
from network.core.host import Host
from network.core.network_node import RoutingMode
from network.core.packet import FiveTupleExt, Packet, PacketL3, PacketTrackingInfo, PacketTransport, Protocol


def _packet(*, global_id: int, birth_time: float, route_length: int) -> Packet:
    return Packet(
        routing_header=PacketL3(
            five_tuple=FiveTupleExt("10.0.0.1", "10.0.0.2", 1111, 2222, Protocol.UDP, 0),
            seq_number=global_id,
            size_bytes=100,
            ttl=64,
        ),
        transport_header=PacketTransport(flow_id=1, flow_count=2, flow_seq=global_id),
        tracking_info=PacketTrackingInfo(
            global_id=global_id,
            birth_time=birth_time,
            route_length=route_length,
        ),
    )


def test_host_on_message_records_packet_time_statistics() -> None:
    sim = DiscreteEventSimulator()
    host = Host(
        name="dst",
        scheduler=sim,
        ip_address="10.0.0.2",
        message_verbose=False,
        verbose_route=False,
        max_path=None,
        ports_count=1,
        routing_mode=RoutingMode.ECMP,
        ecmp_flowlet_n_packets=0,
        mtu=1500,
        ttl=64,
    )

    sim.current_time = 1.25
    host.on_message(_packet(global_id=1, birth_time=0.5, route_length=3))

    sim.current_time = 2.0
    host.on_message(_packet(global_id=2, birth_time=1.0, route_length=4))

    stats = sim.packet_stats
    assert stats.delivered_count == 2
    assert stats.min_packet_time == 0.75
    assert stats.max_packet_time == 1.0
    assert stats.avg_packet_time == 0.875
    assert stats.min_route_length == 3
    assert stats.max_route_length == 4


