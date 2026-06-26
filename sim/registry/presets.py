from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..config.models import ConfigError


_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PresetRegistryItem:
    name: str
    description: str
    file_path: Path


_REGISTRY: dict[str, PresetRegistryItem] = {
    "ai/dp-low-small": PresetRegistryItem(
        name="ai/dp-low-small",
        description="AI scale-unit (SU) DP-heavy smaller topology, low-load preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "dp_low_small.yaml",
    ),
    "ai/dp-tiny": PresetRegistryItem(
        name="ai/dp-tiny",
        description="AI scale-unit (SU) DP-heavy smaller topology, smallest preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "dp_tiny.yaml",
    ),
    "ai/dp-single-ring": PresetRegistryItem(
        name="ai/dp-single-ring",
        description="AI scale-unit (SU) DP-heavy small-scale preset with reduce-scatter only (single ring)",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "dp_single_ring.yaml",
    ),
    "ai/mixed-light": PresetRegistryItem(
        name="ai/mixed-light",
        description="AI scale-unit (SU) mixed lightweight preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "mixed_light.yaml",
    ),
}

_ALIASES: dict[str, str] = {
    "ai/su-dp-low-small": "ai/dp-low-small",
    "ai/su-dp-tiny": "ai/dp-tiny",
    "ai/su-dp-single-ring": "ai/dp-single-ring",
    "ai/su-mixed-light": "ai/mixed-light",
}


def iter_preset_items() -> Iterable[PresetRegistryItem]:
    return (_REGISTRY[name] for name in sorted(_REGISTRY))



def get_preset_item(name: str) -> PresetRegistryItem:
    key = str(name).strip().lower()
    key = _ALIASES.get(key, key)
    item = _REGISTRY.get(key)
    if item is None:
        valid = ", ".join(sorted(set(_REGISTRY) | set(_ALIASES)))
        raise ConfigError(f"Unknown preset '{name}'. Valid: {valid}")
    return item

