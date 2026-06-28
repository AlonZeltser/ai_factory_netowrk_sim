# Network Simulator for AI Factory Workloads

## Project Overview

This project is a **discrete-event network simulator** designed to evaluate routing strategies for AI training workloads in data center fabrics. It focuses on comparing different load-balancing approaches (ECMP, Flowlet, Adaptive) under various traffic patterns and failure scenarios.
Project experiments summary is described in submitted project paper.
This document focus on  instructions for running simulations, analyzing results, and possibly extending the simulator for future research.

### Key Features

- **Multiple Routing Algorithms**: ECMP (Equal-Cost Multi-Path), Flowlet-based routing, and Adaptive routing
- **AI Workload Modeling**: Simulates realistic AI training patterns including:
  - DP (Data Parallel) heavy workloads with AllReduce collectives
  - Mixed workloads combining TP (Tensor Parallel) and PP+DP (Pipeline + Data Parallel)
  - Mice flow injection for latency sensitivity analysis
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
├── sim/                               # Unified config, registries, presets, runners
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

#### Discover what is available

```bash
python -m apps.sim list presets
python -m apps.sim list workloads
python -m apps.sim list routing
```

#### Quick runs from presets

```bash
python -m apps.sim run --preset ai/su-dp-low-small
python -m apps.sim run --preset ai/su-mixed-light
```

#### Override a few parameters without copying YAML files

```bash
python -m apps.sim run --preset ai/su-dp-low-small --set routing.mode=adaptive
python -m apps.sim run --preset ai/su-mixed-light --set topology.params.leaf_count=12
python -m apps.sim run --preset ai/su-mixed-light --set topology.params.fabric.link_failure_percent=5
```

#### Validate and inspect the resolved experiment

```bash
python -m apps.sim validate --preset ai/su-mixed-light
python -m apps.sim validate --config experiments/custom.yaml
```

To save communication-distribution plots and open them in a window after a run:

```yaml
run:
  visualize: true
  show_visualization_window: true
```

#### Generate a starter config from a preset

```bash
python -m apps.sim init --preset ai/su-mixed-light --out experiments/mixed_light.yaml
python -m apps.sim init --preset ai/su-dp-low-small --out experiments/dp-low-small.yaml
```

### 2. Batch Execution

For running multiple experiments sequentially, use the built-in Python batch command instead of a PowerShell script.

#### Batch from presets or config files

```bash
python -m apps.sim batch --preset ai/su-dp-low-small --preset ai/su-mixed-light
python -m apps.sim batch --config experiments/run1.yaml --config experiments/run2.yaml
python -m apps.sim batch --directory experiments/
```

#### Batch output summary

```bash
python -m apps.sim batch --preset ai/su-dp-low-small --preset ai/su-mixed-light --summary-out results/batch-summary.yaml
```

#### Stop on first failure

```bash
python -m apps.sim batch --directory experiments/ --stop-on-error
```

---

### 3. Sweep Execution

For cartesian parameter sweeps, use the built-in sweep command.

```bash
python -m apps.sim sweep --preset ai/su-dp-low-small --vary routing.mode=ecmp,adaptive --vary topology.params.leaf_count=8,16
python -m apps.sim sweep --preset ai/su-mixed-light --vary topology.params.fabric.link_failure_percent=0,5 --summary-out results/sweep.yaml
```

This replaces the old shell-driven workflow for selecting many scenario combinations manually.

---

## Unified Configuration Structure

The new config model is centered on one concept: an **experiment**.

```yaml
kind: experiment

meta:
  name: ai-su-mixed-light
  description: Example mixed workload on the AI scale-unit clos preset

run:
  file_debug: false
  message_verbose: false
  verbose_route: false
  visualize: false

topology:
  params:
    leaf_count: 8
    spine_count: 4
    fabric:
      bandwidth_profile: 4g
      link_failure_percent: 0.0

routing:
  mode: ecmp
  ecmp_flowlet_n_packets: 0

workload:
  kind: mixed
  params: {}
```

