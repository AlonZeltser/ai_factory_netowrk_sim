# Section 5.1 Code References: Chunk Partitioning in Ring Code

This document provides evidence in code for each calculation and formula described in **Section 5.1** of `DP_HEAVY_WORKLOAD_REFERENCE.md`.

---

## Section 5.1 Summary

Section 5.1 describes **Chunk partitioning used by ring code**:

- `base = B // P` and `rem = B % P`
- `chunk_size[i] = base + 1` for `i < rem`, else `base`
- `U_collective_per_sender = sum_{s=0..P-2} chunk_size[s]`
- Closed form: `U_collective_per_sender = (P - 1) * base + min(rem, P - 1)`
- Per bucket calculations

---

## Code References

### 1. Chunk Size Calculation: `base = B // P` and `rem = B % P`

**Location:** `ai_factory/traffic/patterns/ring.py`, lines 35-39

```python
def _chunk_sizes(bytes_per_participant: int, p: int) -> list[int]:
    base = bytes_per_participant // p
    rem = bytes_per_participant % p
    # Deterministic remainder: first `rem` steps get +1 byte.
    return [base + (1 if i < rem else 0) for i in range(p)]
```

**Explanation:**
- `B` = `bytes_per_participant` (parameter name)
- `P` = `p` (number of participants)
- `base` is the integer division: `base = B // P`
- `rem` is the remainder: `rem = B % P`
- The list comprehension produces: `chunk_size[i] = base + 1` for `i < rem`, else `base`

---

### 2. Ring Expansion Using Chunk Sizes

**Location:** `ai_factory/traffic/patterns/ring.py`, lines 42-97

```python
def expand_ring_neighbor_sends(
    *,
    op_tag: str,
    participants: list[str],
    bytes_per_participant: int,
    start_time: float,
    gap_us: float,
    ids: IdGenerator,
    job_id: int,
    step_id: int,
    phase_id: int,
    bucket_id: int | None,
) -> list[Flow]:
    """Minimum viable ring model.
    
    Rule:
      - P participants, steps = P-1
      - Chunk size per step per sender = bytes_per_participant / P (deterministic remainder)
      - At each step s, each node i sends one chunk to next(i) in ring order
      - Emit all step flows at time start_time + s * gap_us
    """
    
    p = len(participants)
    if p < 2:
        return []
    
    ring = build_ring_order(participants, seed=ids.seed)
    steps = p - 1                                      # Ring steps = P-1
    chunk_per_step = _chunk_sizes(bytes_per_participant, p)  # Get all chunk sizes
    
    flows: list[Flow] = []
    for s in range(steps):  # s = 0 to P-2
        t = start_time + (s * (gap_us * 1e-6))
        for sender in ring.participants:  # Each of P participants
            receiver = ring.next_of(sender)
            size = chunk_per_step[s]     # Use chunk_size[s]
            flow_id = ids.next_int()
            flows.append(
                Flow(
                    flow_id=flow_id,
                    job_id=job_id,
                    step_id=step_id,
                    phase_id=phase_id,
                    bucket_id=bucket_id,
                    tag=f"{op_tag}/ring_step_{s}",
                    src_node_id=sender,
                    dst_node_id=receiver,
                    size_bytes=size,  # Each flow gets the computed chunk size
                    start_time=t,
                    metadata={"ring_step": s, "participants": p},
                )
            )
    
    return flows
```

**Key Points:**
- Line 71: `steps = p - 1` implements ring steps = P-1
- Line 72: `chunk_per_step = _chunk_sizes(bytes_per_participant, p)` creates the list of chunk sizes
- Lines 75-79: Loop over `s = 0 to P-2` and each sender in ring
- Line 79: `size = chunk_per_step[s]` uses the chunk size for step s
- Lines 81-95: Each sender sends one flow to its ring neighbor with the computed chunk size

---

### 3. Useful Bytes per Collective per Sender

**Interpretation from code:**

In `expand_ring_neighbor_sends()`:
- Each step `s` (from `0` to `P-2`) sends one flow per sender
- Each flow has size `chunk_per_step[s]`
- Total flows per sender = `P - 1` (one per ring step)
- Total useful bytes per sender per collective:

```
U_collective_per_sender = sum(chunk_per_step[s] for s in range(P-1))
```

**Closed form validation:**
- `chunk_per_step` has:
  - First `rem` elements = `base + 1`
  - Remaining `(P - rem)` elements = `base`
