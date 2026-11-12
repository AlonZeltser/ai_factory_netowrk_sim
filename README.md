# Network Simulator for AI Factory Workloads

## Project Overview

This project is a **discrete-event network simulator** for studying how AI training traffic behaves in a data-center fabric. The main research question is how **retransmit-like packet stalls** slow down ring collectives (the gradient synchronization of data-parallel training), and how much **flow-level packet redundancy** recovers that time.

The simulator models a two-layer clos (leaf-spine) fabric, a data-parallel training job that synchronizes gradients with ring collectives, packet stalls injected at switches, and three routing modes (ECMP, flowlet, adaptive). Experiments are YAML files; a sweep runs every combination of chosen parameter values in parallel and draws comparison plots. A separate interactive tool, the **Ring Collective Stall Visualizer**, shows how each ring chain progressed and where it stalled.

This document covers installation, running simulations and sweeps, the config format, the outputs, and the visualizer.

### Key Features

- **Routing modes**: ECMP (hash-based), flowlet (ECMP that rehashes every N packets) and adaptive (least-loaded egress queue)
- **AI workload model**: a DP-heavy training job; each step runs compute, then synchronizes gradient buckets with a ring all-reduce (reduce-scatter + all-gather, or reduce-scatter only)
- **Packet stall regime**: a chosen percentage of packets is held at a switch and re-sent from the source host after a delay, like a retransmission; retransmitted packets can optionally get queue priority
- **Flow redundancy**: extra packets per flow; a flow completes when any `N` of its `N + R` packets arrive
- **Link failures**: a percentage of fabric links can be marked failed when the topology is built
- **Sweeps**: every combination of `sweep.vary` values, run in parallel worker processes, with a summary file, comparison plots and CSV data
- **Metrics**: training-step and job time, gradient-bucket time, ring flow time, stall counts per flow, queue peaks, link utilization, drops
- **Visualizer**: Gantt and heatmap views of ring chains from the per-step chain logs

---

## Project Structure

```
ai_factory_netowrk_sim/
├── apps/
│   ├── sim.py                          # Main CLI: run, validate, sweep, plot-summary, list
│   └── render_results.py               # Small script to re-render plots from a saved summary (edit its paths)
├── sim/                                # Experiment layer
│   ├── config/                         # YAML loading (extends, paths) and config validation
│   ├── registry/                       # Builds the network and the workload from a config
│   └── runners/                        # Single run, sweep execution, deep flow chain logs
├── experiments/                        # Experiment YAML files
│   ├── base/                           # Shared fragments (run, topology, routing, stall regime, workload)
│   ├── research_configurations/        # The research sweep and single run
│   └── dp_single_bucket.yaml
│
├── ai_factory/                         # AI workload modeling
│   ├── core/                           # Training job, steps, phases, gradient buckets, job runner
│   ├── scenarios/                      # DP-heavy scenario and the flow injector (packetization, redundancy)
│   ├── simulators/                     # The clos (AI-factory scale unit) topology builder
│   ├── traffic/                        # Collectives and the ring pattern
│   └── workloads/                      # DP-heavy workload definition
│
├── network/                            # Network simulation engine
│   ├── core/                           # Hosts, switches, links, ports/queues, packets, IPs, routing modes
│   └── scenarios/                      # Scenario base class
│
├── des/                                # Discrete-event scheduler and packet statistics
├── visualization/                      # Result plots and topology drawing
│   ├── experiment_visualizer.py        # Run and sweep plots
│   ├── visualizer.py                   # Topology drawing
│   ├── build_topology_viz.py           # Draw the topology of a config without running it
│   └── QUICKREF.py                     # Quick reference for the topology drawing tool
├── ring_collective_stall_visualizer/   # Interactive ring chain visualizer (Streamlit) and PDF export
│
├── log_setup.py                        # Run logging setup
├── run_label.py                        # Turns sweep run labels into short file names
├── tests/                              # Unit tests (pytest)
├── pytest.ini
├── requirements.txt                    # Python dependencies of the simulator
└── results/                            # Output logs, plots and summaries (created by runs)
```

