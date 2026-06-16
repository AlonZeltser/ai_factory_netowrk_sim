# Stall Packets: Functional Review and Implementation Notes

This document explains how packet stalls work in the simulator at parameter, random-behavior, functional, and code-implementation levels.

## 1) Parameters

Stall behavior is controlled by three topology fabric parameters:

- `topology.params.fabric.packet_stall_percent`
  - Meaning: percentage of packets that are tagged for exactly one future switch stall.
  - Valid range: `0.0..100.0`.
  - Validation: `network/core/network.py` (`Network.__init__`) enforces range.
- `topology.params.fabric.packet_stall_delay_ms`
  - Meaning: extra hold time (milliseconds) applied when a tagged packet hits its selected switch hop.
  - Valid range: `>= 0.0`.
  - Validation: `network/core/network.py`.
- `topology.params.fabric.packet_stall_max_switch_hop`
  - Meaning: maximum zero-based switch-hop index eligible for stall trigger.
  - Valid range: `>= 0`.
  - Validation: `network/core/network.py`.

Where parameters are wired:

- Config parsing/defaults: `sim/registry/topologies.py`
  - Defaults if omitted:
    - `packet_stall_percent`: `0.0`
    - `packet_stall_delay_ms`: `50.0`
    - `packet_stall_max_switch_hop`: `2`
- YAML examples and comments:
  - `sim/presets/ai/bases/topology-clos-small-scale-unit.yaml`
  - `sim/presets/ai/bases/topology-clos-large-scale-unit.yaml`
- Runtime propagation:
  - `Network` stores the values and copies them onto DES scheduler fields:
    - `scheduler.packet_stall_percent`
    - `scheduler.packet_stall_delay_s`
    - `scheduler.packet_stall_max_switch_hop`

## 2) Random Component of Stall

Randomization happens once, at packet creation time in `Host.send_message(...)` (`network/core/host.py`).

For every packet (not per flow), the host does:

1. Bernoulli sampling for tagging:
   - Condition: `random.random() < packet_stall_percent / 100.0`
   - If true, the packet is marked as stall-eligible.
2. If marked, choose target switch hop uniformly:
   - `packet_stall_target_switch_hop = random.randint(0, packet_stall_max_switch_hop)`
   - This is inclusive on both ends.

Important consequences:

- Tagging is packet-independent, so packets from the same flow can get different stall outcomes.
- With `packet_stall_percent=0`, no packets are marked.
- With `packet_stall_percent=100`, all packets are marked.
- Target hop index is in switch-hop space only (not host hops).
- RNG source is Python's global `random` module.
  - Reproducibility comes from `sim/runners/experiment_runner.py`, which calls `random.seed(run.seed)` when a seed is provided.

## 3) What Happens Functionally

At a high level: some packets are pre-tagged at source host, then each tagged packet is delayed exactly once when it reaches its chosen switch-hop index.

Detailed timeline for one tagged packet:

1. Packet is created at source host.
2. Packet carries tracking fields:
   - `packet_stall_target_switch_hop` (maybe `None`)
   - `packet_stall_triggered` (initially `False`)
   - `switch_hops_seen` (initially `0`)
3. At each switch ingress (`Switch.on_message`):
   - `switch_hops_seen` increments by 1.
   - If packet already triggered, no further stall attempts.
   - If packet has no target hop, no stall.
   - Else trigger condition is checked:
     - `(switch_hops_seen - 1) == packet_stall_target_switch_hop`
4. If condition matches:
   - Set `packet_stall_triggered = True`.
   - Increment `packet_stall_triggered_count`.
   - Schedule forwarding after `packet_stall_delay_s` using DES event queue.
   - Packet is not dropped; it is held, then forwarded.
5. After delay event fires, normal forwarding resumes via `_internal_send_packet`.
6. Packet can still later be dropped for unrelated reasons (e.g., TTL expiry, no route, failed link handling).

So stall is an additional queue-like wait inserted at one switch hop, once per marked packet.

## 4) How It Is Implemented (Code-Level)

Core data model (`network/core/packet.py`):

- `PacketTrackingInfo.switch_hops_seen`
- `PacketTrackingInfo.packet_stall_target_switch_hop`
- `PacketTrackingInfo.packet_stall_triggered`

Marking path (`network/core/host.py`):

- In `Host.send_message(...)`, after packet tracking object creation:
  - read scheduler stall params,
  - perform random mark + random hop selection,
  - increment `packet_stall_marked_count` when tagged.

Trigger path (`network/core/switch.py`):

- `_should_delay_packet(packet)`:
  - increments `switch_hops_seen`,
  - returns true once at configured switch hop index if not previously triggered.
- `on_message(packet)`:
  - if expired: drop path,
  - else if `_should_delay_packet` true:
    - mark triggered,
    - record triggered counter,
    - `schedule_event(packet_stall_delay_s, lambda: _internal_send_packet(packet))`,
    - return early (do not forward immediately).

Validation and exposure (`network/core/network.py`):

- Constructor validates parameter ranges.
- Converts ms to seconds (`packet_stall_delay_s`).
- Exposes stall parameters in `parameters summary` output.
- Exposes counters in `run statistics`:
  - `packet_stall_marked_count`
  - `packet_stall_triggered_count`

Statistics (`des/packet_statistics.py`):

- Separate counters for marked vs triggered packets.
- Useful because marked may exceed triggered if a packet never reaches target switch hop.

## 5) Observability and Logs

If message debug logging is enabled (`message_verbose` and logger DEBUG level):

- On trigger, switch logs:
  - `Packet stalled`
  - switch name
  - packet id
  - switch hop index
  - delay seconds

At the end of run, results include stall counters in run statistics (see `Network.get_results()`).

## 6) Practical Interpretation / Edge Cases

- `packet_stall_max_switch_hop=0` means only first switch can trigger stall.
- If path has fewer switch hops than selected target, packet is marked but never triggered.
- Stalling does not bypass normal link serialization/propagation; it adds an extra wait before enqueueing next hop.
- Stalling is one-shot due to `packet_stall_triggered` guard.
- Because marking is packet-level random, micro-bursts can be affected unevenly.

## 7) Minimal End-to-End Behavior Check in Tests

A direct test exists in `tests/network/test_port_queue.py`:

- Sets `packet_stall_percent=100`, `packet_stall_delay_s=0.05`, `packet_stall_max_switch_hop=0`.
- Sends one packet through `Host -> Switch -> Host`.
- Asserts:
  - packet delivered,
  - marked count is `1`,
  - triggered count is `1`,
  - simulation end time includes the stall delay (~`0.05s`).

This test confirms the one-time hold-and-forward behavior functionally.

