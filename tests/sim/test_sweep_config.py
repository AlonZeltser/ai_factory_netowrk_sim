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
    "paper_style",
    "gantt_pdfs",
    "gantt_chain_limit",
    "gantt_compare",
)


def test_sweep_section_is_parsed_in_file_order() -> None:
    sweep = load_sweep_spec(DP_SMALL_SWEEP)

    assert sweep.vary == (
        ("routing.mode", ("ecmp", "adaptive")),
        ("ai_workload.flow_redundancy_extra_packets", (0, 1)),
    )
    assert sweep.combination_count() == 4
    assert Path(sweep.summary_out) == _REPO_ROOT / "results" / "test-dp-small-sweep" / "summary.yaml"
    assert sweep.lower_zoom_percent == 15.0
    assert sweep.max_processes is None  # processes: auto
    assert not any(
        (sweep.visualize_summary, sweep.plot_ring_heatmaps, sweep.stop_on_error, sweep.plot_topology_once, sweep.show_visualization_window,
         sweep.paper_style)
    )


def test_config_without_sweep_section_has_no_plan() -> None:
    assert load_sweep_spec(DP_SMALL) is None


def test_single_run_ignores_sweep_section() -> None:
    spec = load_experiment_spec(config_path=DP_SMALL_SWEEP, overrides=[])

    # Base values from the extended files, not the sweep values.
    assert spec.routing.mode == "adaptive"
    assert spec.ai_workload.flow_redundancy_extra_packets == 0


def test_build_sweep_inputs_uses_file_dimensions() -> None:
    inputs = build_sweep_inputs(config_path=DP_SMALL_SWEEP, sweep=load_sweep_spec(DP_SMALL_SWEEP))

    assert [item.overrides for item in inputs] == [
        ("routing.mode=ecmp", "ai_workload.flow_redundancy_extra_packets=0"),
        ("routing.mode=ecmp", "ai_workload.flow_redundancy_extra_packets=1"),
        ("routing.mode=adaptive", "ai_workload.flow_redundancy_extra_packets=0"),
        ("routing.mode=adaptive", "ai_workload.flow_redundancy_extra_packets=1"),
    ]
    assert inputs[0].label == f"{DP_SMALL_SWEEP} | routing.mode=ecmp | ai_workload.flow_redundancy_extra_packets=0"


def test_sweep_values_apply_with_their_yaml_types(write_sweep_config) -> None:
    cfg = write_sweep_config(
        {
            "stall_regime.packet_stall_retransmit_priority": [True, False],
            "stall_regime.packet_stall_percent": [0.5],
        },
        drop=(),
    )
    first = build_sweep_inputs(config_path=cfg, sweep=load_sweep_spec(cfg))[0]

    spec = load_experiment_spec(config_path=cfg, overrides=list(first.overrides))
    assert spec.stall_regime.packet_stall_retransmit_priority is True
    assert spec.stall_regime.packet_stall_percent == 0.5


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
        # A key the standard plots group by, so they are drawn (a routing.mode sweep would skip them).
        {"ai_workload.flow_redundancy_extra_packets": [0, 1]},
        visualize_summary=True,
        lower_zoom_percent=25.0,
        show_visualization_window=True,
        paper_style=True,
        drop=(),
    )
    summary_path = Path(load_sweep_spec(cfg).summary_out)
    calls: dict[str, object] = {}

    def _fake_run_sweep(**kwargs):
        calls["run_sweep"] = kwargs
        return [{"label": "ok", "ok": True}]

    def _fake_compare(summary, *, out_dir, show, training_step_time_lower_zoom_percent, paper_style):
        calls["compare"] = (out_dir, show, training_step_time_lower_zoom_percent, paper_style)
        return []

    monkeypatch.setattr(sim_app, "run_sweep", _fake_run_sweep)
    monkeypatch.setattr(sim_app, "visualize_sweep_time_comparison", _fake_compare)

    exit_code = sim_app.main(["sweep", "--config", cfg])

    assert exit_code == 0
    assert summary_path.exists()
    assert calls["compare"] == (str(summary_path.parent), True, 25.0, True)


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

    def _fake_from_yaml(
        summary_yaml_path, *, out_dir, show, training_step_time_lower_zoom_percent, include_training_step_traffic_matrices,
        paper_style,
    ):
        calls["from_yaml"] = (out_dir, show, training_step_time_lower_zoom_percent, include_training_step_traffic_matrices, paper_style)
        return ["plot.png"]

    monkeypatch.setattr(sim_app, "visualize_sweep_time_comparison_from_yaml", _fake_from_yaml)

    exit_code = sim_app.main(
        ["plot-summary", "--summary", str(tmp_path / "summary.yaml"), "--config", cfg, "--out-dir", str(tmp_path / "plots")]
    )

    assert exit_code == 0
    assert calls["from_yaml"] == (str(tmp_path / "plots"), False, 30.0, True, False)


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