---

## Installation

### Prerequisites

- **Python 3.13** (the version the project is developed and tested with)
- **Git**

No system packages are needed. Topology drawings use `networkx` and `matplotlib`.

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/AlonZeltser/ai_factory_netowrk_sim.git
   cd ai_factory_netowrk_sim
   ```

2. Create a virtual environment and install the dependencies:
   ```bash
   python -m venv venv
   venv\Scripts\activate            # Windows
   source venv/bin/activate         # Linux / macOS
   pip install -r requirements.txt
   pip install -r ring_collective_stall_visualizer/requirements.txt
   ```
   The second file adds the visualizer's packages (Streamlit, plotly, kaleido). The test suite and the sweep's Gantt PDFs need them too. kaleido draws the PDFs with a Chrome browser; if Chrome is not installed, run `plotly_get_chrome` once.

3. Verify the installation by running the unit tests:
   ```bash
   python -m pytest -q
   ```

#### IDE Setup (Optional)

**PyCharm:**
1. Open the project: `File` → `Open` → select the repository folder
2. Set the interpreter: `File` → `Settings` → `Project` → `Python Interpreter` → `Add Interpreter` → `Virtualenv` (or select the `venv` created above)
3. Install the requirements when PyCharm prompts, or run the two `pip install` commands in the terminal
4. Tests can be run from any folder (for example right-click `tests/`); `pytest.ini` puts the repository root on the import path

**VS Code:**
1. Open the project folder
2. Press `Ctrl+Shift+P` → `Python: Select Interpreter` → choose the `venv`
3. Run the two `pip install` commands in the VS Code terminal

---

## Running Simulations

### 1. Unified CLI

Use `apps/sim.py` for everything:

```bash
python -m apps.sim <command> [options]
```

| Command | What it does |
|---|---|
| `run --config FILE` | Run one experiment |
| `validate --config FILE` | Check the config, print the resolved values and the sweep plan |
| `sweep --config FILE` | Run every combination in the config's `sweep:` section |
| `plot-summary --summary FILE --config FILE --out-dir DIR` | Redraw the comparison plots from a saved sweep summary |
| `list routing` | List the routing modes |

#### Run one experiment

```bash
python -m apps.sim run --config experiments/dp_single_bucket.yaml
python -m apps.sim run --config experiments/research_configurations/single_run.yaml
```

#### Run a variation of an experiment

The YAML file is the only way to set experiment values. To change a few of them, write a small file that `extends` the experiment and overrides only those keys:

```yaml
# experiments/dp_single_bucket_ecmp.yaml
extends: dp_single_bucket.yaml
name: dp-single-bucket-ecmp
routing:
  mode: ecmp
topology:
  leaf_count: 8
```

```bash
python -m apps.sim run --config experiments/dp_single_bucket_ecmp.yaml
```

To run many variations, use a sweep (below).

#### Validate and inspect the resolved experiment

```bash
python -m apps.sim validate --config experiments/dp_single_bucket.yaml
```

`validate` builds the network and workload without running them, prints the fully resolved config (after `extends`), and prints the sweep plan if the file has one.

To save communication-distribution plots after a run (and open them in a window):

```yaml
visualize: true
show_visualization_window: true
```

### 2. Sweep Execution

A sweep runs every combination of a set of parameter values on top of one experiment file, in parallel worker processes. The `sweep:` section of the experiment file is the only way to set up a sweep: every key below is required, and the `sweep` command takes only `--config`. One command reproduces a whole result set.

The research sweep is `experiments/research_configurations/main_sweep.yaml` (9 redundancy values x 10 stall percentages = 90 runs):

```yaml
extends:
  - run-research.yaml
  - ../base/topology-clos-small.yaml
  - ../base/routing-default.yaml
  - ../base/stall_regime-default.yaml
  - ai_workload-research.yaml
