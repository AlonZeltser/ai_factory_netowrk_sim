from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ring_collective_stall_visualizer import export_gantt_pdf


@pytest.mark.parametrize(
    "missing",
    [["--color-by", "stall_bucket"], ["--chain-limit", "16"]],
)
def test_color_by_and_chain_limit_are_required(tmp_path: Path, missing: list[str]) -> None:
    options = ["--out", str(tmp_path / "gantt.pdf"), "--color-by", "stall_bucket", "--chain-limit", "16"]
    start = options.index(missing[0])
    del options[start : start + 2]

    with pytest.raises(SystemExit) as exc:
        export_gantt_pdf.main([str(tmp_path / "scan.log"), *options])

    assert exc.value.code == 2


def test_filter_on_a_missing_column_is_an_error() -> None:
    df = pd.DataFrame({"step": [0, 1]})

    with pytest.raises(ValueError, match="the log has no column 'stpe'"):
        export_gantt_pdf._apply_filters(df, ["stpe=0"])


def test_filter_keeps_matching_rows() -> None:
    df = pd.DataFrame({"step": [0, 1, 2]})

    assert export_gantt_pdf._apply_filters(df, ["step=0,2"])["step"].tolist() == [0, 2]