- Sum = `rem * (base + 1) + (P - 1 - rem) * base`
  - = `rem * base + rem + P * base - rem * base - base + rem`
  - = `P * base + (rem - base + rem)`  
  
Actually, let me recalculate: Since we only use steps 0 to P-2 (which is P-1 elements):
- The sum of the first P-1 elements where first rem elements are (base+1) and rest are base
- If P-1 >= rem: sum = rem * (base + 1) + (P - 1 - rem) * base = (P-1)*base + rem ✓
- If P-1 < rem: sum = (P-1) * (base + 1) = (P-1)*base + (P-1), which equals (P-1)*base + min(rem, P-1) ✓

Formula: `U_collective_per_sender = (P - 1) * base + min(rem, P - 1)` ✓

---

### 4. Collective Expansion and Redundancy Application

**Location:** `ai_factory/workloads/dp_heavy_workload.py`, lines 56-91

```python
# For each bucket:
for b in range(int(config.num_buckets)):
    bucket_id = b
    start_time = 0.0
    
    # Expand REDUCE_SCATTER collective
    rs = expand_collective(
        kind=CollectiveKind.REDUCE_SCATTER,
        algorithm=config.algorithm,
        participants=participants,
        bytes_per_participant=int(config.bucket_bytes_per_participant),
        start_time=start_time,
        gap_us=float(config.gap_us),
        ids=ids.child((step_idx, 1, bucket_id, "rs")),
        job_id=job_id,
        step_id=step_idx,
        phase_id=1,
        bucket_id=bucket_id,
    )
    
    # Expand ALL_GATHER collective
    ag = expand_collective(
        kind=CollectiveKind.ALL_GATHER,
        algorithm=config.algorithm,
        participants=participants,
        bytes_per_participant=int(config.bucket_bytes_per_participant),
        start_time=start_time,
        gap_us=float(config.gap_us),
        ids=ids.child((step_idx, 1, bucket_id, "ag")),
        job_id=job_id,
        step_id=step_idx,
        phase_id=1,
        bucket_id=bucket_id,
    )
    
    # Apply redundancy to combined flows
    comm_buckets.append(
        Bucket(
            bucket_id=bucket_id,
            flows=apply_chunk_redundancy(
                rs.flows + ag.flows,  # RS + AG flows combined
                extra_percent=float(config.chunk_redundancy_percent),
            ),
        )
    )
```

**Key Points:**
- Both RS and AG collectives expand using the same `bytes_per_participant`
- Total flows per bucket = RS flows + AG flows = 2 * P * (P-1) flows
- Redundancy is applied to all combined flows

---

### 5. Redundancy Inflation (Section 5.2 Related)

**Location:** `ai_factory/traffic/flow.py`, lines 40-67

```python
def apply_chunk_redundancy(flows: list[Flow], *, extra_percent: float) -> list[Flow]:
    if extra_percent <= 0.0:
        return flows
    
    multiplier = 1.0 + (float(extra_percent) / 100.0)
    out: list[Flow] = []
    for flow in flows:
        useful_bytes = int(flow.useful_size_bytes)
        redundant_bytes = max(useful_bytes, int(math.ceil(useful_bytes * multiplier)))
        out.append(
            Flow(
                flow_id=int(flow.flow_id),
                job_id=int(flow.job_id),
                step_id=int(flow.step_id),
                phase_id=int(flow.phase_id),
                bucket_id=flow.bucket_id,
                tag=flow.tag,
                src_node_id=flow.src_node_id,
                dst_node_id=flow.dst_node_id,
                size_bytes=redundant_bytes,        # Transmitted bytes (inflated)
                completion_bytes=useful_bytes,      # Completion threshold (original)
                start_time=float(flow.start_time),
                priority=flow.priority,
                deadline=flow.deadline,
                metadata={**dict(flow.metadata), "chunk_redundancy_percent": float(extra_percent)},
            )
        )
    return out
```

**Implements Section 5.2 formula:**
- `T_flow = ceil(U_flow * (1 + R/100))` where:
  - `R` = `extra_percent` (chunk_redundancy_percent)
  - `U_flow` = `useful_bytes`
  - `T_flow` = `redundant_bytes` = `ceil(useful_bytes * multiplier)`
- `completion_bytes` is set to `useful_bytes` (flow completes after receiving original data)

---

### 6. Packet Calculation from Flow Bytes (Section 5.3 Related)

**Location:** `network/core/host.py`, line 84

