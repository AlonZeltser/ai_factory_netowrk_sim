from __future__ import annotations

import apps.sim as sim_app
from sim.runners.batch_runner import BatchInput
from sim.runners import batch_runner, sweep_runner


def test_default_process_count_balances_tasks(monkeypatch) -> None:
    monkeypatch.setattr(batch_runner.os, "cpu_count", lambda: 8)

    assert batch_runner._default_process_count(1) == 1
    assert batch_runner._default_process_count(8) == 4
    assert batch_runner._default_process_count(10) == 3
    assert batch_runner._default_process_count(17) == 3


def test_run_sweep_enables_process_workers(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run_batch(inputs, *, stop_on_error=False, use_processes=False, max_processes=None):
        captured["count"] = len(inputs)
        captured["stop_on_error"] = stop_on_error
        captured["use_processes"] = use_processes
        captured["max_processes"] = max_processes
        return [{"label": i.label, "ok": True} for i in inputs]

    monkeypatch.setattr(sweep_runner, "run_batch", _fake_run_batch)

    summary = sweep_runner.run_sweep(
        preset_name="ai/dp-low-small",
        vary_specs=["routing.mode=ecmp,adaptive"],
        max_processes=3,
    )

    assert len(summary) == 2
    assert captured == {
        "count": 2,
        "stop_on_error": False,
        "use_processes": True,
        "max_processes": 3,
    }


def test_sweep_cli_forwards_process_count(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run_sweep(**kwargs):
        captured.update(kwargs)
        return [{"label": "test", "ok": True}]

    monkeypatch.setattr(sim_app, "run_sweep", _fake_run_sweep)

    exit_code = sim_app.main(
        [
            "sweep",
            "--preset",
            "ai/dp-low-small",
            "--vary",
            "routing.mode=ecmp,adaptive",
            "--processes",
            "4",
        ]
    )

    assert exit_code == 0
    assert captured["max_processes"] == 4
    assert captured["preset_name"] == "ai/dp-low-small"
    assert captured["vary_specs"] == ["routing.mode=ecmp,adaptive"]


def test_sweep_cli_maps_packet_memory_flags_to_overrides(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run_sweep(**kwargs):
        captured.update(kwargs)
        return [{"label": "test", "ok": True}]

    monkeypatch.setattr(sim_app, "run_sweep", _fake_run_sweep)

    exit_code = sim_app.main(
        [
            "sweep",
            "--preset",
            "ai/dp-low-small",
            "--vary",
            "routing.mode=ecmp,adaptive",
            "--store-packets",
            "--collect-packet-timeline",
        ]
    )

    assert exit_code == 0
    overrides = captured.get("base_overrides")
    assert isinstance(overrides, list)
    assert "run.store_packets=true" in overrides
    assert "run.collect_packet_timeline=true" in overrides


def test_sweep_cli_plot_topology_once_uses_first_combo(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def _fake_build_inputs(**kwargs):
        calls["build_inputs"] = kwargs
        return [BatchInput(label="first", preset_name="ai/dp-low-small", overrides=("routing.mode=ecmp",))]

    def _fake_load_spec(**kwargs):
        calls["load_spec"] = kwargs
        return object()

    class _FakeNetwork:
        def create(self, visualize):
            calls["topology_create"] = visualize

    def _fake_build_network(spec):
        calls["build_network_spec"] = spec
        return _FakeNetwork()

    def _fake_run_sweep(**kwargs):
        calls["run_sweep"] = kwargs
        return [{"label": "ok", "ok": True}]

    monkeypatch.setattr(sim_app, "build_sweep_inputs", _fake_build_inputs)
    monkeypatch.setattr(sim_app, "load_experiment_spec", _fake_load_spec)
    monkeypatch.setattr(sim_app, "build_network", _fake_build_network)
    monkeypatch.setattr(sim_app, "run_sweep", _fake_run_sweep)

    exit_code = sim_app.main(
        [
            "sweep",
            "--preset",
            "ai/dp-low-small",
            "--vary",
            "routing.mode=ecmp,adaptive",
            "--plot-topology-once",
        ]
    )

    assert exit_code == 0
    assert calls["topology_create"] is True
    assert calls["load_spec"] == {
        "preset_name": "ai/dp-low-small",
        "config_path": None,
        "overrides": ["routing.mode=ecmp"],
    }


def test_sweep_cli_plot_ring_heatmaps_without_comparison(monkeypatch) -> None:
    calls: dict[str, object] = {"comparison": 0, "heatmaps": 0}

    def _fake_run_sweep(**kwargs):
        return [{"label": "ok", "ok": True, "step_traffic_matrices": []}]

    def _fake_compare(summary, *, out_dir, show):
        calls["comparison"] = int(calls["comparison"]) + 1
        return ["cmp.png"]

    def _fake_heatmaps(summary, *, out_dir, show):
        calls["heatmaps"] = int(calls["heatmaps"]) + 1
        return ["heat.png"]

    monkeypatch.setattr(sim_app, "run_sweep", _fake_run_sweep)
    monkeypatch.setattr(sim_app, "visualize_sweep_time_comparison", _fake_compare)
    monkeypatch.setattr(sim_app, "visualize_summary_step_traffic_matrices", _fake_heatmaps)

    exit_code = sim_app.main(
        [
            "sweep",
            "--preset",
            "ai/dp-low-small",
            "--vary",
            "routing.mode=ecmp,adaptive",
            "--plot-ring-heatmaps",
        ]
    )

    assert exit_code == 0
    assert calls["comparison"] == 0
    assert calls["heatmaps"] == 1


