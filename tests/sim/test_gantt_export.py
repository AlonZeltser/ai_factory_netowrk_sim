from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import apps.sim as sim_app
from sim.config.loader import load_sweep_spec
from sim.config.models import ConfigError
from sim.runners.deep_flow_log import chain_log_path, keep_sampled_steps, sample_chain_log_steps
from sim.runners.gantt_export import check_gantt_export_ready, plan_gantt_pdfs
from sim.runners.sweep_executor import write_sweep_summary

DP_SMALL = "repo:tests/fixtures/dp_small.yaml"


def _record(step_id: int, start: float, end: float, job_id: int = 1) -> dict:
    return {"job_id": job_id, "step_id": step_id, "sim_start_time": start, "sim_end_time": end}


def test_samples_are_the_first_middle_and_slowest_step() -> None:
    records = [
        _record(0, 0.0, 1.0),
        _record(1, 2.0, 3.0),
        _record(2, 4.0, 4.5),
        _record(3, 5.0, 9.0),  # slowest: spans 4.0
        _record(3, 6.0, 7.0),
        _record(4, 10.0, 11.0),
        _record(-1, 0.0, 99.0),  # not a training step
    ]

    assert sample_chain_log_steps(records) == [
        {"job_id": 1, "step_id": 0, "kinds": ["first"]},
        {"job_id": 1, "step_id": 2, "kinds": ["middle"]},
        {"job_id": 1, "step_id": 3, "kinds": ["slowest"]},
    ]


def test_a_step_picked_twice_appears_once_with_both_kinds() -> None:
    records = [_record(0, 0.0, 5.0), _record(1, 6.0, 7.0)]

    assert sample_chain_log_steps(records) == [
        {"job_id": 1, "step_id": 0, "kinds": ["first", "slowest"]},
        {"job_id": 1, "step_id": 1, "kinds": ["middle"]},
    ]


def test_only_records_of_sampled_steps_are_kept() -> None:
    records = [_record(step, step, step + 1.0) for step in range(5)]
    samples = [{"job_id": 1, "step_id": 0, "kinds": ["first"]}, {"job_id": 1, "step_id": 4, "kinds": ["slowest"]}]

    assert [record["step_id"] for record in keep_sampled_steps(records, samples)] == [0, 4]


def test_gantt_settings_are_parsed(write_sweep_config) -> None:
    cfg = write_sweep_config(
        {"routing.mode": ["ecmp", "adaptive"], "ai_workload.flow_redundancy_extra_packets": [0, 1, 2]},
        gantt_pdfs=True,
        gantt_chain_limit=12,
        gantt_compare={"ai_workload.flow_redundancy_extra_packets": [0, 2]},
        drop=(),
    )
    sweep = load_sweep_spec(cfg)

    assert sweep.gantt_pdfs is True
    assert sweep.gantt_chain_limit == 12
    assert sweep.gantt_compare == ("ai_workload.flow_redundancy_extra_packets", (0, 2))


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"gantt_chain_limit": 0}, "'sweep.gantt_chain_limit' must be an integer >= 1"),
        ({"gantt_chain_limit": True}, "'sweep.gantt_chain_limit' must be an integer >= 1"),
        ({"gantt_compare": [1]}, "Expected mapping at 'sweep.gantt_compare'"),
        ({"gantt_compare": {"routing.mod": ["ecmp", "adaptive"]}}, "must be one of the 'sweep.vary' keys"),
        ({"gantt_compare": {"routing.mode": ["ecmp"]}}, "must list 2 to 4 values"),
        ({"gantt_compare": {"routing.mode": ["ecmp", "flowlet"]}}, r"values \['flowlet'\] are not in"),
        (
            {"gantt_compare": {"routing.mode": ["ecmp", "adaptive"], "ai_workload.steps": [1, 2]}},
            "takes one vary key",
        ),
    ],
)
def test_invalid_gantt_settings_are_rejected(write_sweep_config, settings: dict, message: str) -> None:
    cfg = write_sweep_config({"routing.mode": ["ecmp", "adaptive"], "ai_workload.steps": [1, 2]}, **settings, drop=())

    with pytest.raises(ConfigError, match=message):
        load_sweep_spec(cfg)


def test_gantt_pdfs_need_chain_logs_and_fail_before_the_sweep_runs(monkeypatch, write_sweep_config, capsys) -> None:
    cfg = write_sweep_config({"routing.mode": ["ecmp"]}, gantt_pdfs=True, drop=())  # dp_small: deep_flow_chain_log false
    monkeypatch.setattr(sim_app, "run_sweep", lambda **_: pytest.fail("the sweep must not start"))

    assert sim_app.main(["sweep", "--config", cfg]) == 2
    assert "sweep.gantt_pdfs needs deep_flow_chain_log: true" in capsys.readouterr().err


