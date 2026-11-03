from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sim.config.loader import load_experiment_spec, load_sweep_spec
from sim.config.models import ConfigError
from sim.runners.experiment_runner import validate_experiment

_REPO_ROOT = Path(__file__).resolve().parents[2]
DP_SMALL = "tests/fixtures/dp_small.yaml"

# Every experiment the repo ships (base fragments are only building blocks).
REPO_CONFIGS = sorted(
    str(path.relative_to(_REPO_ROOT).as_posix())
    for path in [*(_REPO_ROOT / "experiments").glob("*.yaml"), *(_REPO_ROOT / "tests" / "fixtures").glob("*.yaml")]
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
        ("meta.titel=x", "'meta'"),
        ("run.vizualize=true", "'run'"),
        ("routing.mod=ecmp", "'routing'"),
        ("topology.familly=clos", "'topology'"),
        ("workload.knd=dp-heavy", "'workload'"),
    ],
)
def test_unknown_key_in_a_config_section_is_rejected_on_load(override: str, section: str) -> None:
    with pytest.raises(ConfigError, match=f"Unknown key.*in {section}"):
        load_experiment_spec(config_path=DP_SMALL, overrides=[override])


@pytest.mark.parametrize(
    ("override", "section"),
    [
        ("topology.params.leaf_cout=2", "'topology.params'"),
        ("topology.params.fabric.packet_stall_pct=1.0", "'topology.params.fabric'"),
        ("workload.params.num_bucket=2", "'workload.params'"),
    ],
)
def test_unknown_key_in_params_is_rejected_when_building(override: str, section: str) -> None:
    spec = load_experiment_spec(config_path=DP_SMALL, overrides=[override])

    with pytest.raises(ConfigError, match=f"Unknown key.*in {section}"):
        validate_experiment(spec)


def test_unknown_sweep_vary_key_fails_instead_of_being_ignored(write_sweep_config) -> None:
    cfg = write_sweep_config({"workload.params.num_bucket": [1, 2]})
    sweep = load_sweep_spec(cfg)
    key, values = sweep.vary[0]
    spec = load_experiment_spec(config_path=cfg, overrides=[f"{key}={values[0]}"])

    with pytest.raises(ConfigError, match="num_bucket"):
        validate_experiment(spec)


def _write_dp_small_without(tmp_path: Path, *key_path: str) -> str:
    """Write dp_small fully resolved (no extends) with one key removed."""
    from sim.config.loader import _load_yaml_with_extends

    data = _load_yaml_with_extends((_REPO_ROOT / DP_SMALL).resolve(), seen=())
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
        (("kind",), "'/.kind'"),
        (("meta",), "section 'meta'"),
        (("meta", "name"), "'meta.name'"),
        (("meta", "description"), "'meta.description'"),
        (("run", "seed"), "'run.seed'"),
        (("routing", "ecmp_flowlet_n_packets"), "'routing.ecmp_flowlet_n_packets'"),
        (("topology", "family"), "'topology.family'"),
        (("topology", "params"), "'topology.params'"),
        (("workload", "kind"), "'workload.kind'"),
        (("workload", "params"), "'workload.params'"),
    ],
)
def test_required_key_missing_is_rejected(tmp_path: Path, key_path: tuple[str, ...], message: str) -> None:
    cfg = _write_dp_small_without(tmp_path, *key_path)

    with pytest.raises(ConfigError, match=message):
        load_experiment_spec(config_path=cfg, overrides=[])


@pytest.mark.parametrize(
    "override",
    [
        "run.debug=true",
        "routing.flowlet_packets=8",
        "topology.name=clos",
        "topology.type=clos",
        "topology.profile=x",
        "workload.name=dp-heavy",
        "workload.profile=x",
    ],
)
def test_removed_config_aliases_are_rejected(override: str) -> None:
    with pytest.raises(ConfigError, match="Unknown key"):
        load_experiment_spec(config_path=DP_SMALL, overrides=[override])


def test_removed_bandwidth_profile_is_rejected() -> None:
    spec = load_experiment_spec(config_path=DP_SMALL, overrides=["topology.params.fabric.bandwidth_profile=400g"])

    with pytest.raises(ConfigError, match="Unknown key.*bandwidth_profile"):
        validate_experiment(spec)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (["meta.name=' '"], "'meta.name' must not be empty"),
        (["meta.name="], "'meta.name' must be a string"),
        (["run.seed=abc"], "'run.seed' must be an integer or null"),
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
    assert load_experiment_spec(config_path=DP_SMALL, overrides=["run.seed=7"]).run.seed == 7
