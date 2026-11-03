from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from network.core.network import Network


class Scenario(ABC):
    """A traffic/workload definition.

    A Scenario must not create or connect topology objects. It should only schedule events
    and send traffic using the entities created by a topology builder.

    Contract:
      - `install(network)` may call `network.get_entity(...)` / access `network.hosts`, etc.
      - It may schedule events on `network.simulator`.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Scenario name reported as `scenario` in the parameters summary."""
        raise NotImplementedError

    @abstractmethod
    def install(self, creator: Network) -> None:
        raise NotImplementedError

    def parameters_summary(self) -> Dict[str, Any]:
        return {"scenario": self.name}


