# DP-Heavy Workload: Detailed Implementation and Modeling Guide

This document explains the `dp-heavy` workload end-to-end:
- what it models in AI-factory training,
- how collectives are translated into network traffic,
- where synchronization/barriers happen,
- how to estimate flow and packet counts,
- which code entities participate from AI-factory layer down to DES/network.

Primary implementation files:
- `ai_factory/workloads/dp_heavy_workload.py`
- `ai_factory/scenarios/ai_factory_su_dp_heavy_scenario.py`
- `ai_factory/traffic/collective.py`
- `ai_factory/traffic/patterns/ring.py`
- `ai_factory/core/runner.py`
- `ai_factory/scenarios/network_flow_injector.py`
- `network/core/host.py`
- `sim/registry/workloads.py`
- `sim/presets/ai/workload-dp-heavy-*.yaml`

---

## 1) What `dp-heavy` simulates in AI-factory terms

`dp-heavy` models a classic data-parallel training job where all workers execute the same training step pattern:

1. local forward+backward compute,
2. global gradient synchronization,
3. local optimizer/update compute.

In this model, communication is dominated by DP gradient sync traffic. This is why the workload is called "dp-heavy".

### Collective concept in this workload

The workload models gradient synchronization as two collectives per bucket:
- `REDUCE_SCATTER`
- `ALL_GATHER`

This is a standard decomposition of all-reduce-like synchronization in distributed training.

In the current implementation, collectives are expanded using a **ring algorithm only**.
- `CollectiveAlgorithm.RING` is used by the DP-heavy scenario.
- `TREE` is declared in enum but not implemented for expansion.

---

## 2) Who participates? (hosts and participants)

In `AIFactorySUDpHeavyScenario.install()`:
- participants are taken as `sorted(network.hosts.keys())`.
- Therefore, **all hosts in the instantiated topology participate** in the DP collective job.

So if topology has `P` hosts, the job has `P` participants.

---

## 3) Step and phase structure

For each training step (`steps`):

1. `ComputePhase("fwd_bwd_compute")`
   - duration: `t_fwd_bwd_ms / 1000`
2. `CommPhase("gradient_sync")`
   - contains `num_buckets` buckets
   - each bucket contains `REDUCE_SCATTER` + `ALL_GATHER` flows
3. `ComputePhase("optimizer_compute")`
   - duration: `optimizer_ms / 1000`

This is built in `build_workload1_dp_heavy_job()`.

---

## 4) How collectives are expanded into flows

Collective expansion path:

1. Workload builder calls `expand_collective(...)` for `reduce_scatter` and `all_gather`.
2. `expand_collective()` dispatches to `expand_ring_neighbor_sends(...)`.
3. Ring expansion emits explicit `Flow` objects.

### Ring communication pattern used

Given `P` participants:
- ring steps = `P - 1`
- at each ring step `s`, every participant sends one flow to its ring neighbor (`next_of(sender)`).

So for one collective:
- flows per step = `P`
- steps = `P - 1`
- total flows = `P * (P - 1)`

For one bucket in DP-heavy (RS + AG):
- `2 * P * (P - 1)` flows

For one training step:
- `num_buckets * 2 * P * (P - 1)` flows

For whole job:
- `steps * num_buckets * 2 * P * (P - 1)` flows

### Timing in ring expansion

Each flow has start time:

`t_flow(s) = start_time + s * gap_us * 1e-6`

In DP-heavy builder, both RS and AG are created with `start_time = 0.0` for every bucket, so both collectives are emitted on the same intra-bucket timeline in this model.

---

## 5) Data amount model: bytes, chunks, buckets, steps

Define:
- `P` = number of participants (hosts)
- `B` = `bucket_bytes_per_participant` (useful bytes per participant per bucket, before redundancy)
- `R` = `chunk_redundancy_percent`
- `M` = host MTU in bytes (`topology.params.mtu`, default often 4096)

### 5.1 Chunk partitioning used by ring code

Ring code computes per-step chunk sizes from:

`base = B // P`
`rem = B % P`

`chunk_size[i] = base + 1` for `i < rem`, else `base`.

Then only steps `s = 0..P-2` are emitted (because ring steps = `P-1`), and each step uses `chunk_size[s]`.

So per sender per collective transmitted useful bytes are:

`U_collective_per_sender = sum_{s=0..P-2} chunk_size[s]`

Closed form:

`U_collective_per_sender = (P - 1) * base + min(rem, P - 1)`

Per bucket per sender (RS + AG):

`U_bucket_per_sender = 2 * U_collective_per_sender`

Per bucket total useful bytes over all senders:

`U_bucket_total = P * U_bucket_per_sender`

### 5.2 Redundancy inflation

`apply_chunk_redundancy()` transforms each flow:
- `useful_bytes` stays as original chunk bytes,
- `size_bytes` becomes inflated by `R` percent:

`T_flow = ceil(U_flow * (1 + R/100))` (and at least `U_flow`).

Important completion rule:
- flow completion is triggered after receiving `useful_bytes`, not necessarily all inflated transmitted bytes.

### 5.3 Packets per flow and totals

Host packetization in `Host.send_message()` uses:

`packets_per_flow = ceil(T_flow / M)`

Where `T_flow` is transmitted bytes after redundancy.

Therefore, estimated packets:

- per bucket:
  `Packets_bucket = sum( ceil(T_flow_i / M) )` over all `2 * P * (P - 1)` flows
