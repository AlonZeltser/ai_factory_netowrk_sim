# Network Simulator for AI Factory Workloads

## Project Overview

This project is a **discrete-event network simulator** designed to evaluate routing strategies for AI training workloads in data center fabrics. It focuses on comparing different load-balancing approaches (ECMP, Flowlet, Adaptive) under various traffic patterns and failure scenarios.
Project experiments summary is described in submitted project paper.
This document focus on  instructions for running simulations, analyzing results, and possibly extending the simulator for future research.

### Key Features

- **Multiple Routing Algorithms**: ECMP (Equal-Cost Multi-Path), Flowlet-based routing, and Adaptive routing
- **AI Workload Modeling**: Simulates realistic AI training patterns including:
  - DP (Data Parallel) heavy workloads with AllReduce collectives
- **Fabric Topologies**: Clos/Leaf-Spine architectures with configurable counts and fabric parameters
- **Failure Scenarios**: Link failure injection to test resilience
- **Performance Metrics**: Step completion time, FCT (Flow Completion Time), queue occupancy, congestion analysis

### Research Outputs

Detailed analysis and results are available in **`project.pdf`**.

---

## Project Structure

```
network_sim/
├── project.pdf                        # Main paper that describes the research and results
├── apps/
│   └── sim.py                         # Main unified CLI entry point
├── sim/                               # Config loading, registries, runners
├── experiments/                       # Experiment YAML files (base/ holds shared fragments)
├── requirements.txt                    # Python dependencies
│
├── ai_factory_simulation/              # AI workload modeling
│   ├── core/                           # Core entities (jobs, workers, collectives)
│   ├── scenarios/                      # Scenario definitions
│   ├── traffic/                        # Traffic generators
│   └── workloads/                      # Workload definitions
│
├── network_simulation/                 # Core network simulation engine
│   ├── host.py                         # End-host nodes
│   ├── switch.py                       # Switch nodes with routing logic
│   ├── link.py                         # Network links
│   ├── port.py                         # Port queues
│   ├── packet.py                       # Packet structures
│   └── network_node.py                 # Routing mode implementations
│
├── network_simulators/                 # Topology builders
│   └── ai_factory_su_network_simulator.py  # AI Factory scale-unit topology
│
├── des/                                # Discrete Event Simulation framework
│   └── des.py                          # Event scheduler
│
├── log_analyze_utilities/              # Post-processing and analysis (TBD)
│
├── visualization/                      # Visualization tools
│   ├── experiment_visualizer.py        # Result visualizers
│   └── visualizer.py                   # Topology visualizers
│
├── scenarios/                          # Generic scenarios
│   └── none_scenario.py
│
├── tests/                              # Unit tests (pytest)
│   ├── des/
│   ├── network/
│   └── ai_factory/
│
└── results/                            # Output graphs and visualizations
```

---

## Installation

### Prerequisites

- **Python 3.13+**
- **System dependencies**: Graphviz (for topology visualization)
  - Windows: Download from https://graphviz.org/download/
  - Linux: `sudo apt-get install graphviz`
  - macOS: `brew install graphviz`

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/AlonZeltser/networks_for_AI_factories_and_datacenters_final_project.git
   cd network_sim
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Verify installation by running unit tests:
   ```bash
   python -m pytest tests/ -v
   ```


#### IDE Setup (Optional)

**PyCharm:**
1. Open project: `File` → `Open` → Select `network_sim` directory
2. Configure interpreter: `File` → `Settings` → `Project: network_sim` → `Python Interpreter`
3. Click gear icon → `Add Interpreter` → Choose system Python or create virtualenv
4. Install requirements: PyCharm will prompt, or run `pip install -r requirements.txt` in terminal

**VS Code:**
1. Open project folder
2. Press `Ctrl+Shift+P` → `Python: Select Interpreter`
3. Choose your Python installation
4. Open terminal in VS Code and run `pip install -r requirements.txt`

---

## Running Simulations

