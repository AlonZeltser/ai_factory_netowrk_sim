from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Mapping


class ConfigError(ValueError):
    """Raised when a unified experiment configuration is invalid."""


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"Expected mapping at '{path}', got {type(value).__name__}")
    return dict(value)


def _key_path(section: str, key: str) -> str:
    # Top-level keys (section "/") are named without a prefix.
    return key if section == "/" else f"{section}.{key}"


def _require_key(data: dict[str, Any], key: str, section: str) -> Any:
    if key not in data:
        raise ConfigError(f"Missing required key '{_key_path(section, key)}'")
    return data[key]


def reject_unknown_keys(data: Mapping[str, Any], allowed: tuple[str, ...], section: str) -> None:
    """Fail on keys the config section does not define, so typos and removed keys never pass silently."""
    unknown = sorted(str(key) for key in data if key not in allowed)
    if unknown:
        raise ConfigError(
            f"Unknown key(s) in '{section}': {', '.join(unknown)}. Allowed: {', '.join(sorted(allowed))}"
        )


def _require_section(data: dict[str, Any], key: str) -> dict[str, Any]:
    if key not in data:
        raise ConfigError(f"Missing required section '{key}'")
    return _require_mapping(data[key], key)


def _require_str(data: dict[str, Any], key: str, section: str, *, allow_empty: bool) -> str:
    value = _require_key(data, key, section)
    if not isinstance(value, str):
        raise ConfigError(f"'{_key_path(section, key)}' must be a string, got {value!r}")
    if not allow_empty and not value.strip():
        raise ConfigError(f"'{_key_path(section, key)}' must not be empty")
    return value


# Converters for the field types of the plain config sections below.
_CONVERTERS = {"int": int, "float": float, "bool": bool, "str": str}


def _parse_fields(cls: type, data: dict[str, Any], section: str) -> dict[str, Any]:
    """Read every field of dataclass `cls` from `data`; all keys are required and no others are allowed."""
    names = tuple(f.name for f in fields(cls))
    reject_unknown_keys(data, names, section)
    values: dict[str, Any] = {}
    for f in fields(cls):
        raw = _require_key(data, f.name, section)
        try:
            values[f.name] = _CONVERTERS[f.type](raw)
        except (TypeError, ValueError):
            raise ConfigError(f"'{_key_path(section, f.name)}' must be {f.type}, got {raw!r}") from None
    return values


# Top-level keys that hold run settings (the config has no `run:` section).
_RUN_KEYS = (
    "seed",
    "file_debug",
    "message_verbose",
    "verbose_route",
    "visualize",
    "show_visualization_window",
    "store_packets",
    "collect_packet_timeline",
    "deep_flow_chain_log",
    "log_dir",
    "results_dir",
)
_SECTION_KEYS = ("topology", "routing", "stall_regime", "ai_workload")
_EXPERIMENT_KEYS = ("name", *_RUN_KEYS, *_SECTION_KEYS)


@dataclass(frozen=True)
class RunSpec:
    # None means the global random generator is left unseeded (runs are not reproducible).
    seed: int | None
    file_debug: bool
    message_verbose: bool
    verbose_route: bool
    visualize: bool
    show_visualization_window: bool
    store_packets: bool
    collect_packet_timeline: bool
    deep_flow_chain_log: bool
    log_dir: str
    results_dir: str

    @staticmethod
    def from_mapping(data: dict[str, Any]) -> "RunSpec":
        """Read the run settings from the top level of the config."""
        seed = _require_key(data, "seed", "/")
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise ConfigError(f"'seed' must be an integer or null, got {seed!r}")
        store_packets = bool(_require_key(data, "store_packets", "/"))
        collect_packet_timeline = bool(_require_key(data, "collect_packet_timeline", "/"))
        if collect_packet_timeline and not store_packets:
            raise ConfigError("'collect_packet_timeline: true' requires 'store_packets: true'")
        return RunSpec(
            seed=seed,
            file_debug=bool(_require_key(data, "file_debug", "/")),
            message_verbose=bool(_require_key(data, "message_verbose", "/")),
            verbose_route=bool(_require_key(data, "verbose_route", "/")),
            visualize=bool(_require_key(data, "visualize", "/")),
            show_visualization_window=bool(_require_key(data, "show_visualization_window", "/")),
            store_packets=store_packets,
            collect_packet_timeline=collect_packet_timeline,
            deep_flow_chain_log=bool(_require_key(data, "deep_flow_chain_log", "/")),
            log_dir=str(_require_key(data, "log_dir", "/")),
            results_dir=str(_require_key(data, "results_dir", "/")),
        )