_STALL = "stall_regime.packet_stall_percent"
_REDUNDANCY = "ai_workload.flow_redundancy_extra_packets"
_DELAY = "stall_regime.packet_stall_delay_ms"


def test_plot_layout_defaults_follow_vary_order(write_sweep_config) -> None:
    one = load_sweep_spec(write_sweep_config({_STALL: [0, 1]}, drop=()))
    two = load_sweep_spec(write_sweep_config({_STALL: [0, 1], _REDUNDANCY: [0, 2]}, drop=()))
    three = load_sweep_spec(write_sweep_config({_STALL: [0, 1], _REDUNDANCY: [0, 2], _DELAY: [2, 8]}, drop=()))

    assert one.plot_layout is None
    assert (two.plot_layout.split, two.plot_layout.x, two.plot_layout.lines) == (None, _STALL, _REDUNDANCY)
    assert (three.plot_layout.split, three.plot_layout.x, three.plot_layout.lines) == (_STALL, _REDUNDANCY, _DELAY)


def test_plot_layout_can_be_set_explicitly(write_sweep_config) -> None:
    cfg = write_sweep_config(
        {_STALL: [0, 1], _REDUNDANCY: [0, 2], _DELAY: [2, 8]},
        plot_layout={"split": _DELAY, "x": _STALL, "lines": _REDUNDANCY},
        drop=(),
    )

    layout = load_sweep_spec(cfg).plot_layout

    assert (layout.split, layout.x, layout.lines) == (_DELAY, _STALL, _REDUNDANCY)


@pytest.mark.parametrize(
    ("plot_layout", "message"),
    [
        ({"x": _STALL}, "Missing required key 'sweep.plot_layout.lines'"),
        ({"x": _STALL, "lines": "routing.mode"}, "'sweep.plot_layout.lines' must be one of the 'sweep.vary' keys"),
        ({"x": _STALL, "lines": _STALL}, "each role a different vary key"),
        ({"x": _STALL, "lines": _REDUNDANCY, "panel": _STALL}, "Unknown key"),
        ({"x": _STALL, "lines": _REDUNDANCY, "split": None}, None),
    ],
)
def test_plot_layout_is_validated(write_sweep_config, plot_layout, message) -> None:
    cfg = write_sweep_config({_STALL: [0, 1], _REDUNDANCY: [0, 2]}, plot_layout=plot_layout, drop=())

    if message is None:
        assert load_sweep_spec(cfg).plot_layout.split is None
        return
    with pytest.raises(ConfigError, match=message):
        load_sweep_spec(cfg)


def test_plot_layout_must_give_every_vary_key_a_role(write_sweep_config) -> None:
    cfg = write_sweep_config(
        {_STALL: [0, 1], _REDUNDANCY: [0, 2], _DELAY: [2, 8]},
        plot_layout={"x": _STALL, "lines": _REDUNDANCY},
        drop=(),
    )

    with pytest.raises(ConfigError, match=f"no role for {_DELAY}"):
        load_sweep_spec(cfg)


