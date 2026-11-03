from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
DP_SMALL = "tests/fixtures/dp_small.yaml"


@pytest.fixture
def write_sweep_config(tmp_path: Path) -> Callable[..., str]:
    """Return a writer for an experiment file that extends dp_small.yaml and has a full sweep section.

    `vary` is the sweep.vary mapping. Keyword arguments replace sweep settings (or add
    unknown keys); `drop` removes settings, to test missing-key errors.
    """

    def _write(vary: Any, *, drop: tuple[str, ...] = (), **settings: Any) -> str:
        sweep: dict[str, Any] = {
            "vary": vary,
            "summary_out": (tmp_path / "out" / "summary.yaml").as_posix(),
            "visualize_summary": False,
            "plot_ring_heatmaps": False,
            "lower_zoom_percent": 15.0,
            "stop_on_error": False,
            "processes": "auto",
            "plot_topology_once": False,
            "show_visualization_window": False,
        }
        sweep.update(settings)
        for key in drop:
            del sweep[key]
        cfg = tmp_path / "exp.yaml"
        cfg.write_text(
            yaml.safe_dump({"extends": (_REPO_ROOT / DP_SMALL).as_posix(), "sweep": sweep}, sort_keys=False),
            encoding="utf-8",
        )
        return str(cfg)

    return _write
