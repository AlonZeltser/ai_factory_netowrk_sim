from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from network.core.network import Network
from network.core.network_node import RoutingMode


@dataclass(frozen=True)
class AIFactorySUTopologyConfig:
    """Topology sizing parameters for the AI-Factory scale unit (SU) simulator."""

    leaves: int
    spines: int
    servers_per_leaf: int
    server_parallel_links: int
    leaf_to_spine_parallel_links: int

    @staticmethod
    def from_mapping(d: Mapping[str, Any] | None) -> "AIFactorySUTopologyConfig":
        if not isinstance(d, Mapping):
            raise ValueError("Expected mapping for topology.ai_factory_su")

        missing = [
            k
            for k in (
                "leaves",
                "spines",
                "servers_per_leaf",
                "server_parallel_links",
                "leaf_to_spine_parallel_links",
            )
            if k not in d
        ]
        if missing:
            raise ValueError(
                "Missing required topology.ai_factory_su keys: " + ", ".join(missing)
            )

        return AIFactorySUTopologyConfig(
            leaves=int(d["leaves"]),
            spines=int(d["spines"]),
            servers_per_leaf=int(d["servers_per_leaf"]),
            server_parallel_links=int(d["server_parallel_links"]),
            leaf_to_spine_parallel_links=int(d["leaf_to_spine_parallel_links"]),
        )


