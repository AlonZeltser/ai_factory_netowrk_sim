# Workload Phases Summary

This note summarizes the two built-in workloads and the phases they model.

## 1. `dp-heavy`

Defined by:
- builder: `ai_factory/workloads/dp_heavy_workload.py`
- scenario wrapper: `ai_factory/scenarios/ai_factory_su_dp_heavy_scenario.py`

### What it represents
A classic **data-parallel training step** where all workers:
1. do local forward/backward compute,
2. synchronize gradients,
3. apply the optimizer update.

### Phase breakdown per step

| Phase | Code name | What it represents in real life | How the simulator builds it |
|---|---|---|---|
| 1 | `fwd_bwd_compute` | GPU/accelerator compute for forward + backward pass on local mini-batch | `ComputePhase(duration_s=t_fwd_bwd_ms / 1000)` |
| 2 | `gradient_sync` | Gradient aggregation across all workers | For each bucket, build `REDUCE_SCATTER` + `ALL_GATHER`; combine both into one `CommPhase` |
| 3 | `optimizer_compute` | Local optimizer step after gradients are synchronized | `ComputePhase(duration_s=optimizer_ms / 1000)` |

### How the communication is modeled
- Gradient sync is split into `num_buckets` buckets.
- Each bucket uses:
  - `reduce-scatter`
  - then `all-gather`
- The collective expansion is done by `expand_collective(...)`.
- The current scenario uses the `RING` collective algorithm.
- Optional `chunk_redundancy_extra_packets` adds a fixed number of redundant packets to each communication flow; a flow with `N` useful packets completes when any `N` packets out of the gross packet stream arrive.

### Why this is realistic
This is a standard decomposition of distributed DP training:
- local compute first,
- then global gradient exchange,
- then local weight update.

The simulator simplifies reality by:
- modeling compute as a fixed-duration phase,
- modeling communication as explicit network flows generated from collectives.

---

## 2. `mixed`

Defined by:
- workload builders: `ai_factory/workloads/mixed_scenario.py`
- scenario wrapper: `ai_factory/scenarios/mixed_scenario.py`

This workload runs **two jobs concurrently** on disjoint halves of the cluster:
- `tp_heavy`
- `pp_dp`

The scenario first:
1. splits hosts between the two jobs,
2. assigns 4 PP stages for the `pp_dp` job,
3. builds both jobs,
4. runs both over the same network at the same time.

## 2a. `tp_heavy` job inside `mixed`

### What it represents
A workload dominated by **tensor-parallel communication**:
- compute,
- many small repeated TP collectives,
- one heavier final DP-style synchronization,
- a short tail compute.

### Phase breakdown per step

| Phase | Code name pattern | What it represents in real life | How the simulator builds it |
|---|---|---|---|
| 1 | `tp_heavy_compute_front` | Front-side model compute before communication bursts | `ComputePhase(fwd_compute_ms)` |
| 2 | `tp_heavy_tp_micro_<m>` | Repeated tensor-parallel syncs between shards | One `ALL_REDUCE` per micro-collective |
| 3 | `tp_heavy_gap_<m>` | Small compute gap between TP collectives | `ComputePhase(micro_compute_gap_ms)` |
| 4 | `tp_heavy_dp_sync` | Heavier synchronization at the end of the step | `REDUCE_SCATTER` + `ALL_GATHER` |
| 5 | `tp_heavy_compute_tail` | Final compute / cleanup after sync | `ComputePhase(tail_compute_ms)` |

### Why this is realistic
This approximates models where tensor-parallel layers repeatedly exchange activations or partial results during a step, then still need a larger synchronization near the end.

The simulator captures that with:
- many alternating comm/compute micro-phases,
- a larger final collective,
- configurable traffic scaling.
- optional `chunk_redundancy_extra_packets` on communication flows.

---

## 2b. `pp_dp` job inside `mixed`

### What it represents
A hybrid **pipeline-parallel + data-parallel** job:
- pipeline forward traffic,
- pipeline backward traffic,
- then a DP gradient sync,
- then a small tail compute.

### Phase breakdown per step

| Phase | Code name | What it represents in real life | How the simulator builds it |
|---|---|---|---|
| 1 | `pp_dp_pp_fwd` | Forward pipeline sends between consecutive stages | `_build_pp_microbatches(..., direction="fwd")` builds stage-to-stage flows `0->1->2->3` |
| 2 | `pp_dp_pp_bwd` | Backward pipeline gradient sends in reverse stage order | `_build_pp_microbatches(..., direction="bwd")` builds flows `3->2->1->0` |
| 3 | `pp_dp_dp_sync` | Data-parallel sync after pipeline work | `REDUCE_SCATTER` + `ALL_GATHER` across all `pp_dp` participants |
| 4 | `pp_dp_compute_tail` | Final local compute/update after communication | `ComputePhase(tail_compute_ms)` |

### How the pipeline traffic is modeled
- Hosts assigned to `pp_dp` are split into exactly **4 stages**.
- For each microbatch:
  - forward sends are emitted as sequential bursts across `0->1`, `1->2`, `2->3`
  - backward sends are emitted as sequential bursts across `3->2`, `2->1`, `1->0`
- Each hop is represented as explicit `Flow` objects with slightly offset start times.

### Why this is realistic
This approximates the communication pattern of pipeline training:
- activations move forward,
- gradients move backward,
- then replicas synchronize parameters or gradients.

The simulator simplifies reality by representing each pipeline hop as a deterministic burst rather than a full execution engine with overlapping compute kernels and scheduler details.

Like the other workloads, `mixed` can also use `chunk_redundancy_extra_packets` to send extra packets per communication chunk while completing once any `N` packets out of `N + R` arrive.

---

## Cross-cutting modeling notes

### Compute phases
All compute phases are modeled as:
- `ComputePhase(name, duration_s)`

So they represent elapsed accelerator work, not packets.

### Communication phases
All communication phases are modeled as either:
- collectives expanded into many flows via `expand_collective(...)`, or
- explicit point-to-point `Flow` bursts for pipeline traffic.

### Optional background traffic
Both scenarios can inject optional `mice` traffic using `MiceFlowInjector`.
This represents small background network activity that competes with the main training traffic.

---

## Short intuition

- `dp-heavy` = **compute -> global gradient sync -> optimizer**
- `mixed/tp_heavy` = **compute -> many small TP syncs -> bigger sync -> tail compute**
- `mixed/pp_dp` = **pipeline forward -> pipeline backward -> DP sync -> tail compute**

That is the main mapping from simulator phases to real-world distributed training behavior.

