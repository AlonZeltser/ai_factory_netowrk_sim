import itertools
import logging
import random
from dataclasses import dataclass
from typing import cast

from des.des import DiscreteEventSimulator
from network.core.packet import FiveTupleExt, Protocol, PacketL3, PacketTransport, \
    PacketTrackingInfo, Packet
from network.core.network_node import NetworkNode, RoutingMode

_logger = logging.getLogger(__name__)

packet_ids = itertools.count()
flow_ids = itertools.count(1)

@dataclass
class Flow:
    flow_id: int
    app_id: int
    session_id: int
    src_ip: str
    dst_ip: str
    size_bytes: int
    start_time: float
    end_time: float | None = None
    bytes_received: int = 0

class Host(NetworkNode):
    def __init__(
        self,
        name: str,
        scheduler: DiscreteEventSimulator,
        ip_address: str,
        message_verbose: bool,
        verbose_route: bool,
        max_path: int | None,
        ports_count: int,
        routing_mode: RoutingMode,
        ecmp_flowlet_n_packets: int,
        mtu: int,
        ttl: int,
    ):
        super().__init__(
            name,
            ports_count,
            scheduler,
            routing_mode=routing_mode,
            message_verbose=message_verbose,
            verbose_route=verbose_route
        )
        self._ip_address: str = ip_address
        self._received_count: int = 0
        self.max_path: int | None = max_path
        self.flows: dict[int, Flow] = {}
        self.ecmp_flowlet_n_packets = ecmp_flowlet_n_packets
        self.mtu = mtu
        self.ttl = ttl
        hosts_by_ip = getattr(self.scheduler, "hosts_by_ip", None)
        if hosts_by_ip is None:
            hosts_by_ip = {}
            self.scheduler.hosts_by_ip = hosts_by_ip
        existing = hosts_by_ip.get(self.ip_address)
        if existing is not None and existing is not self:
            raise ValueError(f"Duplicate host IP registration: {self.ip_address}")
        hosts_by_ip[self.ip_address] = self

    @property
    def ip_address(self) -> str:
        return self._ip_address


    def send_message(
        self,
        session_id: int,
        dst_ip_address: str,
        source_port: int,
        dest_port: int,
        size_bytes: int,
        protocol: Protocol,
        **_kwargs,
    ) -> None:
        """Send a bulk message from this Host.

        Notes:
        - `session_id` is the value that becomes `PacketTransport.flow_id` and is used by higher layers
          (including the AI-factory layer) to join on flow completion.
        - `app_id` is currently unused (kept only for backward compatibility with older scenarios).
        """
        #logging.debug(f"[t={self.scheduler.get_current_time():.6f}s] Host {self.name} sending message "
        #              f"session_id={session_id} to {dst_ip_address} size={size_bytes}B protocol={protocol.name}")

        packet_count = (size_bytes + self.mtu - 1) // self.mtu
        flowlet_field: int = int(self.scheduler.get_current_time() * 1_000_000_000)
        flowlet_enabled = self.ecmp_flowlet_n_packets > 0
        for i in range(packet_count):
            packet_size = self.mtu if i < packet_count - 1 else size_bytes - self.mtu * (packet_count - 1)
            packet_global_id: int = next(packet_ids)  # globally unique
            if flowlet_enabled:
                # Update flowlet field every N packets.
                if (i + 1) % self.ecmp_flowlet_n_packets == 0:
                    flowlet_field += 1
            header: PacketL3 = PacketL3(
                five_tuple=FiveTupleExt(self.ip_address, dst_ip_address, source_port, dest_port, protocol, cast(int, flowlet_field)),
                seq_number=i,
                size_bytes=packet_size,
                ttl=self.ttl
            )
            app_header: PacketTransport = PacketTransport(
                flow_id=session_id,
                flow_count=packet_count,
                flow_seq=i
            )
            tracking_info = PacketTrackingInfo(
                global_id=packet_global_id,
                birth_time=self.scheduler.get_current_time(),
                initial_ttl=self.ttl,
                route_length=0,
                verbose_route=None)
            if self.verbose_route:
                tracking_info.verbose_route = [self.name]
            packet_stall_percent = float(getattr(self.scheduler, "packet_stall_percent", 0.0) or 0.0)
            packet_stall_max_switch_hop = int(getattr(self.scheduler, "packet_stall_max_switch_hop", 0) or 0)
            if packet_stall_percent > 0.0 and random.random() < (packet_stall_percent / 100.0):
                tracking_info.packet_stall_target_switch_hop = random.randint(0, max(0, packet_stall_max_switch_hop))
                self.scheduler.packet_stats.record_packet_stall_marked()
            packet = Packet(routing_header=header,
                            transport_header=app_header,
                            tracking_info=tracking_info)
            # Record packet creation in streaming stats
            self.scheduler.packet_stats.record_created()
            # Optionally store packet for debugging (when enabled)
            if self.scheduler._store_packets and self.scheduler.packets is not None:
                self.scheduler.packets.append(packet)
            self._internal_send_packet(packet)

    def reinject_stalled_packet(self, packet: Packet, *, stalled_switch_name: str | None = None) -> None:
        now = self.scheduler.get_current_time()
        initial_ttl = int(packet.tracking_info.initial_ttl or self.ttl)
        packet.routing_header.ttl = initial_ttl
        packet.tracking_info.arrival_time = None
        packet.tracking_info.delivered = False
        if self.verbose_route and packet.tracking_info.verbose_route is not None:
            packet.tracking_info.verbose_route.append(self.name)
        if self.message_verbose and _logger.isEnabledFor(logging.DEBUG):
            stall_text = f" stalled_at={stalled_switch_name}" if stalled_switch_name else ""
            _logger.debug(
                f"[sim_t={now:012.6f}s] Packet reinjected  host={self.name} packet_id={packet.tracking_info.global_id}{stall_text} ttl_reset={initial_ttl}"
            )
        self._internal_send_packet(packet)


    def on_message(self, packet: Packet):
        now = self.scheduler.get_current_time()
        packet.tracking_info.delivered = True
        packet.tracking_info.arrival_time = now
        self._received_count += 1
        # Record delivery in streaming stats
        self.scheduler.packet_stats.record_delivered(packet.tracking_info.route_length)

        if self.message_verbose and _logger.isEnabledFor(logging.DEBUG):
            _logger.debug(
                f"[sim_t={now:012.6f}s] Packet received    host={self.name} packet_id={packet.tracking_info.global_id}")

    @property
    def received_count(self) -> int:
        return self._received_count