@dataclass(frozen=True)
class TopologySpec:
    """`topology:` - the two-layer clos (leaf-spine) fabric."""

    layers: int
    leaf_count: int
    spine_count: int
    servers_per_leaf: int
    host_links_per_server: int
    parallel_leaf_to_spine_links: int
    link_failure_percent: float
    server_to_leaf_bandwidth_bps: float
    leaf_to_spine_bandwidth_bps: float

    @staticmethod
    def from_mapping(data: dict[str, Any]) -> "TopologySpec":
        spec = TopologySpec(**_parse_fields(TopologySpec, data, "topology"))
        if spec.layers != 2:
            raise ConfigError("The clos implementation supports only topology.layers=2 (leaf-spine)")
        if spec.leaf_count <= 0:
            raise ConfigError("topology.leaf_count must be >= 1")
        if spec.spine_count <= 0:
            raise ConfigError("topology.spine_count must be >= 1")
        return spec


@dataclass(frozen=True)
class RoutingSpec:
    """`routing:` - path selection and packet limits."""

    max_path: int
    mtu: int
    ttl: int
    mode: str
    ecmp_flowlet_n_packets: int

    @staticmethod
    def from_mapping(data: dict[str, Any]) -> "RoutingSpec":
        return RoutingSpec(**_parse_fields(RoutingSpec, data, "routing"))


@dataclass(frozen=True)
class StallRegimeSpec:
    """`stall_regime:` - retransmit-like packet stalls injected at switches."""

    packet_stall_percent: float
    packet_stall_delay_ms: float
    packet_stall_max_switch_hop: int
    packet_stall_retransmit_priority: bool

    @staticmethod
    def from_mapping(data: dict[str, Any]) -> "StallRegimeSpec":
        return StallRegimeSpec(**_parse_fields(StallRegimeSpec, data, "stall_regime"))


@dataclass(frozen=True)
class AIWorkloadSpec:
    """`ai_workload:` - the DP-heavy training job."""

    steps: int
    seed: int
    num_buckets: int
    bucket_bytes_per_participant: int
    gap_us: float
    prolog_compute_ms: float
    bucket_interval_ms: float
    bucket_scheduling: str
    optimizer_ms: float
    flow_redundancy_extra_packets: int
    single_ring_only: bool

    @staticmethod
    def from_mapping(data: dict[str, Any]) -> "AIWorkloadSpec":
        return AIWorkloadSpec(**_parse_fields(AIWorkloadSpec, data, "ai_workload"))


@dataclass(frozen=True)
class ExperimentSpec:
    name: str
    run: RunSpec
    topology: TopologySpec
    routing: RoutingSpec
    stall_regime: StallRegimeSpec
    ai_workload: AIWorkloadSpec
    source_config_path: str

    @staticmethod
    def from_mapping(value: Any, *, source_config_path: str) -> "ExperimentSpec":
        data = _require_mapping(value, "/")
        reject_unknown_keys(data, _EXPERIMENT_KEYS, "/")
        return ExperimentSpec(
            name=_require_str(data, "name", "/", allow_empty=False),
            run=RunSpec.from_mapping(data),
            topology=TopologySpec.from_mapping(_require_section(data, "topology")),
            routing=RoutingSpec.from_mapping(_require_section(data, "routing")),
            stall_regime=StallRegimeSpec.from_mapping(_require_section(data, "stall_regime")),
            ai_workload=AIWorkloadSpec.from_mapping(_require_section(data, "ai_workload")),
            source_config_path=source_config_path,
        )

    @property
    def display_name(self) -> str:
        return self.name

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            **asdict(self.run),
            "topology": asdict(self.topology),
            "routing": asdict(self.routing),
            "stall_regime": asdict(self.stall_regime),
            "ai_workload": asdict(self.ai_workload),
        }


_SWEEP_KEYS = (
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
# Most logs one Gantt comparison page can show side by side (the visualizer's limit).
GANTT_MAX_PANELS = 4
_SCALAR_TYPES = (str, int, float, bool)
# `sweep.processes: auto` picks a worker count that balances the runs across the CPUs.
SWEEP_PROCESSES_AUTO = "auto"


def _require_number(data: dict[str, Any], key: str, section: str) -> float:
    value = _require_key(data, key, section)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"'{section}.{key}' must be a number, got {value!r}")
    return float(value)


def _require_processes(data: dict[str, Any]) -> int | None:
    """Return the worker count, or None for `auto`."""
    value = _require_key(data, "processes", "sweep")
    if value == SWEEP_PROCESSES_AUTO:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"'sweep.processes' must be an integer >= 1 or '{SWEEP_PROCESSES_AUTO}', got {value!r}")
    return value


