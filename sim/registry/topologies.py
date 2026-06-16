from __future__ import annotations

from typing import Any

from ai_factory.simulators.ai_factory_su_network_simulator import AIFactorySUNetworkSimulator, AIFactorySUTopologyConfig
from network.core.network import Network
from network.core.network_node import RoutingMode
from ..config.models import ConfigError, ExperimentSpec, RoutingSpec, RunSpec, TopologySpec


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
    if mode in {"ecmp", "hash"}:
        return RoutingMode.ECMP, max(flowlet_packets, 0)
    if mode == "flowlet":
        return RoutingMode.ECMP, flowlet_packets if flowlet_packets > 0 else 64
    if mode in {"adaptive", "adapt"}:
        return RoutingMode.ADAPTIVE, max(flowlet_packets, 0)
    raise ConfigError(f"Unsupported routing.mode: {spec.mode!r}. Valid: ecmp | adaptive | flowlet")
def _require_int_param(params: dict[str, Any], key: str) -> int:
    if key not in params:
        raise ConfigError(f"Missing required key 'topology.params.{key}'")
    return int(params[key])


def _require_float_param(params: dict[str, Any], key: str) -> float:
    if key not in params:
        raise ConfigError(f"Missing required key 'topology.params.{key}'")
    return float(params[key])


def _optional_float_param(params: dict[str, Any], key: str, default: float) -> float:
    value = params.get(key)
    return float(default if value is None else value)


def _optional_int_param(params: dict[str, Any], key: str, default: int) -> int:
    value = params.get(key)
    return int(default if value is None else value)


def _bandwidth_profile_to_bps(profile: str) -> tuple[float, float]:
    normalized = profile.strip().lower()
    if normalized == "4g":
        return 4e9, 4e9
    if normalized == "400g":
        return 400e9, 400e9
    raise ConfigError(f"Unsupported topology fabric bandwidth_profile: {profile!r}. Valid: 4g | 400g")


def _build_clos(topology: TopologySpec, routing: RoutingSpec, run: RunSpec) -> Network:
    routing_mode, flowlet_packets = _normalize_routing(routing)
    if str(topology.profile).strip():
        raise ConfigError("topology.profile is no longer supported. Put topology defaults in YAML via extends and override topology.params directly.")

    params = dict(topology.params)
    layers = _require_int_param(params, "layers")
    if layers != 2:
        raise ConfigError("The current clos implementation supports only layers=2 (leaf-spine) during Batch 2")

    fabric = _require_mapping_param(params, "fabric")
    leaf_count = _require_int_param(params, "leaf_count")
    spine_count = _require_int_param(params, "spine_count")
    if leaf_count <= 0:
        raise ConfigError("topology.params.leaf_count must be >= 1")
    if spine_count <= 0:
        raise ConfigError("topology.params.spine_count must be >= 1")
    servers_per_leaf = _require_int_param(fabric, "servers_per_leaf")
    host_links_per_server = _require_int_param(fabric, "host_links_per_server")
    parallel_leaf_to_spine_links = _require_int_param(fabric, "parallel_leaf_to_spine_links")

    server_to_leaf_bandwidth_bps = fabric.get("server_to_leaf_bandwidth_bps")
    leaf_to_spine_bandwidth_bps = fabric.get("leaf_to_spine_bandwidth_bps")
    bandwidth_profile = fabric.get("bandwidth_profile")
    if bandwidth_profile is not None:
        server_to_leaf_bandwidth_bps, leaf_to_spine_bandwidth_bps = _bandwidth_profile_to_bps(str(bandwidth_profile))
    else:
        if server_to_leaf_bandwidth_bps is None:
            server_to_leaf_bandwidth_bps = _require_float_param(fabric, "server_to_leaf_bandwidth_bps")
        if leaf_to_spine_bandwidth_bps is None:
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
        packet_stall_percent=_optional_float_param(fabric, "packet_stall_percent", 0.0),
        packet_stall_delay_ms=_optional_float_param(fabric, "packet_stall_delay_ms", 50.0),
        packet_stall_max_switch_hop=_optional_int_param(fabric, "packet_stall_max_switch_hop", 2),
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




