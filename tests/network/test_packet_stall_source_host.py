import pytest

from des.des import DiscreteEventSimulator
from network.core.network_node import RoutingMode
from network.core.packet import FiveTupleExt, Packet, PacketL3, PacketTrackingInfo, PacketTransport, Protocol
from network.core.switch import Switch


def test_stalled_packet_without_registered_source_host_raises() -> None:
    sim = DiscreteEventSimulator(
        store_packets=False,
        packet_stall_percent=100.0,
        packet_stall_delay_s=0.05,
        packet_stall_max_switch_hop=0,
        packet_stall_retransmit_priority=False,
    )
    switch = Switch(
        "s1",
        ports_count=1,
        scheduler=sim,
        routing_mode=RoutingMode.ECMP,
        message_verbose=False,
        verbose_route=False,
    )
    tracking = PacketTrackingInfo(global_id=1, birth_time=0.0, initial_ttl=16, route_length=0, verbose_route=None)
    tracking.packet_stall_target_switch_hop = 0  # stall at the first switch
    packet = Packet(
        routing_header=PacketL3(
            five_tuple=FiveTupleExt("10.9.9.9", "10.0.0.2", 1000, 2000, Protocol.UDP, 0),
            seq_number=0,
            size_bytes=100,
            ttl=16,
        ),
        transport_header=PacketTransport(flow_id=1, flow_count=1, flow_seq=0),
        tracking_info=tracking,
    )

    with pytest.raises(LookupError, match="no host is registered for its source IP 10.9.9.9"):
        switch.on_message(packet)
