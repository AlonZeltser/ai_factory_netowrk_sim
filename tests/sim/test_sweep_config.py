from __future__ import annotations

from pathlib import Path

import pytest

import apps.sim as sim_app
from sim.config.loader import load_experiment_spec, load_sweep_spec
from sim.config.models import ConfigError
from sim.runners.sweep_runner import build_sweep_inputs

_REPO_ROOT = Path(__file__).resolve().parents[2]
DP_SMALL = "repo:tests/fixtures/dp_small.yaml"
DP_SMALL_SWEEP = "repo:tests/fixtures/dp_small_sweep.yaml"

_SWEEP_SETTING_KEYS = (
    "vary",
    "summary_out",
    "visualize_summary",
    "plot_ring_heatmaps",
    "lower_zoom_percent",
    "stop_on_error",
    "processes",
    "plot_topology_once",
    "show_visualization_window",
)


def test_sweep_section_is_parsed_in_file_order() -> None:
    sweep = load_sweep_spec(DP_SMALL_SWEEP)

    assert sweep.vary == (
        ("routing.mode", ("ecmp", "adaptive")),
        ("workload.params.flow_redundancy_extra_packets", (0, 1)),
    )
    assert sweep.combination_count() == 4
    assert Path(sweep.summary_out) == _REPO_ROOT / "results" / "test-dp-small-sweep" / "summary.yaml"
    assert sweep.lower_zoom_percent == 15.0
    assert sweep.max_processes is None  # processes: auto
    assert not any(
        (sweep.visualize_summary, sweep.plot_ring_heatmaps, sweep.stop_on_error, sweep.plot_topology_once, sweep.show_visualization_window)
    )


def test_config_without_sweep_section_has_no_plan() -> None:
    assert load_sweep_spec(DP_SMALL) is None


def test_single_run_ignores_sweep_section() -> None:
    spec = load_experiment_spec(config_path=DP_SMALL_SWEEP, overrides=[])

    # Base values from the extended files, not the sweep values.
    assert spec.routing.mode == "adaptive"
    assert spec.workload.params["flow_redundancy_extra_packets"] == 0


def test_build_sweep_inputs_uses_file_dimensions() -> None:
    inputs = build_sweep_inputs(config_path=DP_SMALL_SWEEP, sweep=load_sweep_spec(DP_SMALL_SWEEP))

    assert [item.overrides for item in inputs] == [
        ("routing.mode=ecmp", "workload.params.flow_redundancy_extra_packets=0"),
        ("routing.mode=ecmp", "workload.params.flow_redundancy_extra_packets=1"),
        ("routing.mode=adaptive", "workload.params.flow_redundancy_extra_packets=0"),
        ("routing.mode=adaptive", "workload.params.flow_redundancy_extra_packets=1"),
    ]
    assert inputs[0].label == f"{DP_SMALL_SWEEP} | routing.mode=ecmp | workload.params.flow_redundancy_extra_packets=0"


def test_sweep_values_apply_with_their_yaml_types(write_sweep_config) -> None:
    cfg = write_sweep_config(
        {
            "topology.params.fabric.packet_stall_retransmit_priority": [True, False],
            "topology.params.fabric.packet_stall_percent": [0.5],
        },
        drop=(),
    )
    first = build_sweep_inputs(config_path=cfg, sweep=load_sweep_spec(cfg))[0]

    spec = load_experiment_spec(config_path=cfg, overrides=list(first.overrides))
    fabric = spec.topology.params["fabric"]
    assert fabric["packet_stall_retransmit_priority"] is True
    assert fabric["packet_stall_percent"] == 0.5


@pytest.mark.parametrize("key", _SWEEP_SETTING_KEYS)
def test_sweep_setting_missing_is_rejected(write_sweep_config, key: str) -> None:
    cfg = write_sweep_config({"routing.mode": ["ecmp"]}, drop=(key,))

    with pytest.raises(ConfigError, match=f"Missing required key 'sweep.{key}'"):
        load_sweep_spec(cfg)


@pytest.mark.parametrize(
    ("vary", "settings", "message"),
    [
        ({"routing.mode": ["ecmp"]}, {"varry": {"routing.mode": ["ecmp"]}}, "Unknown key"),
        ({}, {}, "at least one key"),
        ({"routing.mode": []}, {}, "non-empty list"),
        ({"routing.mode": "ecmp"}, {}, "non-empty list"),
        ({"routing.mode": [["ecmp"]]}, {}, "plain scalars"),
        ({"routing.mode": ["ecmp"]}, {"summary_out": ""}, "'sweep.summary_out' must not be empty"),
        ({"routing.mode": ["ecmp"]}, {"processes": 0}, "'sweep.processes' must be an integer >= 1 or 'auto'"),
        ({"routing.mode": ["ecmp"]}, {"processes": "many"}, "'sweep.processes' must be an integer >= 1 or 'auto'"),
        ({"routing.mode": ["ecmp"]}, {"processes": True}, "'sweep.processes' must be an integer >= 1 or 'auto'"),
        ({"routing.mode": ["ecmp"]}, {"lower_zoom_percent": "x"}, "'sweep.lower_zoom_percent' must be a number"),
        ({"routing.mode": ["ecmp"]}, {"lower_zoom_percent": 150}, "between 0 and 100"),
    ],
)
def test_invalid_sweep_section_is_rejected(write_sweep_config, vary, settings, message: str) -> None:
    cfg = write_sweep_config(vary, **settings, drop=())

    with pytest.raises(ConfigError, match=message):
        load_sweep_spec(cfg)