### 1. Unified CLI

Use `apps/sim.py` as the main interface for both simple network runs and AI workload experiments.

```bash
python -m apps.sim <command> [options]
```

Every command takes an experiment YAML file via `--config`. Paths are relative to the repo root.

#### Discover what is available

```bash
python -m apps.sim list workloads
python -m apps.sim list routing
```

#### Run one experiment

```bash
python -m apps.sim run --config experiments/dp_single_bucket.yaml
```

#### Override a few parameters without copying YAML files

```bash
python -m apps.sim run --config experiments/dp_single_bucket.yaml --set routing.mode=adaptive
python -m apps.sim run --config experiments/dp_single_bucket.yaml --set topology.params.leaf_count=12
python -m apps.sim run --config experiments/dp_single_bucket.yaml --set topology.params.fabric.link_failure_percent=5
```

#### Validate and inspect the resolved experiment

```bash
python -m apps.sim validate --config experiments/dp_single_bucket.yaml
```

`validate` prints the fully resolved config (after `extends` and `--set` are applied).

To save communication-distribution plots and open them in a window after a run:

```yaml
run:
  visualize: true
  show_visualization_window: true
```

### 2. Batch Execution

Run several experiment files one after another:

```bash
python -m apps.sim batch --config experiments/run1.yaml --config experiments/run2.yaml
python -m apps.sim batch --directory experiments/ --summary-out results/batch-summary.yaml
python -m apps.sim batch --directory experiments/ --stop-on-error
```

`--directory` picks up every `.yaml` / `.yml` file under that folder, skipping anything inside a `base/` folder (shared fragments, not complete experiments).

---

### 3. Sweep Execution

A sweep runs every combination of a set of parameter values on top of one experiment file, in parallel. The `sweep:` section of the experiment file is the only way to set up a sweep: every key below is required, and the `sweep` command takes only `--config`. One command reproduces a whole result set:

```yaml
# experiments/my_sweep.yaml
extends:
  - base/run-defaults.yaml
  - base/topology-clos-small.yaml
  - base/workload-dp.yaml
meta:
  name: my-sweep
sweep:
  vary:                                         # dotted config key -> list of values
    routing.mode: [ecmp, adaptive]
    workload.params.flow_redundancy_extra_packets: [0, 1, 2]
  summary_out: results/my_sweep/summary.yaml    # summary file; plots and deep logs go next to it
  visualize_summary: true                       # comparison plots
  plot_ring_heatmaps: false                     # per-training-step traffic heatmaps
  lower_zoom_percent: 15.0                      # extra training-step-time plot of the lowest 15% (0 = skip it)
  stop_on_error: false                          # stop at the first failed run
  processes: auto                               # worker processes: an integer, or auto (balanced across CPUs)
  plot_topology_once: false                     # draw the topology of the first combination before running
  show_visualization_window: false              # open the plots in a window as well as saving them
```

```bash
python -m apps.sim validate --config experiments/my_sweep.yaml   # prints the sweep plan
python -m apps.sim sweep --config experiments/my_sweep.yaml      # runs all 6 combinations
```

- `run` and `validate` ignore the `sweep` section and use the base values.
- To sweep other values or settings, edit the `sweep:` section (or write a small file that `extends` the experiment and changes it).

To redraw the comparison plots from a saved summary, pass the experiment file too; its `sweep:` section supplies `lower_zoom_percent` and `show_visualization_window`:

```bash
python -m apps.sim plot-summary --summary results/my_sweep/summary.yaml --config experiments/my_sweep.yaml
```

---

## Experiment Configuration

Each experiment is one YAML file under `experiments/`. Shared defaults live in `experiments/base/` and are pulled in with `extends`:

```
experiments/
  base/
    run-defaults.yaml          # run, routing and logging defaults
    topology-clos-small.yaml   # 4 leaf, 4 spine, 16 hosts
    topology-clos-large.yaml   # 8 leaf, 4 spine, 32 hosts
    workload-dp.yaml           # DP-heavy workload defaults
  dp_single_bucket.yaml        # a concrete experiment
```