class AIFactorySUNetworkSimulator(Network):
    """A topology inspired by an AI-Factory scale unit (SU).

    We simulate everything over Ethernet.

    Topology (single scale unit / pod):
      - 8 leaf switches (ToRs).
      - 4 spine switches.
      - 4 servers per leaf.
      - Each server connects to its leaf using 8 x 400GbE links.
      - Leaf <-> Spine fabric: each leaf has 32 uplinks total, each spine has 64 downlinks.
        Implemented as 8 uplinks from each leaf to each spine (8 leaves * 8 = 64 per spine).

    Routing:
      - Servers are addressed in per-leaf /24 subnets: 10.<pod_id>.<leaf_id>.<server_id>
      - Leaves route:
          * local /24 -> host-facing ports
          * pod /16 (10.<pod_id>.0.0/16) -> uplinks (ECMP across spines)
      - Spines route:
          * per-leaf /24 -> downlinks to that leaf

    Scenario:
      - No traffic by default (topology-only). Visualization can be enabled.
    """

    POD_ID = 1

    def __init__(
        self,
        max_path: int,
        link_failure_percent: float,
        packet_stall_percent: float = 0.0,
        packet_stall_delay_ms: float = 50.0,
        packet_stall_max_switch_hop: int = 2,
        routing_mode: RoutingMode = RoutingMode.ECMP,
        verbose: bool = False,
        verbose_route: bool = False,
        ecmp_flowlet_n_packets: int = 0,
        server_to_leaf_bandwidth_bps: float = 400e9,
        leaf_to_spine_bandwidth_bps: float = 400e9,
        mtu: int = 4096,
        ttl: int = 64,
        store_packets: bool = False,
        collect_packet_timeline: bool = False,
        *,
        topology_config: AIFactorySUTopologyConfig | None = None,
        topology_cfg: Mapping[str, Any] | None = None,
    ):
        super().__init__(
            name="ai-factory-su",
            max_path=max_path,
            link_failure_percent=link_failure_percent,
            packet_stall_percent=packet_stall_percent,
            packet_stall_delay_ms=packet_stall_delay_ms,
            packet_stall_max_switch_hop=packet_stall_max_switch_hop,
            routing_mode=routing_mode,
            verbose=verbose,
            verbose_route=verbose_route,
            ecmp_flowlet_n_packets=ecmp_flowlet_n_packets,
            mtu=mtu,
            ttl=ttl,
            store_packets=store_packets,
            collect_packet_timeline=collect_packet_timeline,
        )

        if topology_config is not None and topology_cfg is not None:
            raise ValueError("Provide either topology_config or topology_cfg, not both")

        if topology_config is None:
            self.topology = AIFactorySUTopologyConfig.from_mapping(topology_cfg)
        else:
            self.topology = topology_config

        if self.topology.leaves <= 0 or self.topology.spines <= 0:
            raise ValueError("topology.leaves and topology.spines must be > 0")
        if self.topology.servers_per_leaf <= 0:
            raise ValueError("topology.servers_per_leaf must be > 0")
        if self.topology.server_parallel_links <= 0 or self.topology.leaf_to_spine_parallel_links <= 0:
            raise ValueError("topology parallel link counts must be > 0")

        self.server_to_leaf_bandwidth_bps = float(server_to_leaf_bandwidth_bps)
        self.leaf_to_spine_bandwidth_bps = float(leaf_to_spine_bandwidth_bps)
        self._identifier = {
            "topology": "ai-factory-su",
            "leaves": self.topology.leaves,
            "spines": self.topology.spines,
            "servers_per_leaf": self.topology.servers_per_leaf,
            "server_parallel_links": self.topology.server_parallel_links,
            "leaf_to_spine_parallel_links": self.topology.leaf_to_spine_parallel_links,
            "link failure percent": link_failure_percent,
            "packet stall percent": packet_stall_percent,
            "packet stall delay ms": packet_stall_delay_ms,
            "packet stall max switch hop": packet_stall_max_switch_hop,
            "server_to_leaf_bandwidth_bps": self.server_to_leaf_bandwidth_bps,
            "leaf_to_spine_bandwidth_bps": self.leaf_to_spine_bandwidth_bps,
        }

    def create_topology(self):
        server_bw = self.server_to_leaf_bandwidth_bps
        fabric_bw = self.leaf_to_spine_bandwidth_bps
        delay = 1e-6  # 1us per hop propagation (toy value, but non-zero)

        leaves_n = self.topology.leaves
        spines_n = self.topology.spines
        servers_per_leaf = self.topology.servers_per_leaf
        server_parallel_links = self.topology.server_parallel_links
        leaf_to_spine_parallel_links = self.topology.leaf_to_spine_parallel_links

        # Switches
        # Leaf ports: (servers_per_leaf * server_parallel_links) downlinks,
        # plus (spines_n * leaf_to_spine_parallel_links) uplinks.
        leaf_ports = servers_per_leaf * server_parallel_links + (spines_n * leaf_to_spine_parallel_links)
        spine_ports = leaves_n * leaf_to_spine_parallel_links

        leaves = [
            self.create_switch(f"su{self.POD_ID}_leaf{leaf_i}", ports_count=leaf_ports)
            for leaf_i in range(leaves_n)
        ]
        spines = [
            self.create_switch(f"su{self.POD_ID}_spine{spine_i}", ports_count=spine_ports)
            for spine_i in range(spines_n)
        ]

        # Hosts and Host<->Leaf links
        # Addressing: 10.<POD_ID>.<leaf_id+1>.<server_id+1>
        for leaf_i, leaf in enumerate(leaves):
            leaf_subnet_third_octet = leaf_i + 1

            for srv_i in range(servers_per_leaf):
                host_name = f"su{self.POD_ID}_leaf{leaf_i}_srv{srv_i}"
                ip = f"10.{self.POD_ID}.{leaf_subnet_third_octet}.{srv_i + 1}"
                host = self.create_host(host_name, ip, ports_count=server_parallel_links)

                for k in range(server_parallel_links):
                    link = self.create_link(
                        f"su{self.POD_ID}_l_leaf{leaf_i}_srv{srv_i}_nic{k}",
                        bandwidth=server_bw,
                        delay=delay,
                    )
                    # Host port ids are 1..N
                    host.connect(k + 1, link)
                    # Leaf host-facing ports are 1..(servers_per_leaf*server_parallel_links)
                    leaf_port_id = (srv_i * server_parallel_links) + k + 1
                    leaf.connect(leaf_port_id, link)

                # Host routing: route the whole POD via any NIC (ECMP across NICs)
                pod_prefix_16 = f"10.{self.POD_ID}.0.0/16"
                for k in range(server_parallel_links):
                    host.set_ip_routing(pod_prefix_16, k + 1)

            # Leaf routing: per-server /32 routes for local delivery (ECMP across the N ports to that server)
            # and a /24 shortcut for "this leaf".
            leaf_prefix_24 = f"10.{self.POD_ID}.{leaf_subnet_third_octet}.0/24"
            for srv_i in range(servers_per_leaf):
                ip = f"10.{self.POD_ID}.{leaf_subnet_third_octet}.{srv_i + 1}"
                for k in range(server_parallel_links):
                    leaf_port_id = (srv_i * server_parallel_links) + k + 1
                    leaf.set_ip_routing(f"{ip}/32", leaf_port_id)

                # Also include the per-leaf /24 routed to all local host-facing ports (readable subnet entry)
                for k in range(server_parallel_links):
                    leaf_port_id = (srv_i * server_parallel_links) + k + 1
                    leaf.set_ip_routing(leaf_prefix_24, leaf_port_id)

        # Leaf<->Spine links
        # Leaf uplink ports start after host-facing ports.
        leaf_uplink_base = servers_per_leaf * server_parallel_links
        for leaf_i, leaf in enumerate(leaves):
            for spine_i, spine in enumerate(spines):
                for k in range(leaf_to_spine_parallel_links):
                    link = self.create_link(
                        f"su{self.POD_ID}_l_leaf{leaf_i}_spine{spine_i}_{k}",
                        bandwidth=fabric_bw,
                        delay=delay,
                    )

                    leaf_port_id = leaf_uplink_base + (spine_i * leaf_to_spine_parallel_links) + k + 1
                    spine_port_id = (leaf_i * leaf_to_spine_parallel_links) + k + 1

                    leaf.connect(leaf_port_id, link)
                    spine.connect(spine_port_id, link)

        # Fabric routing
        # Leaves: route the entire POD /16 to all uplinks (ECMP across spines and parallel links).
        pod_prefix_16 = f"10.{self.POD_ID}.0.0/16"
        for leaf in leaves:
            for spine_i in range(spines_n):
                for k in range(leaf_to_spine_parallel_links):
                    leaf_port_id = leaf_uplink_base + (spine_i * leaf_to_spine_parallel_links) + k + 1
                    leaf.set_ip_routing(pod_prefix_16, leaf_port_id)

        # Spines: route each leaf /24 to the downlinks to that leaf
        for spine in spines:
            for leaf_i in range(leaves_n):
                leaf_prefix_24 = f"10.{self.POD_ID}.{leaf_i + 1}.0/24"
                for k in range(leaf_to_spine_parallel_links):
                    spine_port_id = (leaf_i * leaf_to_spine_parallel_links) + k + 1
                    spine.set_ip_routing(leaf_prefix_24, spine_port_id)

        # Sanity: check all switch ports connected (unless link failures prevented it).
        # We still physically connect failed links, so ports will be connected.
        for sw in leaves + spines:
            try:
                sw.assert_correctly_full()
            except AssertionError:
                logging.exception(f"Switch {sw.name} isn't fully connected")
                raise

        logging.info(
            f"AI-Factory scale-unit topology created: leaves={leaves_n}, spines={spines_n}, "
            f"servers={leaves_n * servers_per_leaf}, links={len(self.links)}"
        )

    @property
    def identifier(self):
        return self._identifier

