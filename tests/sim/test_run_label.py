from __future__ import annotations

import sys
from pathlib import Path

import yaml

from run_label import MAX_LABEL_SLUG_LEN, label_slug
from sim.runners.deep_flow_log import write_sweep_deep_flow_logs
from visualization import build_topology_viz

_REPO_ROOT = Path(__file__).resolve().parents[2]

LONG_LABEL = (
    "C:/Users/someone/AppData/Local/Temp/a-very-long-scratch-directory-name-that-goes-on/"
    "and-on-3f98e8d5-84a9-4182-a482-099c6e85d08c/scratchpad/smoke/tiny_sweep.yaml"
    " | stall_regime.packet_stall_percent=0.0"
    " | ai_workload.flow_redundancy_extra_packets=0"
)


def test_short_label_keeps_its_full_slug() -> None:
    label = "tests/fixtures/dp_small_sweep.yaml | routing.mode=ecmp"

    assert label_slug(label) == "tests_fixtures_dp_small_sweep.yaml_routing.mode_ecmp"


def test_long_label_is_shortened_but_keeps_file_name_values_and_stays_unique() -> None:
    slug = label_slug(LONG_LABEL)

    assert len(slug) <= MAX_LABEL_SLUG_LEN
    assert slug.startswith("tiny_sweep.yaml_stall_regime.packet_stall_percent_0.0")
    assert label_slug(LONG_LABEL) == slug
    assert label_slug(LONG_LABEL.replace("percent=0.0", "percent=1.0")) != slug


def test_deep_flow_logs_are_written_for_a_long_label(tmp_path: Path) -> None:
    row = {
        "ok": True,
        "label": LONG_LABEL,
        "deep_flow_chain_log_enabled": True,
        "deep_flow_chain_diagnostics": [
            {"job_id": 1, "step_id": 0, "phase_id": 1, "bucket_id": 0, "op_tag": "reduce_scatter",
             "ring_step": 0, "src_node_id": "h1", "dst_node_id": "h2", "sim_start_time": 0.0, "sim_end_time": 0.001},
        ],
    }

    written = write_sweep_deep_flow_logs([row], out_dir=str(tmp_path))

    assert len(written) == 1
    assert written[0].exists()
    assert len(written[0].parent.name) <= MAX_LABEL_SLUG_LEN


def test_build_topology_viz_writes_to_the_requested_output(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "out" / "topology.png"
    cfg = tmp_path / "tiny.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "extends": (_REPO_ROOT / "tests" / "fixtures" / "dp_small.yaml").as_posix(),
                "topology": {"leaf_count": 2, "spine_count": 2, "servers_per_leaf": 2},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["build_topology_viz.py", "--config", str(cfg), "--output", str(output)])

    assert build_topology_viz.main() == 0
    assert output.exists()
    assert not list((tmp_path / "results").glob("topology_*.png"))
