"""Tests for the packet_stall_retransmit_priority feature.

When the flag is enabled, packets reinjected from the source host after a stall
(is_retransmit=True) bypass regular packets in the egress queue: they are placed
in a separate high-priority FIFO that is drained before the regular FIFO.
"""
import unittest
from collections import deque

from des.des import DiscreteEventSimulator
from network.core.host import Host
from network.core.link import Link
from network.core.network_node import RoutingMode
from network.core.packet import (
    FiveTupleExt, PacketL3, PacketTrackingInfo, PacketTransport, Packet, Protocol,
)
from network.core.port import Port
from network.core.switch import Switch


def _make_sim(*, retransmit_priority: bool) -> DiscreteEventSimulator:
    sim = DiscreteEventSimulator(store_packets=False)
    sim.packet_stall_retransmit_priority = retransmit_priority
    return sim


def _make_packet(sim: DiscreteEventSimulator, global_id: int, *, is_retransmit: bool) -> Packet:
    ft = FiveTupleExt("10.0.0.1", "10.0.0.2", 1000, 80, Protocol.UDP, 0)
    header = PacketL3(five_tuple=ft, seq_number=global_id, size_bytes=128, ttl=64)
    transport = PacketTransport(flow_id=1, flow_count=1, flow_seq=global_id)
    tracking = PacketTrackingInfo(
        global_id=global_id,
        birth_time=sim.get_current_time(),
        initial_ttl=64,
        is_retransmit=is_retransmit,
        route_length=0,
        verbose_route=None,
    )
    return Packet(routing_header=header, transport_header=transport, tracking_info=tracking)


class TestRetransmitPriorityQueueUnit(unittest.TestCase):
    """Unit-level tests on Port directly, without running the DES."""

    def _make_port(self, *, priority: bool) -> Port:
        sim = _make_sim(retransmit_priority=priority)
        h = Host(
            name="h",
            scheduler=sim,
            ip_address="10.0.0.1",
            message_verbose=False,
            verbose_route=False,
            max_path=10,
            ports_count=1,
            routing_mode=RoutingMode.ECMP,
            ecmp_flowlet_n_packets=0,
            mtu=4096,
            ttl=64,
        )
        h2 = Host(
            name="h2",
            scheduler=sim,
            ip_address="10.0.0.2",
            message_verbose=False,
            verbose_route=False,
            max_path=10,
            ports_count=1,
            routing_mode=RoutingMode.ECMP,
            ecmp_flowlet_n_packets=0,
            mtu=4096,
            ttl=64,
        )
        link = Link("l", sim, bandwidth_bps=1e6, propagation_time=0.0)
        h.connect(1, link)
        h2.connect(1, link)
        return h.ports[0]

    def test_regular_packet_goes_to_egress_queue_when_priority_off(self):
        port = self._make_port(priority=False)
        pkt = _make_packet(port.owner.scheduler, 1, is_retransmit=False)
        # prevent actual draining
        port._drain_scheduled = True
        port.enqueue(pkt)
        self.assertEqual(len(port.egress_queue), 1)
        self.assertEqual(len(port.priority_queue), 0)

    def test_retransmit_packet_still_goes_to_egress_queue_when_priority_off(self):
        """With flag off, retransmit packets must NOT get any special treatment."""
        port = self._make_port(priority=False)
        pkt = _make_packet(port.owner.scheduler, 2, is_retransmit=True)
        port._drain_scheduled = True
        port.enqueue(pkt)
        self.assertEqual(len(port.egress_queue), 1)
        self.assertEqual(len(port.priority_queue), 0)

    def test_retransmit_packet_goes_to_priority_queue_when_flag_on(self):
        port = self._make_port(priority=True)
        pkt = _make_packet(port.owner.scheduler, 3, is_retransmit=True)
        port._drain_scheduled = True
        port.enqueue(pkt)
        self.assertEqual(len(port.priority_queue), 1)
        self.assertEqual(len(port.egress_queue), 0)

    def test_regular_packet_goes_to_egress_queue_when_flag_on(self):
        port = self._make_port(priority=True)
        pkt = _make_packet(port.owner.scheduler, 4, is_retransmit=False)
        port._drain_scheduled = True
        port.enqueue(pkt)
        self.assertEqual(len(port.priority_queue), 0)
        self.assertEqual(len(port.egress_queue), 1)

    def test_queue_size_counts_both_queues(self):
        port = self._make_port(priority=True)
        port._drain_scheduled = True
        port.enqueue(_make_packet(port.owner.scheduler, 10, is_retransmit=False))
        port.enqueue(_make_packet(port.owner.scheduler, 11, is_retransmit=True))
        port.enqueue(_make_packet(port.owner.scheduler, 12, is_retransmit=True))
        self.assertEqual(port.queue_size(), 3)
        self.assertEqual(len(port.priority_queue), 2)
        self.assertEqual(len(port.egress_queue), 1)

    def test_peak_queue_len_tracks_combined(self):
        port = self._make_port(priority=True)
        port._drain_scheduled = True
        for i in range(5):
            port.enqueue(_make_packet(port.owner.scheduler, 100 + i, is_retransmit=(i % 2 == 0)))
        self.assertEqual(port.peak_queue_len, 5)


