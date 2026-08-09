"""SimContext — per-run simulator parameters (docs/06 §1.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cybersim.simulation.core.clock import SimClock
from cybersim.simulation.core.rng import SeededRNG


@dataclass
class SimContext:
    """Inputs to a `Simulator.init`/`beats`/`apply_command` invocation.

    `clock`, `rng`, and `org_id` are bound per simulation instance so simulator
    code is deterministic by construction. `params` is intentionally `dict[str, Any]`:
    scenarios declare per-simulator parameters (see docs/06 §2) which the
    normalizer & analyst treat as a structurally-typed payload checked via
    Pydantic where needed.
    """

    org_id: str
    simulation_id: str
    scenario_id: str
    seed: int
    clock: SimClock
    rng: SeededRNG
    params: dict[str, Any] = field(default_factory=dict)

    def with_param(self, key: str, value: Any) -> None:
        """Set a parameter (post-construction tuning). Mutates in place."""
        self.params[key] = value
