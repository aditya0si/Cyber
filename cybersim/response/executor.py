"""Response executor — validated application of recommended actions (docs/03 §8.1).

The executor NEVER trusts the analyst: every action_id must exist in the
per-simulator whitelist, and mutating commands are applied to the simulator
instance held by the sim store, emitting `response.applied` events.
"""

from __future__ import annotations

from typing import Any

from cybersim.analyst.response_catalog import allowed_actions
from cybersim.infra.errors import AppError, ErrorCode
from cybersim.simulation.base import RawEvent, ResponseCommand
from cybersim.simulation.core.context import SimContext


class ResponseExecutor:
    """Apply a validated response action against a running simulation."""

    def __init__(self, simulator_id: str) -> None:
        self.simulator_id = simulator_id

    def check_allowed(self, action_id: str) -> None:
        """Raise AppError(ACTION_NOT_ALLOWED) if `action_id` isn't whitelisted."""
        if action_id not in allowed_actions(self.simulator_id):
            raise AppError(
                ErrorCode.ACTION_NOT_ALLOWED,
                f"action {action_id!r} is not in the allowed catalog for "
                f"simulator {self.simulator_id!r}",
            )

    def execute(
        self,
        simulator: Any,
        ctx: SimContext,
        action_id: str,
        params: dict[str, Any] | None = None,
    ) -> list[RawEvent]:
        """Apply the command to `simulator`; returns emitted RawEvents.

        `simulator` is the live `Simulator` instance (WebSimulator etc.),
        which already holds post-init state.
        """
        self.check_allowed(action_id)
        cmd = ResponseCommand(action_id=action_id, params=params or {})
        events = simulator.apply_command(cmd, ctx)
        return list(events)
