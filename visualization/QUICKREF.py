#!/usr/bin/env python3
"""
Quick Reference: Topology Visualization Helper Script

This script makes it easy to visualize network topologies without running a full simulation.
"""

# ============================================================================
# BASIC USAGE
# ============================================================================

# Generate visualization for an experiment config
# python visualization/build_topology_viz.py --config experiments/dp_single_bucket.yaml

# Save the drawing to a specific file
# python visualization/build_topology_viz.py --config experiments/dp_single_bucket.yaml --output results/topology.png

# Draw a variation: write a small YAML file that `extends` the experiment and changes it
# (see PARAMETERS below), then pass that file to --config.


# ============================================================================
# COMMON EXAMPLES
# ============================================================================

"""
1. View a small topology with link failures. Write experiments/small_failures.yaml:

     extends: dp_single_bucket.yaml
     topology:
       leaf_count: 2
       spine_count: 2
       link_failure_percent: 20

   then run:
   python visualization/build_topology_viz.py --config experiments/small_failures.yaml

2. Show the healthy/failed link entries in the legend:
   python visualization/build_topology_viz.py --config experiments/small_failures.yaml --show-link-status-legend
"""


# ============================================================================
# COLOR SCHEME (COLORBLIND SAFE)
# ============================================================================

"""
Node Colors:
   Orange  = Spine Switches (upper layer)
   Teal    = Leaf Switches (lower layer)
   Purple  = Hosts/Servers (hosts connected to leaves)

Link Status:
  ─ Gray solid line     = Healthy link
  - - Red dashed line   = Failed link
"""


# ============================================================================
# PARAMETERS
# ============================================================================

PARAMETERS = """
Common topology keys to change in a YAML file that extends the experiment:

  topology.leaf_count                    Number of leaf switches
  topology.spine_count                   Number of spine switches
  topology.servers_per_leaf              Number of servers per leaf switch
  topology.host_links_per_server         Parallel NIC connections per server
  topology.parallel_leaf_to_spine_links  Parallel links between each leaf-spine pair
  topology.link_failure_percent          Percentage of links to fail (0-100)

Tool options:

  --config FILE                Experiment YAML file (required)
  --output FILE                Save the drawing here instead of results/
  --show-link-status-legend    Show healthy/failed link entries in the legend
"""


# ============================================================================
# EXPERIMENT FILES
# ============================================================================

EXPERIMENTS = """
Experiment configs live in experiments/ (one YAML file per experiment).
Shared fragments live in experiments/base/:
  - run-defaults.yaml          : run and logging settings
  - topology-clos-small.yaml   : 4 leaf, 4 spine, 16 hosts
  - routing-default.yaml       : routing mode, MTU, TTL, max path
  - stall_regime-default.yaml  : packet stall settings
  - ai_workload-default.yaml   : DP-heavy workload defaults
"""


# ============================================================================
# OUTPUT
# ============================================================================

OUTPUT_INFO = """
Output Location: results/topology_<name>_<timestamp>_<version>.png

Console Output Example:
  ✓ Topology visualization saved to:
    C:\\..\\results\\topology_ai-factory-su_20260720_094341_1.png

  Topology Info:
    Name: ai-factory-su
    Switches: 8
    Hosts: 16
    Total nodes: 88
"""


# ============================================================================
# TROUBLESHOOTING
# ============================================================================

TROUBLESHOOTING = """
❌ "No nodes to visualize"
   → Check that the config file is valid
   → Verify topology configuration

❌ Visualization too crowded
   → Reduce the topology size in a YAML file that extends the experiment

❌ Matplotlib not found
   → pip install matplotlib networkx
   → Set MPLBACKEND=Agg

❌ "Config file not found"
   → Paths are relative to the repo root, e.g. experiments/dp_single_bucket.yaml
"""


if __name__ == "__main__":
    print(__doc__)
    print("\n" + "="*70)
    print("PARAMETERS")
    print("="*70)
    print(PARAMETERS)
    print("\n" + "="*70)
    print("EXPERIMENT FILES")
    print("="*70)
    print(EXPERIMENTS)
    print("\n" + "="*70)
    print("OUTPUT")
    print("="*70)
    print(OUTPUT_INFO)
    print("\n" + "="*70)
    print("TROUBLESHOOTING")
    print("="*70)
    print(TROUBLESHOOTING)
