import unittest

from des.des import DiscreteEventSimulator
from network.core.host import Host
from network.core.link import Link
from network.core.switch import Switch
from network.core.packet import Protocol
from network.core.network_node import RoutingMode


class TestPortQueue(unittest.TestCase):

    def test_port_queue_drains_using_link_availability(self):
        sim = DiscreteEventSimulator()

        h1 = Host(
            name="h1",
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

        # 1 Mbps, 0 propagation delay.
        link = Link("l1", sim, bandwidth_bps=1e6, propagation_time=0.0)
        h1.connect(1, link)
        h2.connect(1, link)

        # route between hosts
        h1.set_ip_routing("10.0.0.2/32", 1)
        h2.set_ip_routing("10.0.0.1/32", 1)


        # Create 2 packets at time 0. They should serialize on the link.
        h1.send_message(
            app_id=1,
            session_id=1,
            dst_ip_address="10.0.0.2",
            source_port=12345,
            dest_port=80,
            size_bytes=1000,  # 0.008s serialization
            protocol=Protocol.UDP,
            message="a",
        )
        h1.send_message(
            app_id=1,
            session_id=1,
            dst_ip_address="10.0.0.2",
            source_port=12345,
            dest_port=80,
            size_bytes=1000,
            protocol=Protocol.UDP,
            message="b",
        )


        # Immediately after enqueuing, we should have a backlog (at least 1 waiting).
        self.assertGreaterEqual(h1.port_queue_size(1), 1)

        sim.run()

        self.assertEqual(h2.received_count, 2)
        # Check via streaming stats (packets not stored by default)
        self.assertEqual(sim.packet_stats.total_count, 2)
        self.assertEqual(sim.packet_stats.delivered_count, 2)
        self.assertAlmostEqual(sim.end_time, 0.016, places=6)

    def test_packet_stall_holds_marked_packet_at_switch_before_forwarding(self):
        sim = DiscreteEventSimulator()
        sim.packet_stall_percent = 100.0
        sim.packet_stall_delay_s = 0.05
        sim.packet_stall_max_switch_hop = 0

        h1 = Host(
            name="h1",
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
        sw = Switch(
            "s1",
            ports_count=2,
            scheduler=sim,
            routing_mode=RoutingMode.ECMP,
            message_verbose=False,
            verbose_route=False,
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

        l1 = Link("l1", sim, bandwidth_bps=1e12, propagation_time=0.0)
        l2 = Link("l2", sim, bandwidth_bps=1e12, propagation_time=0.0)
        h1.connect(1, l1)
        sw.connect(1, l1)
        sw.connect(2, l2)
        h2.connect(1, l2)

        h1.set_ip_routing("10.0.0.2/32", 1)
        sw.set_ip_routing("10.0.0.2/32", 2)

        h1.send_message(
            app_id=1,
            session_id=1,
            dst_ip_address="10.0.0.2",
            source_port=12345,
            dest_port=80,
            size_bytes=100,
            protocol=Protocol.UDP,
            message="stall",
        )

        sim.run()

        self.assertEqual(h2.received_count, 1)
        self.assertEqual(sim.packet_stats.packet_stall_marked_count, 1)
        self.assertEqual(sim.packet_stats.packet_stall_triggered_count, 1)
        self.assertGreaterEqual(sim.end_time, 0.05)
        self.assertLess(sim.end_time, 0.051)


if __name__ == "__main__":
    unittest.main()