name: research-sweep
sweep:
  vary:                                         # dotted config key -> list of values
    ai_workload.flow_redundancy_extra_packets: [0, 1, 2, 3, 4, 6, 8, 12, 16]
    stall_regime.packet_stall_percent: [0, 0.02, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8]
  summary_out: repo:results/research-sweep/main_sweep_summary.yaml   # summary file; plots and deep logs go next to it
  visualize_summary: true                       # comparison plots
  plot_ring_heatmaps: false                     # per-training-step traffic heatmaps
  lower_zoom_percent: 15.0                      # extra training-step-time plot of the lowest 15% (0 = skip it)
  stop_on_error: false                          # stop at the first failed run
  processes: auto                               # worker processes: an integer, or auto (balanced across CPUs)
  plot_topology_once: false                     # draw the topology of the first combination before running
  show_visualization_window: false              # open the plots in a window as well as saving them
  paper_style: true                             # paper look (no title, white, 6x3.6 in, 9 pt) for the step-time, best-redundancy and slowdown plots
  gantt_pdfs: true                              # visualizer Gantt PDFs of the first, middle and slowest step of each run (needs deep_flow_chain_log: true)
  gantt_chain_limit: 40                         # most ring chains drawn in one Gantt
  gantt_compare:                                # also put runs that differ only in this vary key side by side (2 to 4 values; {} = none)
    ai_workload.flow_redundancy_extra_packets: [0, 2, 8, 16]
  plot_layout:                                  # layout plot: stall percent on x, one line per redundancy, like the other plots
    x: stall_regime.packet_stall_percent
    lines: ai_workload.flow_redundancy_extra_packets
```

```bash
python -m apps.sim validate --config experiments/research_configurations/main_sweep.yaml   # prints the sweep plan
python -m apps.sim sweep --config experiments/research_configurations/main_sweep.yaml      # runs all 90 combinations
```

- Any config key can be swept, e.g. `routing.mode: [ecmp, adaptive]` or `stall_regime.packet_stall_delay_ms: [2, 8, 32]`.
- Two more research sweeps use the same base files and sweep settings, each writing to its own results folder:
  - `message_size_sweep.yaml`: 1000 packets per flow and an 80 ms stall delay. It varies the stall percent and the redundancy, and writes to `results/message-size-sweep/`.
  - `stall_delay_sweep.yaml`: varies the stall percent, the redundancy and the stall delay, and writes to `results/stall-delay-sweep/`.
- The optional `plot_layout: {split: <vary key>, x: <vary key>, lines: <vary key>}` sets the layout plot (see [Sweep outputs](#sweep-outputs)). Without it, the roles follow the order of the `vary` keys: with 2 keys, x = first and lines = second; with 3 keys, split = first, x = second and lines = third. With any other number of keys there is no layout plot.
- `run` and `validate` ignore the `sweep` section and use the base values.
- `processes: auto` spreads the runs across the CPU cores; a stronger machine finishes a sweep proportionally faster.
- `gantt_pdfs: true` makes the visualizer's Gantt charts during the sweep, without opening the web app (see [Gantt PDFs from a sweep](#gantt-pdfs-from-a-sweep)). The sweep checks before it starts that every run has `deep_flow_chain_log: true` and that PDF export works, so a missing package fails at once rather than after hours of runs.

To redraw the comparison plots from a saved summary, pass the experiment file and an output folder; the file's `sweep:` section supplies `lower_zoom_percent`, `show_visualization_window` and `paper_style`:

```bash
python -m apps.sim plot-summary --summary results/research-sweep/main_sweep_summary.yaml --config experiments/research_configurations/main_sweep.yaml --out-dir results/research-sweep/replot
```

---

## Experiment Configuration

Each experiment is one YAML file under `experiments/`. Shared fragments live in `experiments/base/` and are pulled in with `extends`:

```
experiments/
  base/
    run-defaults.yaml          # run and logging settings (top-level keys)
    topology-clos-small.yaml   # topology: 4 leaf, 4 spine, 16 hosts
    topology-clos-large.yaml   # topology: 8 leaf, 4 spine, 32 hosts
    routing-default.yaml       # routing: mode, MTU, TTL, max path
    stall_regime-default.yaml  # stall_regime: retransmit-like packet stalls
    ai_workload-default.yaml   # ai_workload: DP-heavy training job
  research_configurations/
    run-research.yaml          # run settings for the research (fixed seed)
    ai_workload-research.yaml  # workload for the research (one bucket, reduce-scatter only)
    main_sweep.yaml            # the research sweep
    single_run.yaml            # one research run
  dp_single_bucket.yaml        # a standalone experiment
