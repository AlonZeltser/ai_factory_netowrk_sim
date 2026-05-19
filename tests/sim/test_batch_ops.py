from __future__ import annotations

from pathlib import Path

from sim.runners.batch_runner import collect_batch_inputs, run_batch, write_batch_summary
from sim.runners.sweep_runner import build_sweep_inputs, run_sweep


def test_collect_and_run_batch_from_presets() -> None:
    inputs = collect_batch_inputs(presets=["ai/su-dp-light", "ai/su-mixed-light"])
    summary = run_batch(inputs)

    assert len(summary) == 2
    assert all(item["ok"] for item in summary)


def test_collect_batch_from_directory_and_write_summary(tmp_path: Path) -> None:
    cfg = tmp_path / "batch_case.yaml"
    topology_defaults = Path("sim/presets/ai/topology-clos-large-scale-unit.yaml").resolve()
    cfg.write_text(
        f"""
extends: {topology_defaults}
kind: experiment
meta:
  name: batch-case
run:
  visualize: false
routing:
  mode: ecmp
  ecmp_flowlet_n_packets: 1
workload:
  kind: none
  params: {{}}
""".strip(),
        encoding="utf-8",
    )

    inputs = collect_batch_inputs(directory=str(tmp_path))
    summary = run_batch(inputs)
    assert len(summary) == 1
    assert summary[0]["ok"] is True

    out = write_batch_summary(summary, str(tmp_path / "summary.yaml"))
    assert out.exists()
    assert "batch-case" not in out.read_text(encoding="utf-8") or out.read_text(encoding="utf-8")


def test_build_and_run_sweep() -> None:
    inputs = build_sweep_inputs(
        preset_name="ai/su-dp-light",
        vary_specs=["workload.kind=dp-heavy,none", "topology.params.leaf_count=8,16"],
    )
    assert len(inputs) == 4

    summary = run_sweep(
        preset_name="ai/su-dp-light",
        vary_specs=["workload.kind=dp-heavy,none", "topology.params.leaf_count=8,16"],
    )
    assert len(summary) == 4
    assert all(item["ok"] for item in summary)
    assert {item["workload"] for item in summary} == {"dp-heavy", "none"}


