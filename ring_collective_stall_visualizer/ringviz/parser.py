import re
import ast
from typing import Any, Dict, List, Optional

import pandas as pd


CHAIN_GROUP_RE = re.compile(r"^\[chain_group\]\s+(.*)$")
CHAIN_RE = re.compile(r"^\s*chain\s+(\S+)\s*$")
FLOW_RE = re.compile(r"^\s*net packets in flow=")


KEY_MAP = {
    "net packets in flow": "net_packets",
    "gross packets in flow": "gross_packets",
    "stall packets": "stall_packets_declared",
    "sending host": "sender",
    "receiving host": "receiver",
    "sim start time": "start_s",
    "sim end time": "end_s",
    "sim duration": "duration_s",
    "# of packets stalled": "stalled_packets",
    "max place in egress": "max_egress",
    "average place in egress": "avg_egress",
    "N start time": "n_start_s",
    "N end time": "n_end_s",
    "N egress values": "n_egress_values",
    "N egress sum": "n_egress_sum",
}


def _parse_scalar(value: str) -> Any:
    value = value.strip()

    if value.startswith("[") and value.endswith("]"):
        try:
            return ast.literal_eval(value)
        except Exception:
            return value

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _parse_key_values(text: str, separator: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    for part in text.split(separator):
        part = part.strip()

        if "=" not in part:
            continue

        raw_key, raw_value = part.split("=", 1)

        raw_key = raw_key.strip()
        raw_value = raw_value.strip()

        key = KEY_MAP.get(raw_key, raw_key)
        result[key] = _parse_scalar(raw_value)

    return result


def _parse_chain_group_metadata(line: str) -> Dict[str, Any]:
    match = CHAIN_GROUP_RE.match(line)

    if not match:
        return {}

    metadata_text = match.group(1)
    result: Dict[str, Any] = {}

    for token in metadata_text.split():
        if "=" not in token:
            continue

        key, value = token.split("=", 1)
        result[key.strip()] = _parse_scalar(value.strip())

    return result


def _stall_bucket(x: Any) -> str:
    if pd.isna(x):
        return "unknown"

    x = int(x)

    if x <= 0:
        return "0"
    if x == 1:
        return "1"
    if x == 2:
        return "2"
    if x == 3:
        return "3"
    if x == 4:
        return "4"

    return "5+"


def parse_log_text(text: str) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    current_group: Dict[str, Any] = {}
    current_chain: Optional[str] = None
    hop_index_by_chain: Dict[str, int] = {}

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")

        if not line.strip():
            continue

        if CHAIN_GROUP_RE.match(line):
            current_group = _parse_chain_group_metadata(line)
            current_chain = None
            hop_index_by_chain = {}
            continue

        chain_match = CHAIN_RE.match(line)

        if chain_match:
            current_chain = chain_match.group(1)
            hop_index_by_chain.setdefault(current_chain, 0)
            continue

        if FLOW_RE.match(line):
            if current_chain is None:
                continue

            flow = _parse_key_values(line, "|")

            hop_index = hop_index_by_chain[current_chain]
            hop_index_by_chain[current_chain] += 1

            row = {
                **current_group,
                **flow,
                "chain": current_chain,
                "hop_index": hop_index,
            }

            rows.append(row)

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    numeric_cols = [
        "job",
        "step",
        "phase",
        "bucket",
        "net_packets",
        "gross_packets",
        "stall_packets_declared",
        "start_s",
        "end_s",
        "duration_s",
        "stalled_packets",
        "max_egress",
        "avg_egress",
        "n_start_s",
        "n_end_s",
        "n_egress_sum",
        "hop_index",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "sender" in df.columns and "receiver" in df.columns:
        df["edge"] = df["sender"].astype(str) + " → " + df["receiver"].astype(str)

    # Newer deep-flow logs may omit stalled-packet fields; keep downstream visualizations stable.
    if "stalled_packets" not in df.columns:
        if "stall_packets_declared" in df.columns:
            df["stalled_packets"] = pd.to_numeric(df["stall_packets_declared"], errors="coerce").fillna(0)
        else:
            df["stalled_packets"] = pd.Series([pd.NA] * len(df), index=df.index, dtype="Int64")

    if "stalled_packets" in df.columns:
        df["stall_bucket"] = df["stalled_packets"].apply(_stall_bucket)

    if "duration_s" in df.columns:
        df["duration_ms"] = df["duration_s"] * 1000.0

    if "start_s" in df.columns:
        df["start_ms"] = df["start_s"] * 1000.0

    if "end_s" in df.columns:
        df["end_ms"] = df["end_s"] * 1000.0

    return df


def load_log_file(path: str) -> pd.DataFrame:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return parse_log_text(f.read())