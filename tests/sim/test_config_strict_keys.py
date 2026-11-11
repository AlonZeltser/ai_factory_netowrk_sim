from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sim.config.loader import load_experiment_spec, load_sweep_spec, resolve_cli_path
from sim.config.models import ConfigError
from sim.runners.experiment_runner import validate_experiment

_REPO_ROOT = Path(__file__).resolve().parents[2]
DP_SMALL = "repo:tests/fixtures/dp_small.yaml"

# Every experiment the repo ships (base fragments are only building blocks).
REPO_CONFIGS = sorted(
    str(path.relative_to(_REPO_ROOT).as_posix())
    for path in [
        *(_REPO_ROOT / "experiments").glob("*.yaml"),
        _REPO_ROOT / "experiments" / "research_configurations" / "main_sweep.yaml",
        _REPO_ROOT / "experiments" / "research_configurations" / "single_run.yaml",
        *(_REPO_ROOT / "tests" / "fixtures").glob("*.yaml"),
    ]
)


@pytest.mark.parametrize("config_path", REPO_CONFIGS)
def test_every_repo_config_passes_the_key_checks(config_path: str) -> None:
    spec = load_experiment_spec(config_path=config_path, overrides=[])
    validate_experiment(spec)
    load_sweep_spec(config_path)


@pytest.mark.parametrize(
    ("override", "section"),
    [
        ("typo_top_level=1", "'/'"),
        ("vizualize=true", "'/'"),
        ("routing.mod=ecmp", "'routing'"),
        ("topology.leaf_cout=2", "'topology'"),
        ("stall_regime.packet_stall_pct=1.0", "'stall_regime'"),
        ("ai_workload.num_bucket=2", "'ai_workload'"),
    ],
)
def test_unknown_key_in_a_config_section_is_rejected_on_load(override: str, section: str) -> None:
    with pytest.raises(ConfigError, match=f"Unknown key.*in {section}"):
        load_experiment_spec(config_path=DP_SMALL, overrides=[override])


def test_unknown_sweep_vary_key_fails_instead_of_being_ignored(write_sweep_config) -> None:
    cfg = write_sweep_config({"ai_workload.num_bucket": [1, 2]}, drop=())
    sweep = load_sweep_spec(cfg)
    key, values = sweep.vary[0]

    with pytest.raises(ConfigError, match="num_bucket"):
        load_experiment_spec(config_path=cfg, overrides=[f"{key}={values[0]}"])


def _write_dp_small_without(tmp_path: Path, *key_path: str) -> str:
    """Write dp_small fully resolved (no extends) with one key removed."""
    from sim.config.loader import _load_yaml_with_extends

    data = _load_yaml_with_extends(resolve_cli_path(DP_SMALL), seen=())
    cursor = data
    for key in key_path[:-1]:
        cursor = cursor[key]
    del cursor[key_path[-1]]
    cfg = tmp_path / "without.yaml"
    cfg.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(cfg)


@pytest.mark.parametrize(
    ("key_path", "message"),
    [
        (("name",), "'name'"),
        (("seed",), "'seed'"),
        (("log_dir",), "'log_dir'"),
        (("topology",), "section 'topology'"),
        (("topology", "leaf_count"), "'topology.leaf_count'"),
        (("routing",), "section 'routing'"),
        (("routing", "mtu"), "'routing.mtu'"),
        (("routing", "ecmp_flowlet_n_packets"), "'routing.ecmp_flowlet_n_packets'"),
        (("stall_regime",), "section 'stall_regime'"),
        (("stall_regime", "packet_stall_percent"), "'stall_regime.packet_stall_percent'"),
        (("ai_workload",), "section 'ai_workload'"),
        (("ai_workload", "steps"), "'ai_workload.steps'"),
    ],
)
def test_required_key_missing_is_rejected(tmp_path: Path, key_path: tuple[str, ...], message: str) -> None:
    cfg = _write_dp_small_without(tmp_path, *key_path)

    with pytest.raises(ConfigError, match=message):
        load_experiment_spec(config_path=cfg, overrides=[])


@pytest.mark.parametrize(
    "override",
    [
        # Removed sections and keys must fail loudly, not be ignored.
        "kind=experiment",
        "meta.name=x",
        "run.seed=1",
        "workload.steps=1",
        "topology.family=clos",
        "topology.params.leaf_count=2",
        "ai_workload.kind=dp-heavy",
        "debug=true",
        "routing.flowlet_packets=8",
        "topology.name=clos",
        "topology.bandwidth_profile=400g",
        "ai_workload.name=dp-heavy",
    ],
)
def test_removed_config_keys_are_rejected(override: str) -> None:
    with pytest.raises(ConfigError, match="Unknown key"):
        load_experiment_spec(config_path=DP_SMALL, overrides=[override])


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (["name=' '"], "'name' must not be empty"),
        (["name="], "'name' must be a string"),
        (["seed=abc"], "'seed' must be an integer or null"),
        (["topology.leaf_count=abc"], "'topology.leaf_count' must be int"),
        (["topology.layers=3"], "only topology.layers=2"),
        (["topology.spine_count=0"], "topology.spine_count must be >= 1"),
    ],
)
def test_invalid_required_values_are_rejected(overrides: list[str], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_experiment_spec(config_path=DP_SMALL, overrides=overrides)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (["routing.mode=hash"], "Unsupported routing.mode"),
        (["routing.mode=adapt"], "Unsupported routing.mode"),
        (["routing.mode=flowlet", "routing.ecmp_flowlet_n_packets=0"], "requires routing.ecmp_flowlet_n_packets > 0"),
        (["routing.ecmp_flowlet_n_packets=-1"], "must be >= 0"),
    ],
)
def test_routing_values_are_checked_instead_of_silently_adjusted(overrides: list[str], message: str) -> None:
    spec = load_experiment_spec(config_path=DP_SMALL, overrides=overrides)

    with pytest.raises(ConfigError, match=message):
        validate_experiment(spec)


def test_seed_null_and_int_are_both_accepted() -> None:
    assert load_experiment_spec(config_path=DP_SMALL, overrides=[]).run.seed is None
    assert load_experiment_spec(config_path=DP_SMALL, overrides=["seed=7"]).run.seed == 7
