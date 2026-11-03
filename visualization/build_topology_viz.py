#!/usr/bin/env python3
"""
Helper script to build and save a topology visualization for any experiment config.

This is useful for generating topology diagrams without running the simulator.

Usage:
    python visualization/build_topology_viz.py --config experiments/dp_single_bucket.yaml

To draw a variation, write a small YAML file that `extends` the experiment and changes it.
"""
import argparse
import shutil
import sys
from pathlib import Path

# Add repo root to path
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from sim.config.loader import load_experiment_spec
from sim.registry.topologies import build_network


def main():
    parser = argparse.ArgumentParser(
        description="Build and visualize a topology from an experiment config file"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to an experiment YAML file"
    )
    parser.add_argument(
        "--output",
        help="Explicit output file path (optional). If not specified, uses default results/ naming."
    )
    parser.add_argument(
        "--show-link-status-legend",
        action="store_true",
        help="Show healthy/failed link entries in the legend (disabled by default)"
    )

    args = parser.parse_args()

    try:
        # Load the experiment spec
        print(f"Loading configuration...")
        spec = load_experiment_spec(config_path=args.config, overrides=[])

        print(f"Building network topology...")
        network = build_network(spec)
        network.create_topology()

        print(f"Generating visualization...")
        from visualization.visualizer import visualize_topology

        saved_path = visualize_topology(
            network.name,
            network.entities,
            spacing=2.0,
            show=False,
            show_link_status_legend=args.show_link_status_legend,
        )

        if saved_path and args.output:
            output_path = Path(args.output).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(saved_path, output_path)
            saved_path = str(output_path)

        if saved_path:
            print(f"\n✓ Topology visualization saved to:")
            print(f"  {saved_path}")
            print(f"\nTopology Info:")
            print(f"  Name: {network.name}")
            print(f"  Switches: {len(network.switches)}")
            print(f"  Hosts: {len(network.hosts)}")
            print(f"  Total nodes: {len(network.entities)}")
            return 0
        else:
            print("Error: Failed to save visualization")
            return 1

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

