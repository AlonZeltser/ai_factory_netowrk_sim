import logging
from functools import partial

from network.core.network_node import NetworkNode, RoutingMode

_logger = logging.getLogger(__name__)


class Switch(NetworkNode):

    def __init__(
        self,
        name: str,
        ports_count,
        scheduler,
        message_verbose: bool,
        verbose_route: bool,
        routing_mode: RoutingMode,
    ):
        super().__init__(
            name,
            ports_count,
            scheduler,
            routing_mode=routing_mode,
            message_verbose=message_verbose,
            verbose_route=verbose_route,
        )

    def _is_last_switch_before_destination(self, packet) -> bool:
        best_port_id = self.select_port_for_packet(packet)
        if best_port_id is None:
            return False
        port = self.ports[best_port_id]
        link = port.link
        if link is None or link.failed:
            return False
        if link.port1 is None or link.port2 is None:
            return False
        dst_port = link.port2 if port == link.port1 else link.port1
        return type(dst_port.owner).__name__ == "Host"

    def _should_delay_packet(self, packet) -> bool:
        tracking = packet.tracking_info
        tracking.switch_hops_seen += 1
        if tracking.packet_stall_triggered:
            return False
        target_switch_hop = tracking.packet_stall_target_switch_hop
        if target_switch_hop is None:
            return False
        current_switch_hop = tracking.switch_hops_seen - 1
        if current_switch_hop >= int(target_switch_hop):
            return True
        return self._is_last_switch_before_destination(packet)

    def _reschedule_from_source_host(self, packet, packet_stall_delay_s: float) -> None:
        src_ip = packet.routing_header.five_tuple.src_ip
        source_host = self.scheduler.hosts_by_ip.get(src_ip)
        if source_host is None:
            raise LookupError(
                f"Stalled packet {packet.tracking_info.global_id} at switch {self.name}: "
                f"no host is registered for its source IP {src_ip}"
            )
        self.scheduler.schedule_event(
            packet_stall_delay_s,
            partial(source_host.reinject_stalled_packet, packet, stalled_switch_name=self.name),
        )

    def on_message(self, packet):
        if packet.is_expired():
            if self.message_verbose:
                now = self.scheduler.get_current_time()
                logging.warning(
                    f"[sim_t={now:012.6f}s] Packet expired     switch={self.name} packet_id={packet.tracking_info.global_id} dst={packet.routing_header.five_tuple.dst_ip}")
            packet.routing_header.dropped = True
            self.scheduler.packet_stats.record_dropped(packet)
        else:
            if self._should_delay_packet(packet):
                now = self.scheduler.get_current_time()
                packet_stall_delay_s = self.scheduler.packet_stall_delay_s
                packet.tracking_info.packet_stall_triggered = True
                self.scheduler.packet_stats.record_packet_stall_triggered(packet)
                if self.message_verbose and _logger.isEnabledFor(logging.DEBUG):
                    _logger.debug(
                        f"[sim_t={now:012.6f}s] Packet stalled     switch={self.name} packet_id={packet.tracking_info.global_id} switch_hop={packet.tracking_info.switch_hops_seen - 1} delay_s={packet_stall_delay_s:.6f}"
                    )
                self._reschedule_from_source_host(packet, packet_stall_delay_s)
                return
            if self.message_verbose and _logger.isEnabledFor(logging.DEBUG):
                now = self.scheduler.get_current_time()
                _logger.debug(
                    f"[sim_t={now:012.6f}s] Packet forwarding  switch={self.name} packet_id={packet.tracking_info.global_id} dst={packet.routing_header.five_tuple.dst_ip}")
            self._internal_send_packet(packet)

