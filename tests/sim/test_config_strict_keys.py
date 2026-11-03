from __future__ import annotations

from pathlib import Path

import pytest

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


def test_unknown_sweep_vary_key_fails_instead_of_being_ignored(tmp_path: Path) -> None:
    cfg = tmp_path / "exp.yaml"
    cfg.write_text(
        f"extends: {(_REPO_ROOT / DP_SMALL).as_posix()}\n"
        "sweep:\n  vary:\n    workload.params.num_bucket: [1, 2]\n",
        encoding="utf-8",
    )
    sweep = load_sweep_spec(str(cfg))
    key, values = sweep.vary[0]
    spec = load_experiment_spec(config_path=str(cfg), overrides=[f"{key}={values[0]}"])

    with pytest.raises(ConfigError, match="num_bucket"):
        validate_experiment(spec)
