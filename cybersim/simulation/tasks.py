"""Simulation worker entrypoint (docs/03 §4, docs/21 Task 2.2).

Phase 2 ships the Celery task wrapper that:
  1. Loads the scenario from the catalog
  2. Instantiates the simulator (web/api/network/supply) by `scenario.simulator`
  3. Runs `init` + iterates `beats`, publishing each RawEvent to the EventBus
  4. Reacts to response commands pulled from a Redis list (`commands.<sim_id>`)

The task function calls into the EventBus (in-memory or Redis-backed) but does
not own persistence — the Normalizer consumer (Phase 3) handles canonicalization.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from cybersim.simulation.base import RawEvent, SimBeat, Simulator
from cybersim.simulation.catalog import get_scenario
from cybersim.simulation.core.clock import SimClock
from cybersim.simulation.core.context import SimContext
from cybersim.simulation.core.rng import SeededRNG

log = logging.getLogger(__name__)

_SIM_REGISTRY: dict[str, type[Any]] = {}


def register_simulator(simulator: type[Any]) -> type[Any]:
    """Decorator for `Simulator` impls that should be discoverable on the worker."""
    if not hasattr(simulator, "id"):
        raise TypeError(f"{simulator!r} missing .id attribute")
    _SIM_REGISTRY[simulator.id] = simulator
    return simulator


def get_simulator_class(simulator_id: str) -> type[Any]:
    """Look up a registered Simulator implementation by its id slug."""
    if simulator_id not in _SIM_REGISTRY:
        # Lazy-load default impls
        if simulator_id == "web":
            from cybersim.simulation.web.simulator import WebSimulator

            register_simulator(WebSimulator)
        elif simulator_id == "api":
            from cybersim.simulation.api.simulator import APISimulator

            register_simulator(APISimulator)
        elif simulator_id == "network":
            from cybersim.simulation.network.simulator import NetworkSimulator

            register_simulator(NetworkSimulator)
        elif simulator_id == "supply":
            from cybersim.simulation.supply.simulator import SupplyChainSimulator

            register_simulator(SupplyChainSimulator)
    if simulator_id not in _SIM_REGISTRY:
        raise KeyError(f"no simulator registered for id={simulator_id!r}")
    return _SIM_REGISTRY[simulator_id]


def build_context(
    org_id: str,
    simulation_id: str,
    scenario_id: str,
    seed: int,
    params: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> SimContext:
    """Build a deterministic `SimContext` for a given scenario + seed."""
    from cybersim.simulation.catalog import scenario_params

    if duration_ms is None:
        duration_ms = get_scenario(scenario_id).display.duration_sec * 1000
    return SimContext(
        org_id=org_id,
        simulation_id=simulation_id,
        scenario_id=scenario_id,
        seed=seed,
        clock=SimClock(duration_ms=duration_ms),
        rng=SeededRNG(seed),
        params=scenario_params(scenario_id, override=params or {}),
    )


def run_simulator_in_memory(
    org_id: str,
    simulation_id: str,
    scenario_id: str,
    seed: int = 7,
    params: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> tuple[Simulator, list[RawEvent], SimContext]:
    """Helper used by tests: drive the simulator and collect all raw events.

    Returns `(simulator, events, ctx)`. The simulator instance retains mutated
    state so callers can verify `apply_command` effects.
    """
    ctx = build_context(
        org_id=org_id,
        simulation_id=simulation_id,
        scenario_id=scenario_id,
        seed=seed,
        params=params,
        duration_ms=duration_ms,
    )
    simulator_class = get_simulator_class(get_scenario(scenario_id).simulator)
    sim: Simulator = simulator_class()
    sim.init(ctx)
    events: list[RawEvent] = []
    beats: Iterator[SimBeat] = sim.beats(ctx)
    for beat in beats:
        for ev in beat.events:
            events.append(ev)
            ctx.clock.advance(1)  # advance clock 1ms between events
    return sim, events, ctx


async def run_simulation_async(
    bus: Any,
    org_id: str,
    simulation_id: str,
    scenario_id: str,
    seed: int = 7,
    params: dict[str, Any] | None = None,
) -> int:
    """Publish raw events from a simulator's beats to `bus`.

    The function is awaited from the Celery task; in MVP we bound concurrency
    via the worker count, so each task is single-event-loop. Returns the total
    number of events published (post-dedup).
    """
    ctx = build_context(
        org_id=org_id,
        simulation_id=simulation_id,
        scenario_id=scenario_id,
        seed=seed,
        params=params,
    )
    sim = get_simulator_class(get_scenario(scenario_id).simulator)()
    sim.init(ctx)
    published = 0
    for beat in sim.beats(ctx):
        for ev in beat.events:
            ctx.clock.set_to(beat.sim_time_ms)
            ok = await bus.publish_raw(ev, org_id, simulation_id)
            if ok:
                published += 1
    return published


# NOTE: A real Celery task is wired here once Phase 4 ships JWT-validated start
# endpoints; Phase 2's tests call `run_simulator_in_memory` directly.


__all__ = [
    "build_context",
    "get_simulator_class",
    "register_simulator",
    "run_simulation_async",
    "run_simulator_in_memory",
]
