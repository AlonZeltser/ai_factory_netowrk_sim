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
     "ai/dp-single-bucket": PresetRegistryItem(
        name="ai/dp-single-bucket",
        description="AI scale-unit (SU) DP-heavy small-scale preset with reduce-scatter only (single ring)",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "dp_single_bucket.yaml",
    ),
    "ai/mixed-light": PresetRegistryItem(
        name="ai/mixed-light",
        description="AI scale-unit (SU) mixed lightweight preset on the unified clos family",
        file_path=_REPO_ROOT / "sim" / "presets" / "ai" / "mixed_light.yaml",
    ),
}

def iter_preset_items() -> Iterable[PresetRegistryItem]:
    return (_REGISTRY[name] for name in sorted(_REGISTRY))



def get_preset_item(name: str) -> PresetRegistryItem:
    key = str(name).strip().lower()
    item = _REGISTRY.get(key)
    if item is None:
        raise ConfigError(f"Unknown preset '{name}'. Valid presets are: {', '.join(sorted(_REGISTRY))}")
    return item

