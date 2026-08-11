"""EventBus â€” the producer/consumer seam (docs/03 Â§6.2, docs/07 Â§4).

Phase 1 ships:
  - the `EventBus` Protocol (the implicit swap-out seam for Redisâ†”Kafka)
  - the `InMemoryEventBus` implementation for tests + dev (no I/O)

Phase 3 ships the Redis Streams-backed implementation (`events/bus_redis.py`),
behind the same Protocol.

Per-sim streams use deterministic names:
  raw:       events.raw.<org>.<sim>
  canonical: canonical.events.<org>.<sim>

Dedup is on `event.id` / `event_id`: at-least-once transport + consumer-side
idempotency gives effectively-once semantics (docs/07 Â§4.1).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol

from cybersim.events.schema import CanonicalEvent
from cybersim.simulation.base import RawEvent


def raw_stream_name(org_id: str, sim_id: str) -> str:
    return f"events.raw.{org_id}.{sim_id}"


def canonical_stream_name(org_id: str, sim_id: str) -> str:
    return f"canonical.events.{org_id}.{sim_id}"


@dataclass
class _StreamBuffer:
    raw_ids: set[str] = field(default_factory=set)
    raw_queue: asyncio.Queue[RawEvent] = field(default_factory=asyncio.Queue)
    raw_list: list[RawEvent] = field(default_factory=list)
    canonical_ids: set[str] = field(default_factory=set)
    canonical_queue: asyncio.Queue[CanonicalEvent] = field(default_factory=asyncio.Queue)
    canonical_list: list[CanonicalEvent] = field(default_factory=list)


class EventBus(Protocol):
    """The producer (simulator) / consumer (normalizer) contract.

    Implementations MUST guarantee:
      * Per-stream FIFO order (consumer sees insertion order).
      * At-least-once delivery; consumers dedup on `event_id` (`docs/07 Â§4.1`).
      * `publish_*` is non-blocking; returns False if deduped.
    """

    async def publish_raw(self, event: RawEvent, org_id: str, sim_id: str) -> bool: ...

    def raw_stream(self, org_id: str, sim_id: str) -> AsyncIterator[RawEvent]: ...

    async def ack_raw(self, org_id: str, sim_id: str, ref: str) -> None: ...

    async def publish_canonical(self, event: CanonicalEvent, org_id: str, sim_id: str) -> bool: ...

    def canonical_stream(self, org_id: str, sim_id: str) -> AsyncIterator[CanonicalEvent]: ...


class InMemoryEventBus:
    """In-process EventBus impl (tests + dev).

    Synchronous in-process; FIFO via per-stream asyncio.Queue; dedup via the
    `_StreamBuffer.*_ids` sets. The *_list fields preserve the *complete* ordered
    history so replay tests can assert against it without a live consumer loop.
    """

    def __init__(self) -> None:
        self._buffers: dict[str, _StreamBuffer] = {}

    def _raw_buffer(self, org_id: str, sim_id: str) -> _StreamBuffer:
        return self._buffers.setdefault(raw_stream_name(org_id, sim_id), _StreamBuffer())

    def _canonical_buffer(self, org_id: str, sim_id: str) -> _StreamBuffer:
        return self._buffers.setdefault(canonical_stream_name(org_id, sim_id), _StreamBuffer())

    async def publish_raw(self, event: RawEvent, org_id: str, sim_id: str) -> bool:
        buf = self._raw_buffer(org_id, sim_id)
        if event.id in buf.raw_ids:
            return False
        buf.raw_ids.add(event.id)
        buf.raw_list.append(event)
        await buf.raw_queue.put(event)
        return True

    def raw_stream(self, org_id: str, sim_id: str) -> AsyncIterator[RawEvent]:
        return self._raw_iterator(org_id, sim_id)

    async def _raw_iterator(self, org_id: str, sim_id: str) -> AsyncIterator[RawEvent]:
        buf = self._raw_buffer(org_id, sim_id)
        while True:
            ev = await buf.raw_queue.get()
            yield ev

    async def ack_raw(self, org_id: str, sim_id: str, ref: str) -> None:
        # In-process impl needs no acknowledgement beyond dedup memoization.
        return None

    async def publish_canonical(self, event: CanonicalEvent, org_id: str, sim_id: str) -> bool:
        buf = self._canonical_buffer(org_id, sim_id)
        if event.event_id in buf.canonical_ids:
            return False
        buf.canonical_ids.add(event.event_id)
        buf.canonical_list.append(event)
        await buf.canonical_queue.put(event)
        return True

    def canonical_stream(self, org_id: str, sim_id: str) -> AsyncIterator[CanonicalEvent]:
        return self._canonical_iterator(org_id, sim_id)

    async def _canonical_iterator(self, org_id: str, sim_id: str) -> AsyncIterator[CanonicalEvent]:
        buf = self._canonical_buffer(org_id, sim_id)
        while True:
            ev = await buf.canonical_queue.get()
            yield ev

    # ---- test helpers -------------------------------------------------------
    def raw_history(self, org_id: str, sim_id: str) -> list[RawEvent]:
        """Return the in-order insertion history (test assertions)."""
        return list(self._raw_buffer(org_id, sim_id).raw_list)

    def canonical_history(self, org_id: str, sim_id: str) -> list[CanonicalEvent]:
        return list(self._canonical_buffer(org_id, sim_id).canonical_list)

    def reset(self) -> None:
        """Drop all buffers (test isolation)."""
        self._buffers.clear()