```

A config has these parts: the experiment `name` and the run settings as top-level keys, then the `topology`, `routing`, `stall_regime` and `ai_workload` sections (plus an optional `sweep`). A concrete experiment lists one fragment per part and overrides only what it changes:

```yaml
extends:
  - base/run-defaults.yaml
  - base/topology-clos-small.yaml
  - base/routing-default.yaml
  - base/stall_regime-default.yaml
  - base/ai_workload-default.yaml
name: dp-single-bucket
deep_flow_chain_log: true
stall_regime:
  packet_stall_delay_ms: 2
ai_workload:
  steps: 30
  num_buckets: 1
  single_ring_only: true
```

Every key is documented with its allowed values in the `experiments/base/` fragments.

Paths follow two rules, so a config behaves the same whether it is launched from a terminal in any directory, an IDE, or a GUI:

- **Paths written in a YAML file** (`extends`, `log_dir`, `results_dir`, `sweep.summary_out`) are relative to the file that contains them. Start a path with `repo:` to anchor it at the repository root instead, e.g. `results_dir: repo:results`. Absolute paths are kept as is.
- **Paths given on the command line** (`--config`, `--summary`, `--out-dir`) are relative to the current directory, like any other command-line tool. `repo:` works there too.

Later `extends` entries override earlier ones, and the file's own values override everything it extends. Inheritance can be chained (`a -> b -> c`).

There are no in-code defaults: after `extends` is resolved, every key must be present (including `name` and `seed`, where `seed: null` means an unseeded, non-reproducible run), and any key the simulator does not know is an error rather than being ignored.

### Run settings (top-level keys)

| Key | Meaning |
|---|---|
| `name` | Experiment name, used in log file names |
| `seed` | Seed for packet stalls and routing tie-breaks; `null` = unseeded |
| `file_debug`, `message_verbose`, `verbose_route` | Logging detail (see Troubleshooting) |
| `visualize`, `show_visualization_window` | Save (and show) plots after a single run |
| `store_packets`, `collect_packet_timeline` | Keep packet objects / a per-packet timeline in memory |
| `deep_flow_chain_log` | Write per-step ring chain logs in a sweep (input for the visualizer); on in the research config. It only records data and does not change the results |
| `log_dir`, `results_dir` | Where logs and result files go |

### Topology model

The topology is always a two-layer clos (leaf-spine): every leaf connects to every spine, servers connect to their leaf. An experiment must extend a topology fragment (or provide the full `topology` section itself). Example overrides:

```yaml
topology:
  leaf_count: 12
  spine_count: 6
  host_links_per_server: 2
  parallel_leaf_to_spine_links: 2
  server_to_leaf_bandwidth_bps: 400000000000
  leaf_to_spine_bandwidth_bps: 400000000000
  link_failure_percent: 5.0
```

### Routing

```yaml
routing:
  mode: adaptive               # ecmp | adaptive | flowlet
  ecmp_flowlet_n_packets: 0    # flowlet: rehash every N packets (must be > 0 for flowlet)
  mtu: 4096                    # packet size in bytes
  ttl: 1000                    # hops before a packet is dropped
  max_path: 64