def _require_gantt_compare(
    data: dict[str, Any], vary: tuple[tuple[str, tuple[Any, ...]], ...]
) -> tuple[str, tuple[Any, ...]] | None:
    """Return (vary key, values to put side by side), or None for `{}`."""
    compare = _require_mapping(_require_key(data, "gantt_compare", "sweep"), "sweep.gantt_compare")
    if not compare:
        return None
    if len(compare) != 1:
        raise ConfigError(f"'sweep.gantt_compare' takes one vary key, got {', '.join(map(str, compare))}")
    key, values = next(iter(compare.items()))
    vary_values = dict(vary).get(key)
    if vary_values is None:
        raise ConfigError(f"'sweep.gantt_compare' key {key!r} must be one of the 'sweep.vary' keys")
    if not isinstance(values, list) or not 2 <= len(values) <= GANTT_MAX_PANELS:
        raise ConfigError(f"'sweep.gantt_compare.{key}' must list 2 to {GANTT_MAX_PANELS} values, got {values!r}")
    missing = [v for v in values if v not in vary_values]
    if missing:
        raise ConfigError(f"'sweep.gantt_compare.{key}' values {missing!r} are not in 'sweep.vary.{key}'")
    return key, tuple(values)


@dataclass(frozen=True)
class SweepSpec:
    """The `sweep:` section of an experiment file, the only interface for a sweep.

    `vary` maps a dotted config key to the list of values to try; the sweep runs
    every combination. Every other key is required too.
    """

    vary: tuple[tuple[str, tuple[Any, ...]], ...]
    summary_out: str
    visualize_summary: bool
    plot_ring_heatmaps: bool
    # Lower part (in percent) of the training-step-time range shown in the extra zoomed plot; 0 skips that plot.
    lower_zoom_percent: float
    stop_on_error: bool
    # None means `auto`.
    max_processes: int | None
    plot_topology_once: bool
    show_visualization_window: bool
    # Paper look (no title, white background, 6 x 3.6 in, 9 pt) for the training-step-time,
    # best-redundancy and slowdown-heatmap plots.
    paper_style: bool
    # Gantt PDFs of sample training steps (first, middle, slowest) of every run, made without the web app.
    gantt_pdfs: bool
    gantt_chain_limit: int
    # (vary key, values): also put the runs that differ only in this key side by side. None = no comparisons.
    gantt_compare: tuple[str, tuple[Any, ...]] | None

    @staticmethod
    def from_mapping(value: Any) -> "SweepSpec":
        data = _require_mapping(value, "sweep")
        reject_unknown_keys(data, _SWEEP_KEYS, "sweep")

        vary_map = _require_mapping(_require_key(data, "vary", "sweep"), "sweep.vary")
        if not vary_map:
            raise ConfigError("'sweep.vary' must list at least one key to vary")
        vary: list[tuple[str, tuple[Any, ...]]] = []
        for key, values in vary_map.items():
            if not isinstance(key, str) or not key.strip():
                raise ConfigError(f"Invalid key in 'sweep.vary': {key!r}")
            if not isinstance(values, list) or not values:
                raise ConfigError(f"'sweep.vary.{key}' must be a non-empty list of values")
            for v in values:
                if not isinstance(v, _SCALAR_TYPES):
                    raise ConfigError(f"'sweep.vary.{key}' values must be plain scalars, got {v!r}")
            vary.append((key.strip(), tuple(values)))

        lower_zoom_percent = _require_number(data, "lower_zoom_percent", "sweep")
        if not 0.0 <= lower_zoom_percent <= 100.0:
            raise ConfigError(f"'sweep.lower_zoom_percent' must be between 0 and 100, got {lower_zoom_percent!r}")

        gantt_chain_limit = _require_key(data, "gantt_chain_limit", "sweep")
        if isinstance(gantt_chain_limit, bool) or not isinstance(gantt_chain_limit, int) or gantt_chain_limit < 1:
            raise ConfigError(f"'sweep.gantt_chain_limit' must be an integer >= 1, got {gantt_chain_limit!r}")

        return SweepSpec(
            vary=tuple(vary),
            summary_out=_require_str(data, "summary_out", "sweep", allow_empty=False),
            visualize_summary=bool(_require_key(data, "visualize_summary", "sweep")),
            plot_ring_heatmaps=bool(_require_key(data, "plot_ring_heatmaps", "sweep")),
            lower_zoom_percent=lower_zoom_percent,
            stop_on_error=bool(_require_key(data, "stop_on_error", "sweep")),
            max_processes=_require_processes(data),
            plot_topology_once=bool(_require_key(data, "plot_topology_once", "sweep")),
            show_visualization_window=bool(_require_key(data, "show_visualization_window", "sweep")),
            paper_style=bool(_require_key(data, "paper_style", "sweep")),
            gantt_pdfs=bool(_require_key(data, "gantt_pdfs", "sweep")),
            gantt_chain_limit=gantt_chain_limit,
            gantt_compare=_require_gantt_compare(data, tuple(vary)),
        )

    def combination_count(self) -> int:
        count = 1
        for _, values in self.vary:
            count *= len(values)
        return count