def test_sweep_cli_uses_output_settings_from_config(monkeypatch, write_sweep_config) -> None:
    cfg = write_sweep_config(
        {"routing.mode": ["ecmp", "adaptive"]},
        visualize_summary=True,
        lower_zoom_percent=25.0,
        show_visualization_window=True,
        drop=(),
    )
    summary_path = Path(load_sweep_spec(cfg).summary_out)
    calls: dict[str, object] = {}

    def _fake_run_sweep(**kwargs):
        calls["run_sweep"] = kwargs
        return [{"label": "ok", "ok": True}]

    def _fake_compare(summary, *, out_dir, show, training_step_time_lower_zoom_percent):
        calls["compare"] = (out_dir, show, training_step_time_lower_zoom_percent)
        return []

    monkeypatch.setattr(sim_app, "run_sweep", _fake_run_sweep)
    monkeypatch.setattr(sim_app, "visualize_sweep_time_comparison", _fake_compare)

    exit_code = sim_app.main(["sweep", "--config", cfg])

    assert exit_code == 0
    assert summary_path.exists()
    assert calls["compare"] == (str(summary_path.parent), True, 25.0)


@pytest.mark.parametrize(
    "removed_flag",
    [
        ["--vary", "routing.mode=ecmp"],
        ["--summary-out", "x.yaml"],
        ["--visualize-summary"],
        ["--plot-ring-heatmaps"],
        ["--plot-topology-once"],
        ["--show-visualization-window"],
        ["--stop-on-error"],
        ["--processes", "2"],
        ["--set", "routing.mode=ecmp"],
        ["--store-packets"],
        ["--collect-packet-timeline"],
    ],
)
def test_sweep_cli_has_no_flags_besides_config(removed_flag: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        sim_app.main(["sweep", "--config", DP_SMALL_SWEEP, *removed_flag])

    assert exc.value.code == 2


def test_sweep_cli_without_sweep_section_fails(capsys) -> None:
    assert sim_app.main(["sweep", "--config", DP_SMALL]) == 2
    assert "has no 'sweep' section" in capsys.readouterr().err


def test_plot_summary_reads_plot_settings_from_config(monkeypatch, tmp_path: Path, write_sweep_config) -> None:
    cfg = write_sweep_config({"routing.mode": ["ecmp"]}, lower_zoom_percent=30.0, drop=())
    calls: dict[str, object] = {}

    def _fake_from_yaml(summary_yaml_path, *, out_dir, show, training_step_time_lower_zoom_percent, include_training_step_traffic_matrices):
        calls["from_yaml"] = (out_dir, show, training_step_time_lower_zoom_percent, include_training_step_traffic_matrices)
        return ["plot.png"]

    monkeypatch.setattr(sim_app, "visualize_sweep_time_comparison_from_yaml", _fake_from_yaml)

    exit_code = sim_app.main(
        ["plot-summary", "--summary", str(tmp_path / "summary.yaml"), "--config", cfg, "--out-dir", str(tmp_path / "plots")]
    )

    assert exit_code == 0
    assert calls["from_yaml"] == (str(tmp_path / "plots"), False, 30.0, True)


@pytest.mark.parametrize("missing", ["--config", "--out-dir"])
def test_plot_summary_requires_config_and_out_dir(tmp_path: Path, missing: str) -> None:
    args = {"--summary": str(tmp_path / "summary.yaml"), "--config": DP_SMALL_SWEEP, "--out-dir": str(tmp_path / "plots")}
    del args[missing]

    with pytest.raises(SystemExit) as exc:
        sim_app.main(["plot-summary", *[part for item in args.items() for part in item]])

    assert exc.value.code == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["run", "--config", DP_SMALL, "--set", "routing.mode=ecmp"],
        ["run", "--config", DP_SMALL, "--store-packets"],
        ["run", "--config", DP_SMALL, "--collect-packet-timeline"],
        ["validate", "--config", DP_SMALL, "--set", "routing.mode=ecmp"],
        ["batch", "--config", DP_SMALL],
    ],
)
def test_removed_cli_options_are_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        sim_app.main(argv)

    assert exc.value.code == 2
