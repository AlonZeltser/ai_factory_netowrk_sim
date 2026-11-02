#!/usr/bin/env python3
"""
Quick Reference: Topology Visualization Helper Script

This script makes it easy to visualize network topologies without running a full simulation.
"""

# ============================================================================
# BASIC USAGE
# ============================================================================

# Generate visualization for a preset
# python visualization/build_topology_viz.py --preset ai/su-dp-low-small

# Generate with custom parameter
# python visualization/build_topology_viz.py --preset ai/su-dp-low-small --set topology.params.leaf_count=8

# Generate with better spacing for large topologies
# python visualization/build_topology_viz.py --preset ai/su-dp-low-small --spacing 3.0


# ============================================================================
# COMMON EXAMPLES
# ============================================================================

"""
1. View a small topology:
   python visualization/build_topology_viz.py --preset ai/su-dp-tiny

2. View and customize:
   python visualization/build_topology_viz.py --preset ai/su-dp-low-small \\
     --set topology.params.leaf_count=8 \\
     --set topology.params.spine_count=8

3. Show link failures:
   python visualization/build_topology_viz.py --preset ai/su-dp-low-small \\
     --set topology.params.fabric.link_failure_percent=20

4. Large topology with good readability:
   python visualization/build_topology_viz.py --preset ai/su-dp-low-small \\
     --set topology.params.leaf_count=16 \\
     --spacing 4.0

5. Using custom config file:
   python visualization/build_topology_viz.py --config my-config.yaml

6. List all available presets:
   python -m apps.sim list presets
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
Common Topology Parameters to Override:

  topology.params.leaf_count=N
    Number of leaf switches
    Example: --set topology.params.leaf_count=8

  topology.params.spine_count=N
    Number of spine switches
    Example: --set topology.params.spine_count=4

  topology.params.fabric.servers_per_leaf=N
    Number of servers per leaf switch
    Example: --set topology.params.fabric.servers_per_leaf=8

  topology.params.fabric.host_links_per_server=N
    Parallel NIC connections per server
    Example: --set topology.params.fabric.host_links_per_server=2

  topology.params.fabric.parallel_leaf_to_spine_links=N
    Parallel links between each leaf-spine pair
    Example: --set topology.params.fabric.parallel_leaf_to_spine_links=4

  topology.params.fabric.link_failure_percent=N
    Percentage of links to fail (0-100)
    Example: --set topology.params.fabric.link_failure_percent=10

Visualization Parameters:

  --spacing FLOAT
    Node spacing factor (default: 2.0)
    Higher = more spread out
    Example: --spacing 3.5
"""


# ============================================================================
# AVAILABLE PRESETS
# ============================================================================

PRESETS = """
Available Presets:
  - ai/su-dp-tiny         : Tiny (minimal nodes)
  - ai/su-dp-low-small    : Small (4 leaf, 4 spine, 16 hosts)
  - ai/dp-low-small       : Alternative small topology

Run: python -m apps.sim list presets
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
   → Check that preset/config is valid
   → Verify topology configuration

❌ Visualization too crowded
   → Increase --spacing parameter
   → Reduce topology size via overrides

❌ Matplotlib not found
   → pip install matplotlib networkx
   → Set MPLBACKEND=Agg

❌ "Unknown preset"
   → Run: python -m apps.sim list presets
   → Use correct preset name
"""


if __name__ == "__main__":
    print(__doc__)
    print("\n" + "="*70)
    print("PARAMETERS")
    print("="*70)
    print(PARAMETERS)
    print("\n" + "="*70)
    print("AVAILABLE PRESETS")
    print("="*70)
    print(PRESETS)
    print("\n" + "="*70)
    print("OUTPUT")
    print("="*70)
    print(OUTPUT_INFO)
    print("\n" + "="*70)
    print("TROUBLESHOOTING")
    print("="*70)
    print(TROUBLESHOOTING)