A concrete experiment lists its fragments and overrides only what it changes:

```yaml
extends:
  - base/run-defaults.yaml
  - base/topology-clos-small.yaml
  - base/workload-dp.yaml
meta:
  name: dp-single-bucket
topology:
  params:
    mtu: 4096
workload:
  params:
    steps: 30
    num_buckets: 1
    single_ring_only: true
```

`extends` paths are relative to the file that contains them. Later entries override earlier ones, the file's own values override everything it extends, and `--set` overrides are applied last. Inheritance can be chained (`a -> b -> c`). Every option is documented with its allowed range in the `experiments/base/` fragments.

There are no in-code defaults: after `extends` is resolved, every key must be present (including `meta.name`, `topology.family` and `run.seed`, where `seed: null` means an unseeded, non-reproducible run), and any key the simulator does not know is an error rather than being ignored.

### Topology model

`topology.family: clos` is the only topology. An experiment must extend a topology fragment (or provide the full `topology.params` block itself). Example overrides:

```yaml
topology:
  params:
    leaf_count: 12
    spine_count: 6
    mtu: 32768
    fabric:
      server_to_leaf_bandwidth_bps: 400000000000
      leaf_to_spine_bandwidth_bps: 400000000000
      link_failure_percent: 5.0
```

### Workload model

- `kind: dp-heavy` selects the DP-heavy training-step model
- `kind: none` runs the topology with no traffic workload

Example:

```yaml
workload:
  kind: dp-heavy
  params:
    bucket_bytes_per_participant: 4194304
    flow_redundancy_extra_packets: 2
```

Each training step runs `prolog_compute_ms` of compute (forward pass plus the backward part that produces the first gradient bucket), then gradient sync, then `optimizer_ms`. Gradient bucket `b` is released `b * bucket_interval_ms` after gradient sync starts, modeling backward compute that overlaps communication. With `bucket_scheduling: concurrent` every bucket starts at its release time and buckets may share the network; with `serialized` bucket `b` waits for bucket `b-1` to finish, like the NCCL bucket queue in PyTorch DDP.

`flow_redundancy_extra_packets` adds a fixed number of redundant packets to each communication flow on top of the useful payload. Redundancy is packet-based now, and the simulator validates that each useful flow payload is already an exact whole number of MTU-sized packets before adding those extras. If a flow has `N` useful packets and `R` redundant packets, it transmits `N + R` packets and completes when any `N` of those packets arrive at the receiver; late redundant/stalled packets may still add network load after the flow has completed.

---

## Analyzing Results

### Log Files

Each run generates a detailed log file containing:
- Topology summary (node/link counts)
- Parameter summary (configuration)
- Run statistics:
  - Training step completion times (mean, p95, p99)
  - Queue occupancy metrics
  - Total simulation time

When `run.visualize: true`, the simulator also saves visualization files under `results/`, including an AI-factory communication distribution figure showing:
- gradient bucket completion-time distributions
- lower-level chunk / flow completion-time distributions

In this project, **gradient buckets are not the same as chunks**:
- a **gradient bucket** is a workload-level communication group within one training step
- a **chunk / flow** is a lower-level send emitted inside that gradient bucket (for example, a ring neighbor send)

**Locations:**
- Unified runs: `results/logs/<run-name>_YYYYMMDD_HHMMSS_*.log`


---

## Running Unit Tests