class TestRetransmitPriorityQueueIntegration(unittest.TestCase):
    """End-to-end test: retransmit packets should overtake regular packets in the queue."""

    def _build_topology(self, *, priority: bool):
        """
        Build:  h1 -- s1 -- h2
        with a very slow h1->s1 link so packets queue up,
        and a fast s1->h2 link.
        """
        sim = _make_sim(retransmit_priority=priority)
        sim.packet_stall_percent = 0.0  # we'll inject retransmit manually
        sim.packet_stall_delay_s = 0.0
        sim.packet_stall_max_switch_hop = 0

        h1 = Host(name="h1", scheduler=sim, ip_address="10.0.0.1",
                  message_verbose=False, verbose_route=False, max_path=10,
                  ports_count=1, routing_mode=RoutingMode.ECMP,
                  ecmp_flowlet_n_packets=0, mtu=128, ttl=64)
        sw = Switch("sw", ports_count=2, scheduler=sim, routing_mode=RoutingMode.ECMP,
                    message_verbose=False, verbose_route=False)
        h2 = Host(name="h2", scheduler=sim, ip_address="10.0.0.2",
                  message_verbose=False, verbose_route=False, max_path=10,
                  ports_count=1, routing_mode=RoutingMode.ECMP,
                  ecmp_flowlet_n_packets=0, mtu=128, ttl=64)

        # Slow link between h1 and sw so packets pile up; fast link to h2
        l1 = Link("l1", sim, bandwidth_bps=1e6, propagation_time=0.0)
        l2 = Link("l2", sim, bandwidth_bps=1e12, propagation_time=0.0)
        h1.connect(1, l1)
        sw.connect(1, l1)
        sw.connect(2, l2)
        h2.connect(1, l2)

        h1.set_ip_routing("10.0.0.2/32", 1)
        sw.set_ip_routing("10.0.0.2/32", 2)

        return sim, h1, sw, h2

    def test_retransmit_packets_arrive_before_regular_when_priority_enabled(self):
        """
        Send 3 regular packets + 1 retransmit packet from h1.
        With priority ON the retransmit packet should be forwarded ahead of the
        regular packets that are already waiting in the egress queue.

        We verify this by checking that among delivered packets the retransmit packet
        (seq_number==99) arrives earlier than the last regular packet.
        """
        sim, h1, sw, h2 = self._build_topology(priority=True)

        # Send 3 regular packets (they'll queue up on the slow l1).
        for i in range(3):
            h1.send_message(session_id=1, dst_ip_address="10.0.0.2",
                            source_port=1000, dest_port=80,
                            size_bytes=128, protocol=Protocol.UDP)

        # Inject a retransmit packet directly into the h1 egress port queue
        # after the regular packets are already enqueued but before the link drains.
        retransmit_pkt = _make_packet(sim, global_id=9999, is_retransmit=True)
        retransmit_pkt.routing_header.ttl = 64
        # Deliver via normal routing path from h1
        h1._internal_send_packet(retransmit_pkt)

        # Track arrival order at h2 by monkey-patching on_message
        arrival_order: list[int] = []
        original_on_message = h2.on_message

        def recording_on_message(packet):
            arrival_order.append(packet.tracking_info.global_id)
            original_on_message(packet)

        h2.on_message = recording_on_message

        sim.run()

        self.assertEqual(h2.received_count, 4)

        # The retransmit packet (global_id=9999) should appear in the arrival list
        # BEFORE the last regular packet (the one enqueued last, which got bumped back).
        retransmit_pos = arrival_order.index(9999)
        # At least one regular packet should arrive AFTER the retransmit packet.
        # (With priority on, the retransmit moves ahead of waiting regular packets.)
        regular_positions_after = [i for i, gid in enumerate(arrival_order) if gid != 9999 and i > retransmit_pos]
        self.assertGreater(len(regular_positions_after), 0,
                           f"Expected some regular packets after the retransmit; order={arrival_order}")

    def test_without_priority_retransmit_packet_does_not_jump_queue(self):
        """
        Same scenario with priority OFF: the retransmit packet should NOT overtake
        packets that were enqueued before it.
        """
        sim, h1, sw, h2 = self._build_topology(priority=False)

        for i in range(3):
            h1.send_message(session_id=1, dst_ip_address="10.0.0.2",
                            source_port=1000, dest_port=80,
                            size_bytes=128, protocol=Protocol.UDP)

        retransmit_pkt = _make_packet(sim, global_id=9999, is_retransmit=True)
        retransmit_pkt.routing_header.ttl = 64
        h1._internal_send_packet(retransmit_pkt)

        arrival_order: list[int] = []
        original_on_message = h2.on_message

        def recording_on_message(packet):
            arrival_order.append(packet.tracking_info.global_id)
            original_on_message(packet)

        h2.on_message = recording_on_message

        sim.run()

        self.assertEqual(h2.received_count, 4)

        retransmit_pos = arrival_order.index(9999)
        # With priority OFF, the retransmit packet was enqueued last, so it should
        # arrive last (all 3 regular packets before it).
        self.assertEqual(retransmit_pos, 3,
                         f"Without priority, retransmit should be last; order={arrival_order}")


