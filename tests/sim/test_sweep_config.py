from __future__ import annotations

from pathlib import Path

import pytest

import apps.sim as sim_app
from sim.config.loader import load_experiment_spec, load_sweep_spec
from sim.config.models import ConfigError
from sim.runners.batch_runner import collect_batch_inputs
from sim.runners.sweep_runner import SweepConfigError, build_sweep_inputs

_REPO_ROOT = Path(__file__).resolve().parents[2]
DP_SMALL = "tests/fixtures/dp_small.yaml"
DP_SMALL_SWEEP = "tests/fixtures/dp_small_sweep.yaml"


def _write_sweep_config(tmp_path: Path, sweep_yaml: str) -> str:
    base = (_REPO_ROOT / DP_SMALL).as_posix()
    cfg = tmp_path / "exp.yaml"
    cfg.write_text(f"extends: {base}\n{sweep_yaml}", encoding="utf-8")
    return str(cfg)


def test_sweep_section_is_parsed_in_file_order() -> None:
    sweep = load_sweep_spec(DP_SMALL_SWEEP)

    assert sweep.vary == (
        ("routing.mode", ("ecmp", "adaptive")),
        ("workload.params.chunk_redundancy_extra_packets", (0, 1)),
    )
    assert sweep.combination_count() == 4


def test_config_without_sweep_section_has_empty_plan() -> None:
    sweep = load_sweep_spec(DP_SMALL)

    assert sweep.vary == ()
    assert sweep.combination_count() == 0


def test_single_run_ignores_sweep_section() -> None:
    spec = load_experiment_spec(config_path=DP_SMALL_SWEEP)

    # Base values from the extended files, not the sweep values.
    assert spec.routing.mode == "adaptive"
    assert spec.workload.params["chunk_redundancy_extra_packets"] == 0


def test_build_sweep_inputs_uses_file_dimensions() -> None:
    inputs = build_sweep_inputs(config_path=DP_SMALL_SWEEP)

    assert [item.overrides for item in inputs] == [
        ("routing.mode=ecmp", "workload.params.chunk_redundancy_extra_packets=0"),
        ("routing.mode=ecmp", "workload.params.chunk_redundancy_extra_packets=1"),
        ("routing.mode=adaptive", "workload.params.chunk_redundancy_extra_packets=0"),
        ("routing.mode=adaptive", "workload.params.chunk_redundancy_extra_packets=1"),
    ]


def test_cli_vary_replaces_same_key_and_appends_new_key() -> None:
    inputs = build_sweep_inputs(
        config_path=DP_SMALL_SWEEP,
        vary_specs=["routing.mode=flowlet", "topology.params.leaf_count=4,8"],
    )

    assert [item.overrides for item in inputs] == [
        ("routing.mode=flowlet", "workload.params.chunk_redundancy_extra_packets=0", "topology.params.leaf_count=4"),
        ("routing.mode=flowlet", "workload.params.chunk_redundancy_extra_packets=0", "topology.params.leaf_count=8"),
        ("routing.mode=flowlet", "workload.params.chunk_redundancy_extra_packets=1", "topology.params.leaf_count=4"),
        ("routing.mode=flowlet", "workload.params.chunk_redundancy_extra_packets=1", "topology.params.leaf_count=8"),
    ]


def test_sweep_values_apply_with_their_yaml_types(tmp_path: Path) -> None:
    cfg = _write_sweep_config(
        tmp_path,
        "sweep:\n  vary:\n    topology.params.fabric.packet_stall_retransmit_priority: [true, false]\n"
        "    topology.params.fabric.packet_stall_percent: [0.5]\n",
    )
    first = build_sweep_inputs(config_path=cfg)[0]

    spec = load_experiment_spec(config_path=cfg, overrides=list(first.overrides))
    fabric = spec.topology.params["fabric"]
    assert fabric["packet_stall_retransmit_priority"] is True
    assert fabric["packet_stall_percent"] == 0.5


def test_sweep_without_any_dimension_is_an_error() -> None:
    with pytest.raises(SweepConfigError, match="sweep.vary"):
        build_sweep_inputs(config_path=DP_SMALL)


@pytest.mark.parametrize(
    ("sweep_yaml", "message"),
    [
        ("sweep:\n  varry:\n    routing.mode: [ecmp]\n", "Unknown key"),
        ("sweep:\n  vary:\n    routing.mode: []\n", "non-empty list"),
        ("sweep:\n  vary:\n    routing.mode: ecmp\n", "non-empty list"),
        ("sweep:\n  vary:\n    routing.mode: [[ecmp]]\n", "plain scalars"),
    ],
)
def test_invalid_sweep_section_is_rejected(tmp_path: Path, sweep_yaml: str, message: str) -> None:
    cfg = _write_sweep_config(tmp_path, sweep_yaml)

    with pytest.raises(ConfigError, match=message):
        load_sweep_spec(cfg)


def test_sweep_cli_uses_output_settings_from_config(monkeypatch, tmp_path: Path) -> None:
    summary_path = tmp_path / "out" / "summary.yaml"
    cfg = _write_sweep_config(
        tmp_path,
        "sweep:\n  vary:\n    routing.mode: [ecmp, adaptive]\n"
        f"  summary_out: {summary_path.as_posix()}\n"
        "  visualize_summary: true\n",
    )
    calls: dict[str, object] = {}

    def _fake_run_sweep(**kwargs):
        calls["run_sweep"] = kwargs
        return [{"label": "ok", "ok": True}]

    def _fake_compare(summary, *, out_dir, show):
        calls["compare_out_dir"] = out_dir
        return []

    monkeypatch.setattr(sim_app, "run_sweep", _fake_run_sweep)
    monkeypatch.setattr(sim_app, "visualize_sweep_time_comparison", _fake_compare)

    exit_code = sim_app.main(["sweep", "--config", cfg])

    assert exit_code == 0
    assert summary_path.exists()
    assert calls["compare_out_dir"] == str(summary_path.parent)


def test_sweep_cli_summary_out_flag_overrides_config(monkeypatch, tmp_path: Path) -> None:
    file_summary = tmp_path / "from_file.yaml"
    cli_summary = tmp_path / "from_cli.yaml"
    cfg = _write_sweep_config(
        tmp_path,
        f"sweep:\n  vary:\n    routing.mode: [ecmp]\n  summary_out: {file_summary.as_posix()}\n",
    )
    monkeypatch.setattr(sim_app, "run_sweep", lambda **_: [{"label": "ok", "ok": True}])

    exit_code = sim_app.main(["sweep", "--config", cfg, "--summary-out", str(cli_summary)])

    assert exit_code == 0
    assert cli_summary.exists()
    assert not file_summary.exists()


def test_batch_directory_skips_base_fragments(tmp_path: Path) -> None:
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "fragment.yaml").write_text("run: {}\n", encoding="utf-8")
    (tmp_path / "exp_a.yaml").write_text("kind: experiment\n", encoding="utf-8")

    inputs = collect_batch_inputs(directory=str(tmp_path))

    assert [Path(item.config_path).name for item in inputs] == ["exp_a.yaml"]