```

### Stall regime

Each packet is tagged for a stall with probability `packet_stall_percent`, at a random switch hop up to `packet_stall_max_switch_hop`. When the tagged packet reaches that switch it is taken out of the network and re-sent from its source host after `packet_stall_delay_ms`, like a retransmission after a loss. With `packet_stall_retransmit_priority: true`, re-sent packets go ahead of regular packets in every egress queue.

```yaml
stall_regime:
  packet_stall_percent: 0.01
  packet_stall_delay_ms: 8.0
  packet_stall_max_switch_hop: 2
  packet_stall_retransmit_priority: false
```

### Workload model

The workload is always the DP-heavy training-step model: one data-parallel training job over all servers. Example:

```yaml
ai_workload:
  steps: 30
  num_buckets: 1
  bucket_bytes_per_participant: 6553600
  flow_redundancy_extra_packets: 2
  single_ring_only: true
```

Each training step runs `prolog_compute_ms` of compute (forward pass plus the backward part that produces the first gradient bucket), then gradient sync, then `optimizer_ms`. Gradient bucket `b` is released `b * bucket_interval_ms` after gradient sync starts, modeling backward compute that overlaps communication. With `bucket_scheduling: concurrent` every bucket starts at its release time and buckets may share the network; with `serialized` bucket `b` waits for bucket `b-1` to finish, like the NCCL bucket queue in PyTorch DDP.

Each bucket is synchronized with a ring all-reduce: a reduce-scatter ring followed by an all-gather ring (`single_ring_only: true` runs only the reduce-scatter). In each ring step every host sends one chunk to its ring neighbor, and the next step waits for the previous one. The ring order is fixed by `ai_workload.seed`.

`flow_redundancy_extra_packets` adds a fixed number of redundant packets to each communication flow on top of the useful payload. Each useful flow payload must be a whole number of MTU-sized packets. If a flow has `N` useful packets and `R` redundant packets, it transmits `N + R` packets and completes when any `N` of them arrive at the receiver; late redundant or stalled packets may still add network load after the flow has completed.

---

## Analyzing Results

### Run log files

Every run (including each run of a sweep) writes a log file to `results/logs/<name>_YYYYMMDD_HHMMSS_*.log`. It contains:
- **Experiment parameters**: every resolved config value
- **Network summary**: topology counts, simulated time, packet counts and drops, packet times, route lengths, link delivery times and utilization, queue peaks, stall counts
- **AI-factory summary**: training-step time (avg, p95, p99, std, min, max), training job duration, ring flow time statistics

With `visualize: true`, a single run also saves plots under `results/`, including an AI-factory communication distribution figure (gradient bucket and flow completion-time distributions).

In this project, **gradient buckets are not the same as flows**:
- a **gradient bucket** is a workload-level communication group within one training step
- a **flow** (chunk) is one send inside that bucket, e.g. one ring neighbor send

### Sweep outputs

Everything goes next to `sweep.summary_out` (for the research sweep: `results/research-sweep/`):
- **Summary YAML**: one row per run with the swept values and all metrics (flow, ring flow, bucket, training-step and job times; stall counts and the stalls-per-flow histogram; redundancy and packet counts; drops). With `gantt_pdfs: true`, `deep_flow_chain_sample_steps` lists the sample steps of each run. The raw chain records are left out; the chain logs hold them
- **Comparison plots** (PNG + PDF, with `visualize_summary: true`): each time metric against the stall percent (or link failure percent), one line per redundancy value; the zoomed lower part of the training-step-time plot; the best redundancy per stall percent; the slowdown heatmap (`training_step_slowdown_heatmap`: mean step time of each (R, p) divided by that of the healthy run R = 0, p = 0, best R of each column in bold); per-redundancy charts under `detailed_charts/`
- **Skipped comparison plots**: the comparison plots above (and their CSVs) group runs only by redundancy and the stall (or link failure) percent. If the sweep also varies another key, for example `stall_regime.packet_stall_delay_ms` in `stall_delay_sweep.yaml`, they would merge runs, so they are skipped with a one-line message. The layout plot and the Gantt PDFs are still written
- **Layout plot** (with `visualize_summary: true`): `training_step_time_layout.pdf`, in the paper style. It shows the mean training step time with a ±std band, with one panel per `split` value side by side, the `x` key on the x axis and one line per `lines` value. Only this PDF is written, with no timestamped copy
- **Fixed-name PDFs**: every plot is also written as a PDF without the timestamp (e.g. `training_step_time_vs_packet_stall.pdf`), so a LaTeX paper can include it directly; each sweep overwrites them
- **Paper style** (`paper_style: true`): the training-step-time (mean ± std), best-redundancy and slowdown plots have no title, a white background with a light grid, legend entries `R = 0`, `R = 1`, … and a 6 x 3.6 in size with ~9 pt text. The slowdown heatmap always uses this style
- **CSV files**: the training-step-time points and the stall distribution behind the plots
- **Traffic heatmaps** per training step (with `plot_ring_heatmaps: true`)
- **Deep flow chain logs** (with `deep_flow_chain_log: true` in the config): `deep_flow_chain_logs/<run>/job_<j>_step_<s>.txt`, one file per training step, listing every ring chain hop by hop. These are the input of the visualizer below. With `gantt_pdfs: true`, only the sample steps get a log.
- **Gantt PDFs** (with `gantt_pdfs: true`): `gantt_pdfs/`, see below.

### Ring Collective Stall Visualizer

An interactive Streamlit dashboard for the deep flow chain logs. It answers questions like which ring chains stalled, when, at which hop, and how two runs differ.

Start it from the repository root:

```bash
cd ring_collective_stall_visualizer
python -m streamlit run app.py
```

Then, in the browser:
1. Upload a chain log (`.txt` or `.log`). Up to three more logs can be uploaded for side-by-side comparison.
2. Choose the view: **Gantt** (each chain's hops over simulation time: when stalls happened), **Heatmap** (metric per chain and hop: where the cost is), or **Both**.
3. Filter by job, step, phase, bucket or operation, and limit the number of chains drawn.
4. Color by stall bucket, stalled packets, duration, max egress queue position or average egress queue position.
5. Download any chart as PNG or PDF.

To make a Gantt PDF from the command line (for reports), use `export_gantt_pdf.py` with one to four logs:

```bash
python ring_collective_stall_visualizer/export_gantt_pdf.py run_a.txt run_b.txt --labels "No redundancy,2 extra packets" --color-by stalled_packets --chain-limit 16 --out gantt.pdf
```

`--color-by` is one of `stall_bucket`, `stalled_packets`, `duration_ms`, `max_egress`, `avg_egress`; `--filter key=v1,v2` (repeatable) narrows the data. See `ring_collective_stall_visualizer/README.md` for every view and option.

#### Gantt PDFs from a sweep

A sweep has too many steps to open each one in the web app, so with `sweep.gantt_pdfs: true` it draws a sample itself, using the same Gantt code as the app (colored by stalled packets). For each run it picks three training steps:
- **first**: the first step
- **middle**: the middle step
- **slowest**: the step whose ring flows took longest, from the first flow start to the last flow end

Only these steps are kept (in the worker processes) and written as chain logs, which keeps memory and disk use small. A step picked twice (for example first and slowest) gets one PDF. The output, under `gantt_pdfs/` next to the summary:
- `gantt_pdfs/<run>/job_<j>_step_<s>_<kinds>.pdf`: one PDF per sample step of each run
- `gantt_pdfs/compare_<key>/<other values>_<kind>.pdf` (with `gantt_compare`): for each combination of the other vary keys, the runs with the listed values of the compared key, one panel each, in the listed order. For example `compare_flow_redundancy_extra_packets/packet_stall_percent_1_slowest.pdf` shows the slowest step at 1% stalls with 0, 2, 8 and 16 extra packets. Each panel names the step it shows, since each run has its own slowest step.

`gantt_chain_limit` caps the ring chains drawn per panel (the research ring has 16). Export takes about 0.7 s per PDF; the research sweep makes up to about 300 (up to 270 single-run PDFs and 30 comparisons), about 4 minutes in total. The chain logs stay in `deep_flow_chain_logs/`, so any of them can still be opened in the web app.

### Topology drawing

To draw the topology of a config without running it:

```bash
python visualization/build_topology_viz.py --config experiments/dp_single_bucket.yaml
```

See `visualization/QUICKREF.py` for the options.

---

## Running Unit Tests

```bash
# Run all tests
python -m pytest -q