def _row(label: str, samples: list[dict]) -> dict:
    return {"label": label, "ok": True, "deep_flow_chain_sample_steps": samples}


def test_plan_has_one_pdf_per_sample_step_and_comparisons_per_group(write_sweep_config, tmp_path: Path) -> None:
    cfg = write_sweep_config(
        {"stall_regime.packet_stall_percent": [0, 1], "ai_workload.flow_redundancy_extra_packets": [0, 2, 8]},
        gantt_pdfs=True,
        gantt_compare={"ai_workload.flow_redundancy_extra_packets": [8, 0]},
        drop=(),
    )
    sweep = load_sweep_spec(cfg)
    first_and_slowest = [
        {"job_id": 1, "step_id": 0, "kinds": ["first", "slowest"]},
        {"job_id": 1, "step_id": 1, "kinds": ["middle"]},
    ]
    summary = [
        _row(f"c.yaml | stall_regime.packet_stall_percent={stall} | ai_workload.flow_redundancy_extra_packets={red}", first_and_slowest)
        for stall in (0, 1)
        for red in (0, 2, 8)
    ]
    summary.append({"label": "failed", "ok": False})
    root, out = tmp_path / "logs", tmp_path / "pdfs"

    plans = plan_gantt_pdfs(summary, sweep=sweep, chain_log_root=root, out_dir=out)

    singles = [plan for plan in plans if plan.labels is None]
    compares = [plan for plan in plans if plan.labels is not None]
    assert len(singles) == 6 * 2
    assert len(compares) == 2 * 3  # 2 stall values x first/middle/slowest
    stall_1_slowest = next(p for p in compares if p.out.name == "packet_stall_percent_1_slowest.pdf")
    # Panels follow the order given in gantt_compare, and each run uses its own sample step.
    assert stall_1_slowest.labels == ("flow_redundancy_extra_packets=8 (step 0)", "flow_redundancy_extra_packets=0 (step 0)")
    assert stall_1_slowest.logs == (
        chain_log_path(root, summary[5]["label"], 1, 0),
        chain_log_path(root, summary[3]["label"], 1, 0),
    )
    assert stall_1_slowest.title == "packet_stall_percent=1 | slowest step, by flow_redundancy_extra_packets"


def test_summary_file_leaves_out_the_raw_chain_records(tmp_path: Path) -> None:
    row = {"label": "x", "ok": True, "deep_flow_chain_diagnostics": [{"step_id": 0}], "deep_flow_chain_sample_steps": []}

    path = write_sweep_summary([row], str(tmp_path / "summary.yaml"))

    assert yaml.safe_load(path.read_text(encoding="utf-8")) == [{"label": "x", "ok": True, "deep_flow_chain_sample_steps": []}]


def test_sweep_writes_gantt_pdfs_for_sample_steps(tmp_path: Path) -> None:
    try:
        check_gantt_export_ready()
    except ConfigError as exc:
        pytest.skip(f"PDF export is not available here: {exc}")
    cfg = tmp_path / "gantt.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "extends": DP_SMALL,
                "deep_flow_chain_log": True,
                "ai_workload": {"steps": 3},
                "sweep": {
                    "vary": {"ai_workload.flow_redundancy_extra_packets": [0, 1]},
                    "summary_out": (tmp_path / "out" / "summary.yaml").as_posix(),
                    "visualize_summary": False,
                    "plot_ring_heatmaps": False,
                    "lower_zoom_percent": 15.0,
                    "stop_on_error": True,
                    "processes": 1,
                    "plot_topology_once": False,
                    "show_visualization_window": False,
                    "paper_style": False,
                    "gantt_pdfs": True,
                    "gantt_chain_limit": 40,
                    "gantt_compare": {"ai_workload.flow_redundancy_extra_packets": [0, 1]},
                },
            }
        ),
        encoding="utf-8",
    )

    assert sim_app.main(["sweep", "--config", str(cfg)]) == 0

    out = tmp_path / "out"
    summary = yaml.safe_load((out / "summary.yaml").read_text(encoding="utf-8"))
    sample_count = sum(len(row["deep_flow_chain_sample_steps"]) for row in summary)
    assert 2 <= sample_count <= 6
    # Only the sample steps get chain logs.
    assert len(list((out / "deep_flow_chain_logs").rglob("*.txt"))) == sample_count
    pdfs = list((out / "gantt_pdfs").rglob("*.pdf"))
    assert len(pdfs) == sample_count + 3  # + first/middle/slowest comparison
    assert all(pdf.read_bytes().startswith(b"%PDF") for pdf in pdfs)
