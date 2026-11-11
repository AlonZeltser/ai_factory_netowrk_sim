from __future__ import annotations

from pathlib import Path

import pytest

from sim.config.models import ConfigError
from sim.config.loader import load_experiment_spec
from sim.runners.experiment_runner import run_experiment, validate_experiment

DP_SMALL = "repo:tests/fixtures/dp_small.yaml"


def test_load_config_with_overrides() -> None:
    spec = load_experiment_spec(
        config_path=DP_SMALL,
        overrides=[
            "routing.mode=adaptive",
            "topology.leaf_count=12",
            "stall_regime.packet_stall_percent=3",
            "stall_regime.packet_stall_delay_ms=50",
        ],
    )

    assert spec.routing.mode == "adaptive"
    assert spec.topology.leaf_count == 12
    assert spec.stall_regime.packet_stall_percent == 3
    assert spec.stall_regime.packet_stall_delay_ms == 50
    assert spec.source_config_path.endswith("dp_small.yaml")




def test_validate_and_run_dp_low_small() -> None:
    spec = load_experiment_spec(config_path=DP_SMALL, overrides=[])

    summary = validate_experiment(spec)
    assert summary["name"] == "test-dp-small"
    assert summary["source_config_path"].endswith("dp_small.yaml")

    results = run_experiment(spec)
    stats = results["run statistics"]
    assert stats["total packets count"] > 0
    assert stats["delivered packets count"] > 0
    assert stats["dropped packets count"] == 0


def test_validate_requires_topology_defaults_from_yaml_chain(tmp_path: Path) -> None:
    base = (Path(__file__).resolve().parents[2] / "experiments" / "base").as_posix()
    cfg = tmp_path / "missing_topology_defaults.yaml"
    cfg.write_text(
        f"""
extends:
  - {base}/run-defaults.yaml
  - {base}/routing-default.yaml
  - {base}/stall_regime-default.yaml
  - {base}/ai_workload-default.yaml
name: missing-topology-defaults
topology: {{}}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Missing required key 'topology.layers'"):
        load_experiment_spec(config_path=str(cfg), overrides=[])


def test_validate_clos_override() -> None:
    spec = load_experiment_spec(
        config_path=DP_SMALL,
        overrides=[
            "topology.leaf_count=10",
            "topology.server_to_leaf_bandwidth_bps=400000000000",
            "topology.leaf_to_spine_bandwidth_bps=400000000000",
        ],
    )

    summary = validate_experiment(spec)
    assert summary["name"] == "test-dp-small"
    assert summary["source_config_path"].endswith("dp_small.yaml")


def test_run_collect_packet_timeline_requires_store_packets() -> None:
    with pytest.raises(ConfigError, match="requires 'store_packets: true'"):
        load_experiment_spec(config_path=DP_SMALL, overrides=["collect_packet_timeline=true"])

    spec = load_experiment_spec(
        config_path=DP_SMALL,
        overrides=["collect_packet_timeline=true", "store_packets=true"],
    )
    assert spec.run.collect_packet_timeline is True
    assert spec.run.store_packets is True


def test_run_deep_flow_chain_log_flag_is_parsed() -> None:
    spec = load_experiment_spec(
        config_path=DP_SMALL,
        overrides=["deep_flow_chain_log=true"],
    )

    assert spec.run.deep_flow_chain_log is True

