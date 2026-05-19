"""Traffic scenarios.

Each scenario is responsible only for scheduling traffic/events on top of an already-built topology.
See `network.scenarios.base.Scenario`.
"""
from network.scenarios.base import Scenario
from .none_scenario import NoneScenario

__all__ = [
    "Scenario",
    "NoneScenario",
]


