import logging

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

    def _should_delay_packet(self, packet) -> bool:
        tracking = packet.tracking_info
        tracking.switch_hops_seen += 1
        if tracking.packet_stall_triggered:
            return False
        target_switch_hop = tracking.packet_stall_target_switch_hop
        if target_switch_hop is None:
            return False
        return (tracking.switch_hops_seen - 1) == int(target_switch_hop)

    def on_message(self, packet):
        if packet.is_expired():
            if self.message_verbose:
                now = self.scheduler.get_current_time()
                logging.warning(
                    f"[sim_t={now:012.6f}s] Packet expired     switch={self.name} packet_id={packet.tracking_info.global_id} dst={packet.routing_header.five_tuple.dst_ip}")
            packet.routing_header.dropped = True
            self.scheduler.packet_stats.record_dropped()
        else:
            if self._should_delay_packet(packet):
                now = self.scheduler.get_current_time()
                packet_stall_delay_s = float(getattr(self.scheduler, "packet_stall_delay_s", 0.0) or 0.0)
                packet.tracking_info.packet_stall_triggered = True
                self.scheduler.packet_stats.record_packet_stall_triggered()
                if self.message_verbose and _logger.isEnabledFor(logging.DEBUG):
                    _logger.debug(
                        f"[sim_t={now:012.6f}s] Packet stalled     switch={self.name} packet_id={packet.tracking_info.global_id} switch_hop={packet.tracking_info.switch_hops_seen - 1} delay_s={packet_stall_delay_s:.6f}"
                    )
                self.scheduler.schedule_event(packet_stall_delay_s, lambda: self._internal_send_packet(packet))
                return
            if self.message_verbose and _logger.isEnabledFor(logging.DEBUG):
                now = self.scheduler.get_current_time()
                _logger.debug(
                    f"[sim_t={now:012.6f}s] Packet forwarding  switch={self.name} packet_id={packet.tracking_info.global_id} dst={packet.routing_header.five_tuple.dst_ip}")
            self._internal_send_packet(packet)

