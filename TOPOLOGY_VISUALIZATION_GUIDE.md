# Topology Visualization Improvements

## Overview
The topology visualization has been significantly improved with:

1. **Color-blind friendly color palette** - Uses ColorBrewer safe colors
2. **Enhanced legend** - Shows node types and link status
3. **Failed link indicators** - Red dashed lines with "(FAILED)" labels
4. **Better node classification** - Automatic spine vs leaf detection
5. **Improved labeling** - Clear hierarchy visualization

## Color Scheme (Color-blind Safe)

### Node Colors
- **Leafs**: Teal/Blue (#1b9e77) - High contrast, safe for all color blindness types
- **Spines**: Orange (#d95f02) - Warm, easily distinguished
- **Hosts/Servers**: Purple (#7570b3) - High contrast, complements other colors

All colors are from ColorBrewer's colorblind-safe palettes, ensuring accessibility for:
- Deuteranopia (red-green, most common)
- Protanopia (red-green)
- Tritanopia (blue-yellow)

## Visual Elements

### Nodes
- **Size**: Hosts are smaller (300 units), Switches are larger (900 units)
- **Color**: Automatically determined by naming convention:
  - Contains `_spine` → Orange (Spine)
  - Contains `_leaf` and NOT `_srv` → Teal (Leaf)
  - Contains `_srv` → Purple (Host/Server)

### Links
- **Healthy links**: Gray solid lines (width: 1.8)
- **Failed links**: Red dashed lines (width: 6.0) with "(FAILED)" label
- **Multiplicity**: Shows "x2", "x3" etc. when multiple links exist between same nodes

### Legend
- Shows all three node types present in topology
- Shows link status color coding
- Positioned at upper-left of visualization
- Two-column layout if needed

## How to Use

### Quick Start - Using the Helper Script

Generate a topology visualization for any preset:

```bash
# Basic usage with a preset
python visualization/build_topology_viz.py --preset ai/su-dp-low-small

# With custom leaf count
python visualization/build_topology_viz.py --preset ai/su-dp-low-small --set topology.params.leaf_count=8

# With larger spacing for readability
python visualization/build_topology_viz.py --preset ai/su-dp-low-small --spacing 3.0

# Multiple overrides
python visualization/build_topology_viz.py --preset ai/su-dp-low-small \
  --set topology.params.leaf_count=8 \
  --set topology.params.spine_count=8 \
  --spacing 2.5
```

### Using a Custom Config File

```bash
python visualization/build_topology_viz.py --config my-topology.yaml --spacing 2.0
```

### Script Help
```bash
python visualization/build_topology_viz.py --help
```

## Output

The script generates:
- PNG file saved to `results/topology_<name>_<timestamp>_<version>.png`
- Console output with topology statistics:
  - Network name
  - Number of switches
  - Number of hosts
  - Total entities

Example output:
```
✓ Topology visualization saved to:
  C:\...\results\topology_ai-factory-su_20260720_094341_1.png

Topology Info:
  Name: ai-factory-su
  Switches: 8
  Hosts: 16
  Total nodes: 88
```

## Customization Options

### Spacing Parameter
Controls node spacing in the visualization. Higher values = more spread out:
- Default: 2.0
- Recommended range: 1.5 - 4.0
- Use higher values for large topologies

Example:
```bash
python visualization/build_topology_viz.py --preset ai/su-dp-low-small --spacing 3.5
```

### Configuration Overrides
Any topology parameter can be overridden using `--set`:
- `topology.params.leaf_count=N` - Number of leaf switches
- `topology.params.spine_count=N` - Number of spine switches
- `topology.params.fabric.servers_per_leaf=N` - Servers per leaf
- `topology.params.fabric.parallel_leaf_to_spine_links=N` - Parallel links

Example:
```bash
python visualization/build_topology_viz.py --preset ai/su-dp-low-small \
  --set topology.params.leaf_count=16 \
  --set topology.params.fabric.servers_per_leaf=8
```

## Integration with Simulation

The visualization is automatically generated during simulation when the `--visualize` flag is used:

```bash
python -m apps.sim run --preset ai/su-dp-low-small --visualize
```

This creates the topology visualization along with experiment result visualizations.

## Available Presets

List all available presets:
```bash
python -m apps.sim list presets
```

Some interesting presets to try:
- `ai/su-dp-tiny` - Very small (minimal nodes)
- `ai/su-dp-low-small` - Small scale unit (4 leafs, 4 spines)
- `ai/su-mixed-light` - Mixed workload on small topology

## Technical Details

### Implementation
- Location: `visualization/visualizer.py` - Main visualization logic
- Location: `visualization/build_topology_viz.py` - Helper script

### Key Functions
- `visualize_topology(name, entities, spacing, show)` - Creates and saves visualization
- Supports both new port-based Link model and legacy node reference model
- Automatically detects scale-unit naming scheme

### Dependencies
- matplotlib - Used for rendering (non-interactive 'Agg' backend)
- networkx - Used for graph layout and structure
- graphviz (optional) - For complex layout algorithms

### Color Palette References
- ColorBrewer: https://colorbrewer2.org/
- Accessible Colors: https://www.color-blindness.com/

## Examples

### Small Topology (8 nodes)
```bash
python visualization/build_topology_viz.py --preset ai/su-dp-low-small
```
- 4 Spine switches (orange)
- 4 Leaf switches (teal)
- 16 Host servers (purple)
- Shows connection structure clearly

### Large Topology with Customization
```bash
python visualization/build_topology_viz.py --preset ai/su-dp-low-small \
  --set topology.params.leaf_count=16 \
  --set topology.params.spine_count=8 \
  --spacing 3.0
```
- Larger topology with custom ratios
- Better spacing for readability

### With Link Failures
```bash
python visualization/build_topology_viz.py --preset ai/su-dp-low-small \
  --set topology.params.fabric.link_failure_percent=20
```
- Shows which links are marked as failed (red dashed)
- Useful for understanding fault scenarios

## Troubleshooting

### "No nodes to visualize"
- Ensure the preset/config is valid
- Check that topology has been properly configured

### Missing visualization file
- Check `results/` directory exists
- Verify write permissions to `results/`

### Matplotlib issues
- Ensure matplotlib and networkx are installed
- Try setting `MPLBACKEND=Agg` environment variable

### Large topology too crowded
- Increase `--spacing` parameter (e.g., 4.0 or higher)
- Reduce topology size via config overrides

## Future Enhancements

Potential improvements forsurface area:
- Hierarchical layout with clear spine/leaf/host layers
- Interactive HTML visualization with hover tooltips
- Export to other formats (SVG, PDF)
- Custom color schemes per user preference
- Node statistics annotations (bandwidth, latency)
- Traffic flow animation
