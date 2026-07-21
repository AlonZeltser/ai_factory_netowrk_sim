from __future__ import annotations

import pandas as pd

from ring_collective_stall_visualizer.ringviz.parser import parse_log_text
from ring_collective_stall_visualizer.ringviz.plots import make_heatmap


def test_parse_log_text_adds_stalled_packets_when_missing() -> None:
    text = """
header: net packets in flow, gross packets in flow
columns: sending host, receiving host, sim start time, sim end time, sim duration, max place in egress, average place in egress, latest arriving valuable packet to receiver (N): start time, end time, list of egress values, sum of egress

[chain_group] job=1 step=0 phase=1 bucket=0 op=reduce_scatter
chain h1
  net packets in flow=2 | gross packets in flow=2 | sending host=h1 | receiving host=h2 | sim start time=0.000000 | sim end time=0.010000 | sim duration=0.010000 | max place in egress=3 | average place in egress=2.000000 | N start time=0.003000 | N end time=0.010000 | N egress values=[1, 3] | N egress sum=4
""".strip()

    df = parse_log_text(text)

    assert not df.empty
    assert "stalled_packets" in df.columns
    assert pd.isna(df.loc[0, "stalled_packets"])
    assert "stall_bucket" in df.columns
    assert str(df.loc[0, "stall_bucket"]) == "unknown"
    assert df.loc[0, "edge"] == "h1 → h2"


def test_make_heatmap_handles_logs_without_stalled_packets_field() -> None:
    text = """
header: net packets in flow, gross packets in flow
columns: sending host, receiving host, sim start time, sim end time, sim duration, max place in egress, average place in egress, latest arriving valuable packet to receiver (N): start time, end time, list of egress values, sum of egress

[chain_group] job=1 step=0 phase=1 bucket=0 op=reduce_scatter
chain h1
  net packets in flow=2 | gross packets in flow=2 | sending host=h1 | receiving host=h2 | sim start time=0.000000 | sim end time=0.010000 | sim duration=0.010000 | max place in egress=3 | average place in egress=2.000000 | N start time=0.003000 | N end time=0.010000 | N egress values=[1, 3] | N egress sum=4
""".strip()

    df = parse_log_text(text)
    fig = make_heatmap(df, metric="duration_ms", chain_limit=8)

    assert len(fig.data) == 1
    assert fig.data[0].text[0][0]
    assert "stalled packets: <NA>" in fig.data[0].text[0][0] or "stalled packets: " in fig.data[0].text[0][0]


def test_parse_log_text_preserves_non_zero_stalled_packets() -> None:
    text = """
header: net packets in flow, gross packets in flow
columns: sending host, receiving host, sim start time (step-relative), sim end time (step-relative), sim duration, # of packets stalled, max place in egress, average place in egress, latest arriving valuable packet to receiver (N): start time, end time, list of egress values, sum of egress

[chain_group] job=1 step=0 phase=1 bucket=0 op=reduce_scatter
chain h1
  net packets in flow=2 | gross packets in flow=3 | sending host=h1 | receiving host=h2 | sim start time=0.000000 | sim end time=0.010000 | sim duration=0.010000 | # of packets stalled=2 | max place in egress=3 | average place in egress=2.000000 | N start time=0.003000 | N end time=0.010000 | N egress values=[1, 3] | N egress sum=4
""".strip()

    df = parse_log_text(text)

    assert int(df.loc[0, "stalled_packets"]) == 2
    assert str(df.loc[0, "stall_bucket"]) == "2"


