from __future__ import annotations

from typing import Any

from ai_factory.simulators.ai_factory_su_network_simulator import AIFactorySUNetworkSimulator, AIFactorySUTopologyConfig
from network.core.network import Network
from network.core.network_node import RoutingMode
from ..config.models import ConfigError, ExperimentSpec, RoutingSpec, RunSpec, TopologySpec, reject_unknown_keys

_CLOS_PARAM_KEYS = ("layers", "leaf_count", "spine_count", "max_path", "mtu", "ttl", "fabric")
_CLOS_FABRIC_KEYS = (
    "servers_per_leaf",
    "host_links_per_server",
    "parallel_leaf_to_spine_links",
    "link_failure_percent",
    "packet_stall_percent",
    "packet_stall_delay_ms",
    "packet_stall_max_switch_hop",
    "packet_stall_retransmit_priority",
    "server_to_leaf_bandwidth_bps",
    "leaf_to_spine_bandwidth_bps",
)


def _require_mapping_param(params: dict[str, Any], key: str) -> dict[str, Any]:
    value = params.get(key)
    if value is None:
        raise ConfigError(f"Missing required key 'topology.params.{key}'")
    if not isinstance(value, dict):
        raise ConfigError(f"Expected mapping at topology.params.{key}")
    return value


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
def _require_int_param(params: dict[str, Any], key: str) -> int:
    if key not in params:
        raise ConfigError(f"Missing required key 'topology.params.{key}'")
    return int(params[key])


def _require_float_param(params: dict[str, Any], key: str) -> float:
    if key not in params:
        raise ConfigError(f"Missing required key 'topology.params.{key}'")
    return float(params[key])


def _require_bool_param(params: dict[str, Any], key: str) -> bool:
    if key not in params:
        raise ConfigError(f"Missing required key 'topology.params.{key}'")
    return bool(params[key])


def _build_clos(topology: TopologySpec, routing: RoutingSpec, run: RunSpec) -> Network:
    routing_mode, flowlet_packets = _normalize_routing(routing)

    params = dict(topology.params)
    reject_unknown_keys(params, _CLOS_PARAM_KEYS, "topology.params")
    layers = _require_int_param(params, "layers")
    if layers != 2:
        raise ConfigError("The clos implementation supports only layers=2 (leaf-spine)")

    fabric = _require_mapping_param(params, "fabric")
    reject_unknown_keys(fabric, _CLOS_FABRIC_KEYS, "topology.params.fabric")
    leaf_count = _require_int_param(params, "leaf_count")
    spine_count = _require_int_param(params, "spine_count")
    if leaf_count <= 0:
        raise ConfigError("topology.params.leaf_count must be >= 1")
    if spine_count <= 0:
        raise ConfigError("topology.params.spine_count must be >= 1")
    servers_per_leaf = _require_int_param(fabric, "servers_per_leaf")
    host_links_per_server = _require_int_param(fabric, "host_links_per_server")
    parallel_leaf_to_spine_links = _require_int_param(fabric, "parallel_leaf_to_spine_links")

    server_to_leaf_bandwidth_bps = _require_float_param(fabric, "server_to_leaf_bandwidth_bps")
    leaf_to_spine_bandwidth_bps = _require_float_param(fabric, "leaf_to_spine_bandwidth_bps")

    topo_cfg = AIFactorySUTopologyConfig(
        leaves=leaf_count,
        spines=spine_count,
        servers_per_leaf=servers_per_leaf,
        server_parallel_links=host_links_per_server,
        leaf_to_spine_parallel_links=parallel_leaf_to_spine_links,
    )
    return AIFactorySUNetworkSimulator(
        max_path=_require_int_param(params, "max_path"),
        link_failure_percent=_require_float_param(fabric, "link_failure_percent"),
        packet_stall_percent=_require_float_param(fabric, "packet_stall_percent"),
        packet_stall_delay_ms=_require_float_param(fabric, "packet_stall_delay_ms"),
        packet_stall_max_switch_hop=_require_int_param(fabric, "packet_stall_max_switch_hop"),
        packet_stall_retransmit_priority=_require_bool_param(fabric, "packet_stall_retransmit_priority"),
        routing_mode=routing_mode,
        verbose=run.message_verbose,
        verbose_route=run.verbose_route,
        ecmp_flowlet_n_packets=flowlet_packets,
        server_to_leaf_bandwidth_bps=float(server_to_leaf_bandwidth_bps),
        leaf_to_spine_bandwidth_bps=float(leaf_to_spine_bandwidth_bps),
        mtu=_require_int_param(params, "mtu"),
        ttl=_require_int_param(params, "ttl"),
        store_packets=run.store_packets,
        collect_packet_timeline=run.collect_packet_timeline,
        topology_config=topo_cfg,
    )


def build_network(spec: ExperimentSpec) -> Network:
    topology_name = str(spec.topology.name).strip().lower()
    if topology_name != "clos":
        raise ConfigError(f"Unsupported topology '{spec.topology.name}'. The current project supports only 'clos'.")
    return _build_clos(spec.topology, spec.routing, spec.run)




