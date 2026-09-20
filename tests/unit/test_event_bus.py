"""InMemoryEventBus round-trip + idempotent dedup (docs/07 §4)."""

from __future__ import annotations

import pytest

from cybersim.events.bus import InMemoryEventBus
from cybersim.events.schema import CanonicalEvent
from cybersim.simulation.base import RawEvent

# ---------- Raw event round-trip ----------


def _raw(event_id: str, origin: str = "web", rtype: str = "http.request") -> RawEvent:
    return RawEvent(
        id=event_id,
        sim_time_ms=0,
        origin=origin,
        type=rtype,
        payload={},
    )


@pytest.mark.asyncio
async def test_publish_raw_returns_true_on_new_id() -> None:
    bus = InMemoryEventBus()
    pub = await bus.publish_raw(_raw("r-1"), "org_demo", "sim-1")
    assert pub is True
    assert bus.raw_history("org_demo", "sim-1") == [_raw("r-1")]


@pytest.mark.asyncio
async def test_publish_raw_dedup_on_same_id() -> None:
    bus = InMemoryEventBus()
    assert await bus.publish_raw(_raw("r-1"), "org_demo", "sim-1")
    assert not await bus.publish_raw(_raw("r-1"), "org_demo", "sim-1")
    # history kept insertion order w/ only one entry
    assert len(bus.raw_history("org_demo", "sim-1")) == 1


@pytest.mark.asyncio
async def test_publish_raw_independent_per_sim_stream() -> None:
    bus = InMemoryEventBus()
    # same id can coexist across two sims because streams are separate
    assert await bus.publish_raw(_raw("r-x"), "org_demo", "sim-A")
    assert await bus.publish_raw(_raw("r-x"), "org_demo", "sim-B")
    assert len(bus.raw_history("org_demo", "sim-A")) == 1
    assert len(bus.raw_history("org_demo", "sim-B")) == 1


@pytest.mark.asyncio
async def test_raw_stream_consumes_in_order() -> None:
    bus = InMemoryEventBus()
    for i in range(3):
        await bus.publish_raw(_raw(f"r-{i}"), "org_demo", "sim-2")
    seen: list[str] = []
    gen = bus.raw_stream("org_demo", "sim-2")
    for _ in range(3):
        ev = await gen.__anext__()
        seen.append(ev.id)
    assert seen == ["r-0", "r-1", "r-2"]


@pytest.mark.asyncio
async def test_ack_raw_is_a_noop() -> None:
    bus = InMemoryEventBus()
    await bus.publish_raw(_raw("r-1"), "org_demo", "sim-3")
    await bus.ack_raw("org_demo", "sim-3", "ref-arbitrary")
    # No assertion failure paths; just exercise the contract.


# ---------- Canonical event round-trip ----------


def _canonical(event_id: str) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        timestamp="2026-08-09T00:00:00Z",
        event_type="LOGIN_FAILED",
        severity="MEDIUM",
        source_ip="192.168.1.5",
        target_asset="auth-api",
        actor="unknown",
        raw_context={},
    )


@pytest.mark.asyncio
async def test_publish_canonical_returns_true_on_new() -> None:
    bus = InMemoryEventBus()
    assert await bus.publish_canonical(_canonical("c-1"), "org_demo", "sim-c")
    assert len(bus.canonical_history("org_demo", "sim-c")) == 1


@pytest.mark.asyncio
async def test_publish_canonical_dedup() -> None:
    bus = InMemoryEventBus()
    assert await bus.publish_canonical(_canonical("c-1"), "org_demo", "sim-c")
    assert not await bus.publish_canonical(_canonical("c-1"), "org_demo", "sim-c")
    assert len(bus.canonical_history("org_demo", "sim-c")) == 1


@pytest.mark.asyncio
async def test_canonical_stream_consumes_in_order() -> None:
    bus = InMemoryEventBus()
    for i in range(2):
        await bus.publish_canonical(_canonical(f"c-{i}"), "org_demo", "sim-c")
    seen: list[str] = []
    gen = bus.canonical_stream("org_demo", "sim-c")
    for _ in range(2):
        ev = await gen.__anext__()
        seen.append(ev.event_id)
    assert seen == ["c-0", "c-1"]


@pytest.mark.asyncio
async def test_reset_drops_state() -> None:
    bus = InMemoryEventBus()
    await bus.publish_raw(_raw("r-1"), "org_demo", "sim-X")
    bus.reset()
    assert bus.raw_history("org_demo", "sim-X") == []
