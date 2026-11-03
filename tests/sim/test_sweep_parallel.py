from __future__ import annotations

from pathlib import Path

import apps.sim as sim_app
from sim.config.loader import load_sweep_spec
from sim.runners.sweep_executor import SweepInput
from sim.runners import sweep_executor, sweep_runner

DP_SMALL = "tests/fixtures/dp_small.yaml"


def test_default_process_count_balances_tasks(monkeypatch) -> None:
    monkeypatch.setattr(sweep_executor.os, "cpu_count", lambda: 8)

    assert sweep_executor._default_process_count(1) == 1
    assert sweep_executor._default_process_count(8) == 4
    assert sweep_executor._default_process_count(10) == 3
    assert sweep_executor._default_process_count(17) == 3


def test_run_sweep_takes_workers_and_stop_on_error_from_the_sweep_section(monkeypatch, write_sweep_config) -> None:
    captured: dict[str, object] = {}

    def _fake_run_sweep_inputs(inputs, *, stop_on_error, use_processes, max_processes):
        captured["count"] = len(inputs)
        captured["stop_on_error"] = stop_on_error
        captured["use_processes"] = use_processes
        captured["max_processes"] = max_processes
        return [{"label": i.label, "ok": True} for i in inputs]

    monkeypatch.setattr(sweep_runner, "run_sweep_inputs", _fake_run_sweep_inputs)
    cfg = write_sweep_config({"routing.mode": ["ecmp", "adaptive"]}, processes=3, stop_on_error=True, drop=())

    summary = sweep_runner.run_sweep(config_path=cfg, sweep=load_sweep_spec(cfg))

    assert len(summary) == 2
    assert captured == {
        "count": 2,
        "stop_on_error": True,
        "use_processes": True,
        "max_processes": 3,
    }


def test_sweep_cli_passes_the_config_sweep_section(monkeypatch, write_sweep_config) -> None:
    captured: dict[str, object] = {}

    def _fake_run_sweep(**kwargs):
        captured.update(kwargs)
        return [{"label": "test", "ok": True}]

    monkeypatch.setattr(sim_app, "run_sweep", _fake_run_sweep)
    cfg = write_sweep_config({"routing.mode": ["ecmp", "adaptive"]}, processes=4, drop=())

    exit_code = sim_app.main(["sweep", "--config", cfg])

    assert exit_code == 0
    assert captured["config_path"] == cfg
    assert captured["sweep"] == load_sweep_spec(cfg)
    assert captured["sweep"].max_processes == 4


def test_sweep_cli_plot_topology_once_uses_first_combo(monkeypatch, write_sweep_config) -> None:
    calls: dict[str, object] = {}

    def _fake_build_inputs(**kwargs):
        calls["build_inputs"] = kwargs
        return [SweepInput(label="first", config_path=DP_SMALL, overrides=("routing.mode=ecmp",))]

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
    cfg = write_sweep_config({"routing.mode": ["ecmp", "adaptive"]}, plot_topology_once=True, drop=())

    exit_code = sim_app.main(["sweep", "--config", cfg])

    assert exit_code == 0
    assert calls["topology_create"] is True
    assert calls["load_spec"] == {
        "config_path": DP_SMALL,
        "overrides": ["routing.mode=ecmp"],
    }


def test_sweep_cli_plot_ring_heatmaps_without_comparison(monkeypatch, write_sweep_config) -> None:
    calls: dict[str, object] = {"comparison": 0, "heatmaps": 0}

    def _fake_run_sweep(**kwargs):
        return [{"label": "ok", "ok": True, "training_step_traffic_matrices": []}]

    def _fake_compare(summary, *, out_dir, show, training_step_time_lower_zoom_percent):
        calls["comparison"] = int(calls["comparison"]) + 1
        return ["cmp.png"]

    def _fake_heatmaps(summary, *, out_dir, show):
        calls["heatmaps"] = int(calls["heatmaps"]) + 1
        return ["heat.png"]

    monkeypatch.setattr(sim_app, "run_sweep", _fake_run_sweep)
    monkeypatch.setattr(sim_app, "visualize_sweep_time_comparison", _fake_compare)
    monkeypatch.setattr(sim_app, "visualize_summary_training_step_traffic_matrices", _fake_heatmaps)
    cfg = write_sweep_config({"routing.mode": ["ecmp", "adaptive"]}, plot_ring_heatmaps=True, drop=())

    exit_code = sim_app.main(["sweep", "--config", cfg])

    assert exit_code == 0
    assert calls["comparison"] == 0
    assert calls["heatmaps"] == 1


def test_sweep_cli_writes_deep_flow_chain_logs(monkeypatch, tmp_path: Path, write_sweep_config) -> None:
    summary_path = tmp_path / "summary.yaml"
    cfg = write_sweep_config({"routing.mode": ["ecmp", "adaptive"]}, summary_out=summary_path.as_posix(), drop=())

    def _fake_run_sweep(**_kwargs):
        return [
            {
                "label": "dp_small.yaml | routing.mode=adaptive",
                "ok": True,
                "deep_flow_chain_log_enabled": True,
                "deep_flow_chain_diagnostics": [
                    {
                        "job_id": 1,
                        "step_id": 0,
                        "phase_id": 0,
                        "bucket_id": 0,
                        "op_tag": "reduce_scatter",
                        "ring_step": 0,
                        "src_node_id": "h1",
                        "dst_node_id": "h2",
                        "sim_start_time": 1.0,
                        "sim_end_time": 1.5,
                        "sim_duration": 0.5,
                        "packets_stalled": 1,
                        "net_packets_in_flow": 2,
                        "gross_packets_in_flow": 3,
                        "stall_percentage": 50.0,
                        "max_place_in_egress": 4,
                        "avg_place_in_egress": 2.5,
                        "latest_valuable_packet_start_time": 1.2,
                        "latest_valuable_packet_end_time": 1.5,
                        "latest_valuable_packet_egress_values": [1, 3],
                        "latest_valuable_packet_egress_sum": 4,
                    }
                ],
            }
        ]

    monkeypatch.setattr(sim_app, "run_sweep", _fake_run_sweep)

    exit_code = sim_app.main(["sweep", "--config", cfg])

    assert exit_code == 0
    deep_root = summary_path.parent / "deep_flow_chain_logs"
    generated = list(deep_root.rglob("*.txt"))
    assert generated
    content = generated[0].read_text(encoding="utf-8")
    assert "header: net packets in flow, gross packets in flow" in content
    assert "stall packets=" not in content
    assert "# of packets stalled=1" in content
    assert "sending host=h1" in content
    assert "sim start time=0.000000" in content
    assert "sim end time=0.500000" in content
    assert "N start time=0.200000" in content
    assert "N end time=0.500000" in content


