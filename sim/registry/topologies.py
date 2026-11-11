from __future__ import annotations

from ai_factory.simulators.ai_factory_su_network_simulator import AIFactorySUNetworkSimulator, AIFactorySUTopologyConfig
from network.core.network import Network
from network.core.network_node import RoutingMode
from ..config.models import ConfigError, ExperimentSpec, RoutingSpec


def _normalize_routing(spec: RoutingSpec) -> tuple[RoutingMode, int]:
    mode = str(spec.mode).strip().lower()
    flowlet_packets = int(spec.ecmp_flowlet_n_packets)
    if flowlet_packets < 0:
        raise ConfigError(f"routing.ecmp_flowlet_n_packets must be >= 0, got {flowlet_packets}")
    if mode == "ecmp":
        return RoutingMode.ECMP, flowlet_packets
    if mode == "flowlet":
        if flowlet_packets == 0:
            raise ConfigError("routing.mode 'flowlet' requires routing.ecmp_flowlet_n_packets > 0")
        return RoutingMode.ECMP, flowlet_packets
    if mode == "adaptive":
        return RoutingMode.ADAPTIVE, flowlet_packets
    raise ConfigError(f"Unsupported routing.mode: {spec.mode!r}. Valid: ecmp | adaptive | flowlet")


def build_network(spec: ExperimentSpec) -> Network:
    """Build the two-layer clos network described by the config."""
    topology, routing, stall, run = spec.topology, spec.routing, spec.stall_regime, spec.run
    routing_mode, flowlet_packets = _normalize_routing(routing)

    topo_cfg = AIFactorySUTopologyConfig(
        leaves=topology.leaf_count,
        spines=topology.spine_count,
        servers_per_leaf=topology.servers_per_leaf,
        server_parallel_links=topology.host_links_per_server,
        leaf_to_spine_parallel_links=topology.parallel_leaf_to_spine_links,
    )
    return AIFactorySUNetworkSimulator(
        max_path=routing.max_path,
        link_failure_percent=topology.link_failure_percent,
        packet_stall_percent=stall.packet_stall_percent,
        packet_stall_delay_ms=stall.packet_stall_delay_ms,
        packet_stall_max_switch_hop=stall.packet_stall_max_switch_hop,
        packet_stall_retransmit_priority=stall.packet_stall_retransmit_priority,
        routing_mode=routing_mode,
        verbose=run.message_verbose,
        verbose_route=run.verbose_route,
        ecmp_flowlet_n_packets=flowlet_packets,
        server_to_leaf_bandwidth_bps=topology.server_to_leaf_bandwidth_bps,
        leaf_to_spine_bandwidth_bps=topology.leaf_to_spine_bandwidth_bps,
        mtu=routing.mtu,
        ttl=routing.ttl,
        store_packets=run.store_packets,
        collect_packet_timeline=run.collect_packet_timeline,
        topology_config=topo_cfg,
    )
