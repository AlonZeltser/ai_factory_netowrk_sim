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
    "ai/dp-light": PresetRegistryItem(
        name="ai/dp-light",
        description="AI scale-unit (SU) DP-heavy lightweight preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "dp_light.yaml",
    ),
    "ai/dp-low": PresetRegistryItem(
        name="ai/dp-low",
        description="AI scale-unit (SU) DP-heavy low-load preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "dp_low.yaml",
    ),
    "ai/dp-low-small": PresetRegistryItem(
        name="ai/dp-low-small",
        description="AI scale-unit (SU) DP-heavy smaller topology, low-load preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "dp_low_small.yaml",
    ),
    "ai/dp-mid": PresetRegistryItem(
        name="ai/dp-mid",
        description="AI scale-unit (SU) DP-heavy medium-load preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "dp_mid.yaml",
    ),
    "ai/dp-high": PresetRegistryItem(
        name="ai/dp-high",
        description="AI scale-unit (SU) DP-heavy high-load preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "dp_high.yaml",
    ),
    "ai/mixed-light": PresetRegistryItem(
        name="ai/mixed-light",
        description="AI scale-unit (SU) mixed lightweight preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "mixed_light.yaml",
    ),
    "ai/mixed-low": PresetRegistryItem(
        name="ai/mixed-low",
        description="AI scale-unit (SU) mixed low-load preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "mixed_low.yaml",
    ),
    "ai/mixed-mid": PresetRegistryItem(
        name="ai/mixed-mid",
        description="AI scale-unit (SU) mixed medium-load preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "mixed_mid.yaml",
    ),
    "ai/mixed-high": PresetRegistryItem(
        name="ai/mixed-high",
        description="AI scale-unit (SU) mixed high-load preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "mixed_high.yaml",
    ),
}


def iter_preset_items() -> Iterable[PresetRegistryItem]:
    return (_REGISTRY[name] for name in sorted(_REGISTRY))



def get_preset_item(name: str) -> PresetRegistryItem:
    key = str(name).strip()
    item = _REGISTRY.get(key)
    if item is None:
        valid = ", ".join(sorted(_REGISTRY))
        raise ConfigError(f"Unknown preset '{name}'. Valid: {valid}")
    return item