class TestIsRetransmitFlag(unittest.TestCase):
    """Verify that reinject_stalled_packet correctly sets is_retransmit=True."""

    def test_reinject_sets_is_retransmit(self):
        sim = _make_sim(retransmit_priority=False)
        sim.packet_stall_percent = 0.0
        h1 = Host(name="h1", scheduler=sim, ip_address="10.0.0.1",
                  message_verbose=False, verbose_route=False, max_path=10,
                  ports_count=1, routing_mode=RoutingMode.ECMP,
                  ecmp_flowlet_n_packets=0, mtu=4096, ttl=64)
        h2 = Host(name="h2", scheduler=sim, ip_address="10.0.0.2",
                  message_verbose=False, verbose_route=False, max_path=10,
                  ports_count=1, routing_mode=RoutingMode.ECMP,
                  ecmp_flowlet_n_packets=0, mtu=4096, ttl=64)
        link = Link("l", sim, bandwidth_bps=1e12, propagation_time=0.0)
        h1.connect(1, link)
        h2.connect(1, link)
        h1.set_ip_routing("10.0.0.2/32", 1)

        pkt = _make_packet(sim, 42, is_retransmit=False)
        self.assertFalse(pkt.tracking_info.is_retransmit)

        h1.reinject_stalled_packet(pkt, stalled_switch_name="sw1")

        self.assertTrue(pkt.tracking_info.is_retransmit)

    def test_fresh_packet_is_not_retransmit(self):
        pkt = _make_packet(_make_sim(retransmit_priority=False), 1, is_retransmit=False)
        self.assertFalse(pkt.tracking_info.is_retransmit)


if __name__ == "__main__":
    unittest.main()

