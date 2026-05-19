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
    "ai/su-dp-light": PresetRegistryItem(
        name="ai/su-dp-light",
        description="AI scale-unit (SU) DP-heavy lightweight preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "dp_light.yaml",
    ),
    "ai/su-dp-low": PresetRegistryItem(
        name="ai/su-dp-low",
        description="AI scale-unit (SU) DP-heavy low-load preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "dp_low.yaml",
    ),
    "ai/su-dp-mid": PresetRegistryItem(
        name="ai/su-dp-mid",
        description="AI scale-unit (SU) DP-heavy medium-load preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "dp_mid.yaml",
    ),
    "ai/su-dp-high": PresetRegistryItem(
        name="ai/su-dp-high",
        description="AI scale-unit (SU) DP-heavy high-load preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "dp_high.yaml",
    ),
    "ai/su-mixed-light": PresetRegistryItem(
        name="ai/su-mixed-light",
        description="AI scale-unit (SU) mixed lightweight preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "mixed_light.yaml",
    ),
    "ai/su-mixed-low": PresetRegistryItem(
        name="ai/su-mixed-low",
        description="AI scale-unit (SU) mixed low-load preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "mixed_low.yaml",
    ),
    "ai/su-mixed-mid": PresetRegistryItem(
        name="ai/su-mixed-mid",
        description="AI scale-unit (SU) mixed medium-load preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "mixed_mid.yaml",
    ),
    "ai/su-mixed-high": PresetRegistryItem(
        name="ai/su-mixed-high",
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