# Run specific test suites
python -m pytest tests/des
python -m pytest tests/network
python -m pytest tests/ai_factory
python -m pytest tests/sim
python -m pytest tests/ring_collective_stall_visualizer
```

**Test coverage:**
- Discrete-event scheduler and packet time statistics
- Network primitives: IP parsing, port queues, retransmit priority, routing modes, packet stalls
- AI workload: ring ordering and dependencies, bucket timing, flow redundancy, flow injection, run logging
- Experiment layer: config keys and paths, sweeps (parsing, execution, parallelism), run labels, plots
- Visualizer: chain log parsing and PDF export, and the sweep's Gantt PDFs (sample steps, comparison groups, settings)

---

## Key Concepts

### Routing Modes

1. **ECMP (Equal-Cost Multi-Path)**
   - Hashes the packet's flow 5-tuple to pick one of the equal-cost next hops
   - All packets of a flow take the same path
   - Standard baseline

2. **Flowlet**
   - ECMP whose hash input changes every `ecmp_flowlet_n_packets` packets
   - Each group of N packets of a flow can take a different path

3. **Adaptive**
   - Queue-aware: picks among the equal-cost next hops with the shortest egress queue (ties broken at random)
   - Packets of one flow can take different paths; reacts to congestion immediately

### Workload

**DP-Heavy**: one data-parallel training job over all servers. Each training step synchronizes its gradient buckets with ring collectives, so the step ends only when the slowest ring chain finishes; one stalled packet can delay the whole step.

---

## Troubleshooting

### Common Issues

1. **Import errors**
   - Install both requirement files (see Setup)
   - Check the Python version: `python --version` (3.13)

2. **Config errors** (`Unknown key ...`, `Missing required key ...`)
   - Run `python -m apps.sim validate --config <file>`; the message names the exact key
   - Check the indentation under `sweep: vary:` (the swept keys must be indented below `vary:`)

3. **Out of memory**
   - Keep `store_packets: false` and `collect_packet_timeline: false`
   - Set `sweep.processes` to a smaller number than `auto`

4. **Slow execution**
   - Keep `visualize: false` for sweeps, and `message_verbose: false`, `verbose_route: false`, `file_debug: false`
   - Lower `ai_workload.steps` while trying out a config

### Debug Options

Enable detailed logging in the YAML:
```yaml
file_debug: true           # Full DEBUG logs to file
message_verbose: true      # Log every packet
verbose_route: true        # Log routing decisions
```

---

## Development

### Code Style

- Python type hints throughout
- Discrete-event simulation (event-driven)
- Strict configs: every key required, unknown keys rejected

### Adding a config key

1. Add the field to the right section class in `sim/config/models.py` (`TopologySpec`, `RoutingSpec`, `StallRegimeSpec`, `AIWorkloadSpec`, or `RunSpec` for top-level keys)
2. Pass it on in `sim/registry/topologies.py` (network) or `sim/registry/workloads.py` (workload)
3. Add it, with a comment on its allowed values, to the matching fragment in `experiments/base/`

### Adding New Routing Algorithms

1. Add a new `RoutingMode` enum value in `network/core/network_node.py`
2. Implement the port selection in the node forwarding path
3. Map the new `routing.mode` value to it in `sim/registry/topologies.py`

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

**Last Updated**: November 2026
