# Implemented Simulator Architecture
## Status
The project now exposes a unified simulator interface centered on:
- `apps/sim.py`
- the `sim/` package
- preset-driven AI-factory / clos experiments
Legacy small test topologies such as HSH and simple-star have been removed from the active project surface.
## Public Interface
Use the unified CLI:
```text
python -m apps.sim <command>
```
Supported commands:
- `list`
- `validate`
- `init`
- `run`
- `batch`
- `sweep`
## Configuration Model
Experiments use a single config structure:
- `meta`
- `run`
- `topology`
- `routing`
- `workload`
Topologies are currently centered on:
- the `clos` family
- YAML topology defaults inherited from `sim/presets/ai/topology-clos-scale-unit.yaml`
Workloads are currently centered on:
- `kind: dp-heavy`
- `kind: mixed`
- `kind: none`
- YAML workload defaults inherited from documented base fragments in `sim/presets/ai/`
## Presets
Presets live under `sim/presets/ai/` and use inheritance via `extends`.
Examples:
- `ai/su-dp-light`
- `ai/su-dp-low`
- `ai/su-dp-mid`
- `ai/su-dp-high`
- `ai/su-mixed-light`
- `ai/su-mixed-low`
- `ai/su-mixed-mid`
- `ai/su-mixed-high`
## Registry Layers
The unified interface is implemented through registries:
- `sim/registry/topologies.py`
- `sim/registry/workloads.py`
- `sim/registry/presets.py`
These map public names to the concrete simulator builders and workload constructors.
## Notes
- Validation prints both the resolved experiment and its preset/config origin.
- Batch and sweep execution are implemented in Python and no longer rely on shell scripts.
- Visualization is controlled via `run.visualize`.
