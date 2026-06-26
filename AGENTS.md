# AGENTS.md

## What this repo is
- Discrete-event network simulator for AI training traffic on a Clos (leaf-spine) fabric, with ECMP/flowlet/adaptive routing and AI workload scenarios.
- Primary user entrypoint is `python -m apps.sim ...` (`apps/sim.py`).

## Big-picture architecture (read these first)
- `apps/sim.py` -> CLI commands (`run`, `validate`, `init`, `batch`, `sweep`, `list`).
- `sim/config/loader.py` + `sim/config/models.py` -> load YAML, resolve `extends`, apply `--set a.b.c=value`, validate into `ExperimentSpec`.
- `sim/registry/topologies.py` -> converts `ExperimentSpec` to concrete `Network` (currently only `clos` supported).
- `sim/registry/workloads.py` -> maps `workload.kind` (`dp-heavy`, `mixed`, `none`) to scenario builders.
- `sim/runners/experiment_runner.py` -> wires logging, builds network+scenario, runs DES, optional visualization.
- `network/core/*` -> packet, host/switch/port/link, forwarding logic, and simulator results aggregation.
- `ai_factory/*` -> workload model and flow injection (`JobRunner`, DP-heavy and mixed scenarios).

## Data/config flow and why it matters
- Presets are layered YAML with deep merge (`extends` chain), not code defaults; see `sim/presets/ai/*.yaml` and `sim/config/loader.py`.
- `topology.profile` and `workload.profile` are intentionally rejected; keep defaults in YAML fragments and override `topology.params` / `workload.params`.
- Override parsing uses `yaml.safe_load`, so `--set topology.params.leaf_count=12` becomes int, booleans parse naturally, etc.
- Routing alias behavior is in `sim/registry/topologies.py`: `flowlet` maps to ECMP with nonzero `ecmp_flowlet_n_packets`.

## Project-specific conventions to preserve
- Port IDs in APIs are **1-based** (`NetworkNode.connect`, `set_ip_routing`); internal storage is 0-based.
- Failed links are still physically connected but excluded from learned forwarding entries (`NetworkNode.set_ip_routing` checks `link.failed`).
- Network metrics are pulled from `network.entities[...]` side channels (e.g., `ai_factory_job_metrics`, `ai_factory_bucket_metrics`, `ai_factory_flow_metrics`).
- Scenario installation pattern: `network.assign_scenario(s)` -> scenario `install(network)` schedules events and stores metrics.
- `apps/sim.py` includes a `sys.path` guard to prevent `apps/sim.py` shadowing the `sim/` package in IDE/debug runs; do not remove casually.

## Developer workflows that are actually used
- List capabilities: `python -m apps.sim list presets|workloads|routing`
- Validate resolved config without running: `python -m apps.sim validate --preset ai/su-mixed-light`
- Run one experiment: `python -m apps.sim run --preset ai/su-dp-low-small`
- Batch presets/configs: `python -m apps.sim batch --preset ai/su-dp-low-small --preset ai/su-mixed-light`
- Sweep cartesian overrides: `python -m apps.sim sweep --preset ai/su-dp-low-small --vary routing.mode=ecmp,adaptive`
- Tests: `python -m pytest tests/ -v` (targeted suites under `tests/des`, `tests/network`, `tests/ai_factory`, `tests/sim`).

## Integration points and dependencies
- Visualization paths: topology via `visualization/visualizer.py`; experiment plots via `visualization/experiment_visualizer.py`.
- Graphviz system install is required for some visualization paths (`requirements.txt` + README notes).
- Logging is centralized in `log_setup.py`; per-run log files go under `results/logs`.
- Simulator output artifacts and summaries are written to `results/` by runners and visualization helpers.

## Safe extension checklist
- New workload: implement scenario in `ai_factory/scenarios/` (or `network/scenarios/`), register in `sim/registry/workloads.py`, add preset YAML under `sim/presets/`.
- New topology family: add builder wiring in `sim/registry/topologies.py` and ensure `ExperimentSpec.topology.params` validation errors are explicit.
- New routing mode: update `network/core/network_node.py` (`RoutingMode` + selection) and normalize CLI-facing values in `sim/registry/topologies.py`.