```python
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
    # ... docstring ...
    
    packet_count = (size_bytes + self.mtu - 1) // self.mtu  # ceil(size_bytes / mtu)
    flowlet_field = self.scheduler.get_current_time()
    flowlet_enabled = self.ecmp_flowlet_n_packets > 0
    for i in range(packet_count):
        packet_size = self.mtu if i < packet_count - 1 else size_bytes - self.mtu * (packet_count - 1)
        # ... packet creation ...
```

**Implements Section 5.3 formula:**
- `packets_per_flow = ceil(T_flow / M)` where:
  - `T_flow` = `size_bytes` (after redundancy inflation)
  - `M` = `self.mtu` (MTU in bytes)
  - Formula: `(size_bytes + mtu - 1) // mtu` is equivalent to `ceil(size_bytes / mtu)`

---

### 7. Collective Expansion Dispatch

**Location:** `ai_factory/traffic/collective.py`, lines 28-58

```python
def expand_collective(
    *,
    kind: CollectiveKind,
    algorithm: CollectiveAlgorithm,
    participants: list[str],
    bytes_per_participant: int,
    start_time: float,
    gap_us: float,
    ids: IdGenerator,
    job_id: int,
    step_id: int,
    phase_id: int,
    bucket_id: int | None,
) -> CollectiveResult:
    if algorithm != CollectiveAlgorithm.RING:
        raise NotImplementedError("Only ring algorithm is implemented for now")
    
    op_tag = f"{kind.value}"
    flows = expand_ring_neighbor_sends(
        op_tag=op_tag,
        participants=participants,
        bytes_per_participant=bytes_per_participant,
        start_time=start_time,
        gap_us=gap_us,
        ids=ids,
        job_id=job_id,
        step_id=step_id,
        phase_id=phase_id,
        bucket_id=bucket_id,
    )
    return CollectiveResult(flows=flows, join_flow_ids={f.flow_id for f in flows})
```

**Key Points:**
- Dispatches to `expand_ring_neighbor_sends()` for ring algorithm
- Passes `bytes_per_participant` to ring expansion
- Returns all flows with their IDs for barrier tracking

---

## Summary: Flow of Chunk Partitioning Calculation

```
1. Scenario/Workload Parameters
   ├── bucket_bytes_per_participant (B)
   └── num_buckets, participants count (P)
           ↓
2. DP-Heavy Workload Builder (dp_heavy_workload.py:56-81)
   └── Calls expand_collective(..., bytes_per_participant=B, participants=P)
           ↓
3. Collective Expansion (collective.py:28-58)
   └── Calls expand_ring_neighbor_sends(...)
           ↓
4. Ring Code Chunk Calculation (ring.py:35-39)
   ├── base = B // P
   ├── rem = B % P
   └── chunk_per_step[i] = base + (1 if i < rem else 0)
           ↓
5. Ring Flow Expansion (ring.py:75-95)
   └── For s in 0..P-2, for each participant:
       └── Create Flow with size = chunk_per_step[s]
           ↓
6. Redundancy Application (flow.py:40-67)
   └── T_flow = ceil(U_flow * (1 + R/100))
       completion_bytes = U_flow
           ↓
7. Packetization (host.py:84)
   └── packets_per_flow = ceil(T_flow / M)
```

---

## Test/Validation

To verify these calculations in action:

1. **View chunk sizes:** Set `--set workload.params.bucket_bytes_per_participant=1000000` and `topology.params.leaf_count=8` to get concrete values
2. **Trace ring expansion:** Enable debug logging in `expand_ring_neighbor_sends()` to see flows being generated
3. **Verify total useful bytes:** Sum all `useful_size_bytes` from flows in a bucket and compare to formula
4. **Check redundancy:** Compare `flow.size_bytes` (transmitted) vs `flow.completion_bytes` (useful) in metrics

---

## Files Involved

| File | Purpose | Lines |
|------|---------|-------|
| `ai_factory/traffic/patterns/ring.py` | Ring chunk partitioning and flow expansion | 35-97 |
| `ai_factory/traffic/collective.py` | Collective dispatch to ring | 28-58 |
| `ai_factory/workloads/dp_heavy_workload.py` | Workload builder calling collectives | 56-91 |
| `ai_factory/traffic/flow.py` | Redundancy inflation logic | 40-67 |
| `network/core/host.py` | Packetization from flow bytes | 84 |
| `ai_factory/scenarios/ai_factory_su_dp_heavy_scenario.py` | Scenario entry point | 38-51 |