### Topology model

Topology defaults now live in YAML preset fragments under `sim/presets/ai/`, and concrete presets usually override only `topology.params`.

- the default AI scale-unit clos shape is described in `sim/presets/ai/topology-clos-scale-unit.yaml`
- `topology.params` lets you override only the knobs you care about in the concrete preset

AI presets inherit their topology shape from that YAML fragment, so most configs only need to edit `topology.params`. Topology shape is now primarily exposed through the YAML preset chain rather than a dedicated listing command.

There are no longer in-code topology defaults for `clos`: if you create a standalone config, inherit the topology fragment (or provide the full required `topology.params` block yourself).

Example overrides:

```yaml
topology:
  params:
    leaf_count: 12
    spine_count: 6
    mtu: 32768
    fabric:
      bandwidth_profile: 400g
      link_failure_percent: 5.0
```

### Workload model

Workload defaults now live in YAML preset fragments under `sim/presets/ai/`, and concrete presets usually override only `workload.params`.

- `kind: dp-heavy` selects the DP-heavy training-step model
- `kind: mixed` selects the concurrent TP-heavy + PP+DP model
- built-in presets like `su-dp-low-small.yaml` and `su-mixed-light.yaml` inherit documented workload fragments for their common defaults

Example:

```yaml
workload:
  kind: dp-heavy
  params:
    bucket_bytes_per_participant: 4194304
    chunk_redundancy_extra_packets: 2
    mice:
      enabled: false
```

`chunk_redundancy_extra_packets` adds a fixed number of redundant packets to each communication flow on top of the useful payload. Redundancy is packet-based now, and the simulator validates that each useful flow payload is already an exact whole number of MTU-sized packets before adding those extras. If a flow has `N` useful packets and `R` redundant packets, it transmits `N + R` packets and completes when any `N` of those packets arrive at the receiver; late redundant/stalled packets may still add network load after the flow has completed.

### Preset inheritance

Preset YAML files can extend a base preset, and chained inheritance like `a -> b -> c` is supported.

```yaml
extends:
  - presets-experiments-base.yaml
  - workload-dp-heavy-low.yaml
meta:
  name: ai-su-dp-low-small
```

The AI preset stack now works roughly like:

- `su-dp-low-small.yaml` inherits from `base-ai-su.yaml` and `workload-dp-heavy-low.yaml`
- `base-ai-su.yaml` inherits from `topology-clos-scale-unit.yaml`
- `workload-dp-heavy-low.yaml` inherits from `workload-dp-heavy-base.yaml`

This keeps the preset library compact and avoids duplicating nearly identical experiment files while keeping topology, routing, and workload defaults visible in YAML.

---

## Analyzing Results

### Log Files

Each run generates a detailed log file containing:
- Topology summary (node/link counts)
- Parameter summary (configuration)
- Run statistics:
  - Step completion times (mean, p95, p99)
  - Mice flow FCT statistics
  - Queue occupancy metrics
  - Total simulation time

When `run.visualize: true`, the simulator also saves visualization files under `results/`, including an AI-factory communication distribution figure showing:
- bucket completion-time distributions
- lower-level chunk / flow completion-time distributions

In this project, **buckets are not the same as chunks**:
- a **bucket** is a workload-level communication group (for example, one DP gradient bucket)
- a **chunk / flow** is a lower-level send emitted inside that bucket (for example, a ring neighbor send)

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

2. **Mixed**
   - Two concurrent jobs:
     - **TP-Heavy**: Tensor parallel with many micro-collectives
     - **PP+DP**: Pipeline parallel with data parallel synchronization
   - Diverse message sizes and patterns
   - Tests routing under heterogeneous traffic

### Mice Flows

- Background short flows injected during training
- Used to measure latency sensitivity under load
- Configurable arrival rate, size distribution, cross-rack enforcement

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
3. Add or update presets under `sim/presets/`
4. Validate it with `python -m apps.sim validate ...`

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