The project includes comprehensive unit tests for core components:

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test suites
python -m pytest tests/des/ -v
python -m pytest tests/network/ -v
python -m pytest tests/ai_factory/ -v
```

**Test Coverage:**
- DES (Discrete Event Simulation) framework
- Network primitives (ports, queues, routing)
- IP address parsing and prefix matching
- Scenario execution and determinism

---

## Key Concepts

### Routing Modes

1. **ECMP (Equal-Cost Multi-Path)**
   - Hash-based path selection
   - Deterministic per-flow routing
   - Standard baseline

2. **Flowlet**
   - Flow-based routing with periodic re-routing
   - Configurable flowlet threshold (`ecmp_flowlet_n_packets`)
   - Balances persistence and adaptability

3. **Adaptive**
   - Queue-aware routing
   - Selects path with shortest egress queue among ECMP candidates
   - Reacts to congestion in real-time

### Workload Types

1. **DP-Heavy**
   - Single data-parallel job
   - AllReduce collectives across all workers
   - Highly synchronized, bandwidth-intensive

---

## Troubleshooting

### Common Issues

1. **Import Errors**
   - Ensure all dependencies are installed: `pip install -r requirements.txt`
   - Check Python version: `python --version` (requires 3.8+)

2. **Graphviz Errors**
   - Install system Graphviz: https://graphviz.org/download/
   - Add Graphviz to system PATH

3. **Out of Memory (Heavy Runs)**
   - Heavy scenarios are memory-intensive
   - Use light configs for testing: `*_light.yaml`
   - Close other applications during batch runs

4. **Slow Execution**
   - Disable visualization: Set `visualize: false` in YAML
   - Reduce verbosity: Set `message_verbose: false`, `verbose_route: false`
   - Use light configs for validation

### Debug Options

Enable detailed logging in YAML:
```yaml
run:
  file_debug: true           # Full DEBUG logs to file
  message_verbose: true      # Log every packet
  verbose_route: true        # Log routing decisions
```

---

## Development

### Code Style

- Python 3.8+ type hints throughout
- Modular design with clear separation of concerns
- Discrete event simulation paradigm (event-driven)

### Adding New Scenarios

1. Create the scenario/workload implementation in `network/scenarios/` or `ai_factory/scenarios/`
2. Register it in `sim/registry/workloads.py`
3. Add an experiment file under `experiments/` that uses it
4. Validate it with `python -m apps.sim validate --config experiments/<file>.yaml`

### Adding New Routing Algorithms

1. Add a new `RoutingMode` enum value in `network/core/network_node.py`
2. Implement the routing logic in the relevant node forwarding path
3. Expose the new mode through the unified config / CLI interface in `sim/registry/topologies.py`

---

## Performance Characteristics

### Light Configs
- **Steps**: 1-5
- **Runtime**: Seconds to minutes
- **Purpose**: Validation, debugging, quick tests

### Heavy Configs
- **Steps**: 50-200
- **Runtime**: Hours per scenario
- **Purpose**: Full experimental results

### Batch Runs (All Scenarios)
- **Count**: 24+ scenarios (6 routing × 4 load points × 2 workload types)
- **Total Runtime**: Many hours to days
- **Purpose**: Complete comparison study

---

## Citation

If you use this simulator in your research, please cite the accompanying paper:

```bibtex
@techreport{zeltser2026network,
  title={Network Simulator for AI Factory Workloads: Evaluating Routing Strategies in Data Center Fabrics},
  author={Zeltser},
  institution={Ben-Gurion University of the Negev},
  year={2026},
  month={February},
  note={Available in project.pdf}
}
```

For more details, see **`project.pdf`**.

---

## License

This project is available for academic and educational purposes. 

**Academic Use:** Free to use for research and educational purposes with proper citation.

**Commercial Use:** Please contact the authors for licensing terms.

Copyright © 2026 Alon Zeltser. All rights reserved.

---

## Contact

For questions, bug reports, or collaboration inquiries, please contact:

- **Alon Zeltser**: [alonzeltser1@gmail.com](mailto:alonzeltser1@gmail.com)

**Institution:** Ben-Gurion University of the Negev, Department of Computer Science

---

## Acknowledgments

This simulator was developed for studying load-balancing strategies in AI training fabrics, with focus on comparing traditional (ECMP), flow-aware (Flowlet), and congestion-aware (Adaptive) routing approaches.

---

**Last Updated**: February 2026