- per step:
  `Packets_step = num_buckets * Packets_bucket`
- per job:
  `Packets_job = steps * Packets_step`

For rough back-of-envelope (if all `T_flow_i` similar), use:

`Packets_job ~= steps * num_buckets * 2 * P * (P - 1) * ceil(T_avg_flow / M)`

---

## 6) Synchronization points (barriers)

Synchronization is implemented in `JobRunner` + `BarrierBookkeeper`.

### Barrier hierarchy

1. **Phase order barrier** inside a step:
   - phase N+1 starts only when phase N finishes.

2. **Comm-phase bucket barrier**:
   - buckets run sequentially.
   - next bucket starts only when all flows in current bucket complete.
   - implemented via `Join(pending={flow_ids...})`.

3. **Step barrier**:
   - next step starts only after all phases in current step finish.

4. **Job completion barrier**:
   - job ends only after all steps finish.

### What is not synchronized explicitly

Inside a bucket, there is no explicit RS-then-AG dependency barrier in code; both sets of flows are placed in the same bucket and launched according to each flow's `start_time`.

---

## 7) Main knobs controlling traffic amount and timing

From `workload.params` (`sim/registry/workloads.py`, `sim/presets/ai/workload-dp-heavy-base.yaml`):

- `steps`
  - linear multiplier on total compute+comm volume.
- `num_buckets`
  - linear multiplier on communication flows/packets per step.
- `bucket_bytes_per_participant`
  - controls per-flow chunk sizes; larger means more bytes and packets.
- `gap_us`
  - spacing between ring steps inside a collective.
- `chunk_redundancy_percent`
  - inflates transmitted bytes per flow.
- `t_fwd_bwd_ms`
  - pre-comm compute duration.
- `optimizer_ms`
  - post-comm compute duration.
- `seed`
  - controls deterministic ID generation/ring ordering behavior.
- `mice` (optional)
  - adds background short-flow traffic competing with DP traffic.

Cross-layer knobs that also affect effective behavior:
- `topology.params.mtu`
  - packetization granularity (`ceil(bytes/mtu)`).
- routing config (`routing.mode`, flowlet params)
  - path selection/congestion distribution; may affect completion time but not intended logical flow count.

---

## 8) AI-factory entities and how they map to network + DES

### 8.1 AI-factory planning entities

- `Job`
  - whole DP training job
- `JobStep`
  - one training iteration
- `ComputePhase`
  - timed compute placeholder
- `CommPhase`
  - communication phase containing buckets
- `Bucket`
  - list of `Flow`s for one gradient bucket
- `Flow`
  - packet-agnostic transfer request with metadata (`job_id`, `step_id`, `phase_id`, `bucket_id`, `tag`, src/dst, bytes, start time)

### 8.2 Runtime execution entities

- `JobRunner`
  - state machine over job -> step -> phase
  - schedules events on DES simulator
- `BarrierBookkeeper` / `Join`
  - completion barriers for bucket flow sets
- `NetworkFlowInjector`
  - adapts `Flow` to `Host.send_message()` and tracks completion

### 8.3 Network/DES entities involved

- DES: `DiscreteEventSimulator`
  - schedules compute timers and delayed flow injections
- Network Host: `Host.send_message(...)`
  - packetizes flow bytes into packets by MTU
  - emits packets into routing/switch fabric
- Packet delivery callback path:
  - host `on_message` is wrapped by injector
  - injector counts received bytes for each flow ID
  - when expected bytes are met, injector calls flow completion callback
  - callback resolves join/barrier in `JobRunner`

---

## 9) Metrics produced for DP-heavy

- per-flow metrics (`ai_factory_flow_metrics`):
  - start/end time, bytes (transmitted/useful), tags, src/dst
- per-bucket metrics:
  - flow count, transmitted/useful bytes, bucket duration
- per-phase and per-step timings
- job-level timing and step statistics (avg/p95/p99)

These are exposed under `network.entities` by scenario/runner.

---

## 10) Practical interpretation and caveats

This DP-heavy model is intentionally compact and event-driven. It captures key pressure patterns (many synchronized collective flows) but remains simplified:

- compute phases are fixed delays (no compute/network overlap model beyond phase sequencing),
- communication is explicit flow injection rather than full collective protocol emulation,
- ring algorithm is the only implemented collective expansion,
- bucket execution is serialized by barrier (one bucket at a time),
- RS and AG are currently co-scheduled within a bucket timeline (no explicit dependency barrier between them).

These choices make experiments reproducible, configurable, and fast enough for comparative routing studies.

---

## 11) Quick formula cheat-sheet

Let:
- `P` participants
- `S` steps
- `K` buckets (`num_buckets`)
- `B` bytes per participant per bucket
- `R` redundancy percent
- `M` MTU bytes

Then:

- flows per collective: `P(P-1)`
- flows per bucket (RS+AG): `2P(P-1)`
- flows per step: `K * 2P(P-1)`
- flows per job: `S * K * 2P(P-1)`

Chunking terms:
- `base = B // P`, `rem = B % P`
- per-sender useful bytes per collective:
  `U_collective = (P-1) * base + min(rem, P-1)`

Per-flow transmitted bytes (after redundancy):
- `T_flow = ceil(U_flow * (1 + R/100))`

Packets:
- `packets_per_flow = ceil(T_flow / M)`
- total packets = sum over all flows.

Use this sheet for rough scaling estimates before running heavy sweeps.

