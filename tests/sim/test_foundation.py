from __future__ import annotations

from pathlib import Path

import pytest

from sim.config.models import ConfigError
from sim.config.loader import load_experiment_spec
from sim.runners.experiment_runner import run_experiment, validate_experiment


def test_load_ai_preset_with_overrides() -> None:
    spec = load_experiment_spec(
        preset_name="ai/su-dp-light",
        overrides=[
            "routing.mode=adaptive",
            "topology.params.leaf_count=12",
            "topology.params.fabric.packet_stall_percent=3",
            "topology.params.fabric.packet_stall_delay_ms=50",
        ],
    )

    assert spec.topology.name == "clos"
    assert spec.routing.mode == "adaptive"
    assert spec.topology.params["leaf_count"] == 12
    assert spec.topology.params["fabric"]["packet_stall_percent"] == 3
    assert spec.topology.params["fabric"]["packet_stall_delay_ms"] == 50
    assert spec.source_preset == "ai/su-dp-light"


def test_load_unified_ai_yaml_as_experiment_spec() -> None:
    spec = load_experiment_spec(
        config_path="sim/presets/ai/dp_light.yaml"
    )

    assert spec.topology.name == "clos"
    assert spec.topology.profile == ""
    assert spec.workload.name == "dp-heavy"
    assert spec.workload.profile == ""
    assert spec.routing.mode == "adaptive"
    assert spec.topology.params["leaf_count"] == 8
    assert spec.topology.params["fabric"]["bandwidth_profile"] == "400g"
    assert spec.source_config_path.endswith("sim\\presets\\ai\\dp_light.yaml")


def test_validate_and_run_dp_light() -> None:
    spec = load_experiment_spec(preset_name="ai/su-dp-light")

    summary = validate_experiment(spec)
    assert summary["topology"] == "clos"
    assert summary["workload"] == "dp-heavy"
    assert summary["source_preset"] == "ai/su-dp-light"

    results = run_experiment(spec)
    stats = results["run statistics"]
    assert stats["total packets count"] > 0
    assert stats["delivered packets count"] > 0
    assert stats["dropped packets count"] == 0


def test_load_ai_preset_with_inheritance_and_profiles() -> None:
    spec = load_experiment_spec(preset_name="ai/su-mixed-mid")

    assert spec.topology.name == "clos"
    assert spec.topology.profile == ""
    assert spec.workload.name == "mixed"
    assert spec.workload.profile == ""
    assert spec.topology.params["leaf_count"] == 8


def test_load_config_supports_chained_extends_for_topology_defaults(tmp_path: Path) -> None:
    base = tmp_path / "a.yaml"
    mid = tmp_path / "b.yaml"
    leaf = tmp_path / "c.yaml"
    topology_defaults = Path("sim/presets/ai/topology-clos-large-scale-unit.yaml").resolve()

    base.write_text(
        f"""
extends: {topology_defaults}
kind: experiment
run:
  visualize: false
routing:
  mode: ecmp
  ecmp_flowlet_n_packets: 0
workload:
  kind: none
  params: {{}}
""".strip(),
        encoding="utf-8",
    )
    mid.write_text(
        f"""
extends: {base.name}
topology:
  params:
    leaf_count: 12
    fabric:
      bandwidth_profile: 400g
""".strip(),
        encoding="utf-8",
    )
    leaf.write_text(
        f"""
extends: {mid.name}
meta:
  name: chained-topology
topology:
  params:
    spine_count: 6
workload:
  kind: none
  params: {{}}
""".strip(),
        encoding="utf-8",
    )

    spec = load_experiment_spec(config_path=str(leaf))

    assert spec.topology.name == "clos"
    assert spec.topology.params["leaf_count"] == 12
    assert spec.topology.params["spine_count"] == 6
    assert spec.topology.params["fabric"]["host_links_per_server"] == 8
    assert spec.topology.params["fabric"]["bandwidth_profile"] == "400g"


def test_validate_requires_topology_defaults_from_yaml_chain(tmp_path: Path) -> None:
    cfg = tmp_path / "missing_topology_defaults.yaml"
    cfg.write_text(
        """
kind: experiment
run:
  visualize: false
topology:
  params:
routing:
  mode: ecmp
  ecmp_flowlet_n_packets: 0
workload:
  kind: none
  params: {}
""".strip(),
        encoding="utf-8",
    )

    spec = load_experiment_spec(config_path=str(cfg))

    with pytest.raises(ConfigError, match="Missing required key 'topology.params.layers'"):
        validate_experiment(spec)


def test_validate_clos_override() -> None:
    spec = load_experiment_spec(
        preset_name="ai/su-dp-low",
        overrides=["topology.params.leaf_count=10", "topology.params.fabric.bandwidth_profile=400g"],
    )

    summary = validate_experiment(spec)
    assert summary["topology"] == "clos"
    assert summary["workload"] == "dp-heavy"
    assert summary["source_preset"] == "ai/su-dp-low"


def test_run_collect_packet_timeline_implies_store_packets() -> None:
    spec = load_experiment_spec(
        preset_name="ai/dp-low",
        overrides=["run.collect_packet_timeline=true"],
    )

    assert spec.run.collect_packet_timeline is True
    assert spec.run.store_packets is True


def test_run_deep_flow_chain_log_flag_is_parsed() -> None:
    spec = load_experiment_spec(
        preset_name="ai/dp-low",
        overrides=["run.deep_flow_chain_log=true"],
    )

    assert spec.run.deep_flow_chain_log is True