@pytest.mark.parametrize(
    ("config", "summary_dir", "layout", "runs"),
    [
        ("message_size_sweep.yaml", "message-size-sweep", (None, _STALL, _REDUNDANCY), 54),
        ("stall_delay_sweep.yaml", "stall-delay-sweep", (_DELAY, _STALL, _REDUNDANCY), 144),
    ],
)
def test_research_side_sweeps_have_their_own_output_and_layout(config, summary_dir, layout, runs) -> None:
    path = f"repo:experiments/research_configurations/{config}"
    sweep = load_sweep_spec(path)
    main = load_sweep_spec("repo:experiments/research_configurations/main_sweep.yaml")

    assert Path(sweep.summary_out).parent == _REPO_ROOT / "results" / summary_dir
    assert Path(sweep.summary_out).parent != Path(main.summary_out).parent
    assert (sweep.plot_layout.split, sweep.plot_layout.x, sweep.plot_layout.lines) == layout
    assert sweep.combination_count() == runs
    # Every other sweep setting is main_sweep's, except the worker count, which depends on the machine.
    for field in ("visualize_summary", "plot_ring_heatmaps", "lower_zoom_percent", "stop_on_error",
                  "plot_topology_once", "show_visualization_window", "paper_style", "gantt_pdfs", "gantt_chain_limit",
                  "gantt_compare"):
        assert getattr(sweep, field) == getattr(main, field), field


def test_main_sweep_layout_matches_its_other_plots() -> None:
    layout = load_sweep_spec("repo:experiments/research_configurations/main_sweep.yaml").plot_layout

    assert (layout.split, layout.x, layout.lines) == (None, _STALL, _REDUNDANCY)


@pytest.mark.parametrize(
    ("vary", "merged"),
    [
        ({_REDUNDANCY: [0, 1], _STALL: [0, 1]}, []),
        ({_STALL: [0.1, 1], _REDUNDANCY: [0, 2], _DELAY: [2, 8]}, [_DELAY]),
        ({"routing.mode": ["ecmp", "adaptive"], _REDUNDANCY: [0, 1]}, ["routing.mode"]),
        # A key with one value merges nothing.
        ({_DELAY: [8], _REDUNDANCY: [0, 1]}, []),
        # Stall percent takes the x axis, so a varied link failure percent would be merged.
        ({_STALL: [0, 1], "topology.link_failure_percent": [0, 5]}, ["topology.link_failure_percent"]),
        ({"topology.link_failure_percent": [0, 5], _REDUNDANCY: [0, 1]}, []),
    ],
)
def test_standard_plot_merged_keys(vary, merged) -> None:
    from visualization.experiment_visualizer import standard_plot_merged_keys

    assert standard_plot_merged_keys(tuple((key, tuple(values)) for key, values in vary.items())) == merged


def test_sweep_skips_standard_plots_that_would_merge_runs(monkeypatch, capsys, write_sweep_config) -> None:
    cfg = write_sweep_config({_STALL: [0.1, 1], _REDUNDANCY: [0, 2], _DELAY: [2, 8]}, visualize_summary=True, drop=())
    calls: dict[str, int] = {"compare": 0, "layout": 0}

    def _fake_compare(summary, **kwargs):
        calls["compare"] += 1
        return []

    def _fake_layout(summary, **kwargs):
        calls["layout"] += 1
        return []

    monkeypatch.setattr(sim_app, "run_sweep", lambda **kwargs: [{"label": "ok", "ok": True}])
    monkeypatch.setattr(sim_app, "visualize_sweep_time_comparison", _fake_compare)
    monkeypatch.setattr(sim_app, "visualize_sweep_layout", _fake_layout)

    assert sim_app.main(["sweep", "--config", cfg]) == 0

    assert calls == {"compare": 0, "layout": 1}
    skipped = [line for line in capsys.readouterr().out.splitlines() if line.startswith("Skipped the standard comparison plots")]
    assert len(skipped) == 1
    assert _DELAY in skipped[0]


def test_message_size_sweep_overrides_message_size_and_stall_delay() -> None:
    spec = load_experiment_spec(config_path="repo:experiments/research_configurations/message_size_sweep.yaml", overrides=[])
    main = load_experiment_spec(config_path="repo:experiments/research_configurations/main_sweep.yaml", overrides=[])

    assert spec.ai_workload.bucket_bytes_per_participant == 65536000
    assert spec.stall_regime.packet_stall_delay_ms == 80.0
    assert spec.ai_workload.steps == main.ai_workload.steps
    assert spec.ai_workload.single_ring_only is True
