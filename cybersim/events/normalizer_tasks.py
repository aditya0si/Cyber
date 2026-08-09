"""Normalizer async-consumer entrypoint (docs/03 §6.3, docs/07 §4).

Phase 3 ships the consumer loop that wires the `Normalizer` to the EventBus:
subscribes to the raw stream, applies graph mutations per normalized event,
and publishes CanonicalEvents on the canonical stream. Persistence lives in
`GraphDAL` + the Postgres `events` table (Phase 9 wires real DB writes; in MVP
the in-memory pipeline uses an `InMemoryEventBus` and an in-memory store).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from cybersim.events.bus import EventBus
from cybersim.events.normalizer import Normalizer
from cybersim.events.schema import CanonicalEvent
from cybersim.graph.repo_nx import NetworkXGraphRepository
from cybersim.graph.types import FootholdState

log = logging.getLogger(__name__)


@dataclass
class NormalizedSink:
    """In-memory accumulation of canonical events (used by tests)."""

    events: list[CanonicalEvent] = field(default_factory=list)

    def add(self, ev: CanonicalEvent) -> None:
        self.events.append(ev)


class NormalizerConsumer:
    """Wires EventBus → Normalizer → CanonicalEvent publisher (docs/07 §4).

    Phase 3 MVP uses an in-memory EventBus + NetworkX repo. Phase 9 swaps the
    bus for Redis Streams and adds PG-backed persistence — both behind the
    EventBus / GraphRepository interfaces so the consumer remains unchanged.
    """

    def __init__(
        self,
        bus: EventBus,
        graph_repo: NetworkXGraphRepository,
        env_graph_lookup: Any,
        sink: NormalizedSink | None = None,
    ) -> None:
        """`env_graph_lookup(sim_id) -> EnvironmentGraph` is provided by the caller.

        The Normalizer needs the env graph to resolve node refs; we don't bake
        that into the repo because it can evolve across sims.
        """
        self._bus = bus
        self._graph_repo = graph_repo
        self._env_lookup = env_graph_lookup
        self._normalizer = Normalizer()
        self._sink = sink or NormalizedSink()
        self._running = False

    @property
    def normalized(self) -> list[CanonicalEvent]:
        return list(self._sink.events)

    @property
    def normalizer(self) -> Normalizer:
        return self._normalizer

    def reset(self) -> None:
        self._normalizer.reset()
        self._sink.events.clear()

    async def consume_once(self, org_id: str, sim_id: str) -> int:
        """Pull ONE available raw event off the bus and normalize it.

        Returns 0 if no event was ready, 1 if one was normalized.
        """
        gen = self._bus.raw_stream(org_id, sim_id)
        ev = await gen.__anext__()
        env_graph = self._env_lookup(sim_id)
        ce = self._normalizer.normalize(
            ev,
            org_id=org_id,
            simulation_id=sim_id,
            env=env_graph,
            received_at_ms=ev.sim_time_ms,
        )
        if ce is None:
            return 0
        # Stateful foothold transition (M1 minimal semantic)
        self._maybe_update_foothold(ce, sim_id)
        self._sink.add(ce)
        if await self._bus.publish_canonical(ce):
            return 1
        return 0

    def _maybe_update_foothold(self, ce: CanonicalEvent, sim_id: str) -> None:
        """Promote foothold state based on the normalized event's severity/stage."""
        if ce.attack_stage is None or ce.benign:
            return
        # Promote only the primary target (first) so test replay stays minimal.
        for nid in ce.target_node_ids:
            try:
                current = self._graph_repo.get_node(sim_id, nid)
            except KeyError:
                current = None
            if current is None:
                continue
            new_state: FootholdState | None = None
            stage = ce.attack_stage
            if stage == "initial_access":
                new_state = FootholdState.ATTEMPTED
            elif stage == "credential_access":
                new_state = FootholdState.FOOTHOLD
            elif stage == "exfiltration":
                new_state = FootholdState.COMPROMISED
            if new_state is not None and current.foothold_state != new_state:
                self._graph_repo.update_foothold(sim_id, nid, new_state)

    async def drain(self, org_id: str, sim_id: str, max_events: int = 2000) -> int:
        """Drain up to `max_events` raw events; tests use this synchronously.

        Drains the entire in-memory buffer when the InMemoryEventBus is used;
        for Redis, use `consume_loop` which polls with backpressure.
        """
        n = 0
        while n < max_events:
            try:
                one = await asyncio.wait_for(self.consume_once(org_id, sim_id), timeout=0.05)
            except TimeoutError:
                break
            n += one
        return n


__all__ = ["NormalizedSink", "NormalizerConsumer"]
