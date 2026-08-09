"""RawEvent / SimBeat / ResponseCommand / Simulator structural tests (docs/06 Â§1)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import pytest
from pydantic import ValidationError

from cybersim.simulation.base import (
    RawEvent,
    ResponseCommand,
    SimBeat,
    Simulator,
)
from cybersim.simulation.core.clock import SimClock
from cybersim.simulation.core.context import SimContext
from cybersim.simulation.core.rng import SeededRNG


def _ctx() -> SimContext:
    return SimContext(
        org_id="org_demo",
        simulation_id="01J9Y",
        scenario_id="web.app.sqli_login",
        seed=7,
        clock=SimClock(duration_ms=1_000),
        rng=SeededRNG(7),
    )


def test_raw_event_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RawEvent(
            id="r-1",
            sim_time_ms=0,
            origin="web",
            type="http.request",
            payload={},
            unexpected="bad",
        )


def test_raw_event_requires_origin_and_type() -> None:
    with pytest.raises(ValidationError):
        RawEvent(id="r-1", sim_time_ms=0, origin="web", type="")  # type: ignore[arg-type]


def test_sim_beat_is_frozen() -> None:
    beat = SimBeat(sim_time_ms=0, events=[])
    with pytest.raises(ValidationError):
        beat.sim_time_ms = 1  # type: ignore[misc]


def test_response_command_defaults() -> None:
    cmd = ResponseCommand(action_id="block_source_ip")
    assert cmd.action_id == "block_source_ip"
    assert cmd.params == {}
    assert cmd.requested_at_ms is None


def test_simulator_protocol_is_runtime_checkable() -> None:
    class WebSim:
        id = "web"

        def init(self, ctx: SimContext) -> None: ...

        def beats(self, ctx: SimContext) -> Iterator[SimBeat]:
            yield SimBeat(sim_time_ms=0, events=[])

        def apply_command(self, cmd: ResponseCommand, ctx: SimContext) -> list[RawEvent]:
            return []

    sim = cast(Simulator, WebSim())
    assert isinstance(sim, Simulator)
    # structural protocol passes with no instances of explicit Simulator parent


def test_sim_context_params_mutable_in_place() -> None:
    ctx = _ctx()
    ctx.with_param("request_rate_per_sec", 4)
    assert ctx.params["request_rate_per_sec"] == 4
