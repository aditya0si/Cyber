"""Redis Streams-backed EventBus (docs/03 Â§6.2, docs/07 Â§4).

In Phase 1 we ship the implementation so dev can use a real bus, but unit
tests rely on the in-memory impl. Phase 3 wires this to the actual worker
pipeline. Two streams per sim:
    events.raw.<org>.<sim>
    canonical.events.<org>.<sim>

Idempotency: consumer dedups by event `id` before processing; the publisher
also short-circuits via Redis SETNX on `dedup:<raw_id>` for the in-stream id,
giving effectively-once semantics on top of at-least-once delivery.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis

from cybersim.events.schema import CanonicalEvent
from cybersim.simulation.base import RawEvent


def raw_stream_name(org_id: str, sim_id: str) -> str:
    return f"events.raw.{org_id}.{sim_id}"


def canonical_stream_name(org_id: str, sim_id: str) -> str:
    return f"canonical.events.{org_id}.{sim_id}"


def _raw_to_dict(event: RawEvent) -> dict[str, str]:
    return {
        "id": event.id,
        "sim_time_ms": str(event.sim_time_ms),
        "origin": event.origin,
        "type": event.type,
        "node_ref": event.node_ref or "",
        "src_ip": event.src_ip or "",
        "benign": "1" if event.benign else "",
        "payload": json.dumps(event.payload, default=str),
    }


def _dict_to_raw(data: dict[str, Any]) -> RawEvent:
    payload_field = data.get("payload", "")
    if isinstance(payload_field, str) and payload_field:
        payload = json.loads(payload_field)
    else:
        payload = payload_field or {}
    return RawEvent(
        id=data["id"],
        sim_time_ms=int(data["sim_time_ms"]),
        origin=data["origin"],
        type=data["type"],
        node_ref=data.get("node_ref") or None,
        src_ip=data.get("src_ip") or None,
        benign=bool(data.get("benign")),
        payload=payload,
    )


def _canonical_to_dict(ev: CanonicalEvent) -> dict[str, str]:
    return {
        "event_id": ev.event_id,
        "timestamp": ev.timestamp,
        "event_type": ev.event_type,
        "severity": ev.severity,
        "source_ip": ev.source_ip,
        "target_asset": ev.target_asset,
        "actor": ev.actor,
        "raw_context": json.dumps(ev.raw_context, default=str),
    }


def _dict_to_canonical(data: dict[str, Any]) -> CanonicalEvent:
    raw_context_field = data.get("raw_context", "{}")
    if isinstance(raw_context_field, str) and raw_context_field:
        raw_context = json.loads(raw_context_field)
    else:
        raw_context = raw_context_field or {}

    return CanonicalEvent(
        event_id=data["event_id"],
        timestamp=data["timestamp"],
        event_type=data["event_type"],
        severity=data["severity"],
        source_ip=data["source_ip"],
        target_asset=data["target_asset"],
        actor=data["actor"],
        raw_context=raw_context,
    )


class RedisEventBus:
    """Redis Streams-backed EventBus (Phase 1 functional surface, Phase 3 wired)."""

    def __init__(self, redis: Redis[Any]) -> None:
        self._redis = redis

    async def publish_raw(self, event: RawEvent, org_id: str, sim_id: str) -> bool:
        dedup_key = f"dedup.raw.{event.id}"
        if not await self._redis.set(dedup_key, "1", ex=86400, nx=True):
            return False  # already published (idempotent dedup)
        stream = raw_stream_name(org_id, sim_id)
        await self._redis.xadd(stream, _raw_to_dict(event))
        return True

    async def raw_stream(
        self,
        org_id: str,
        sim_id: str,
        group: str = "normalizer",
        consumer: str = "c1",
        block_ms: int = 2000,
    ) -> AsyncIterator[RawEvent]:
        stream = raw_stream_name(org_id, sim_id)
        with contextlib.suppress(Exception):
            await self._redis.xgroup_create(stream, group, id="0", mkstream=True)
        while True:
            response = await self._redis.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={stream: ">"},
                count=8,
                block=2000,
            )
            if not response:
                continue
            for _stream_name, entries in response:
                for _msg_id, fields in entries:
                    yield _dict_to_raw(fields)

    async def ack_raw(self, org_id: str, sim_id: str, ref: str, group: str = "normalizer") -> None:
        await self._redis.xack(raw_stream_name(org_id, sim_id), group, ref)  # type: ignore[no-untyped-call]

    async def publish_canonical(self, ev: CanonicalEvent, org_id: str, sim_id: str) -> bool:
        dedup_key = f"dedup.canonical.{ev.event_id}"
        if not await self._redis.set(dedup_key, "1", ex=86400, nx=True):
            return False
        stream = canonical_stream_name(org_id, sim_id)
        await self._redis.xadd(stream, _canonical_to_dict(ev))
        return True

    async def canonical_stream(
        self,
        org_id: str,
        sim_id: str,
        group: str = "analyst",
        consumer: str = "a1",
        block_ms: int = 2000,
    ) -> AsyncIterator[CanonicalEvent]:
        stream = canonical_stream_name(org_id, sim_id)
        with contextlib.suppress(Exception):
            await self._redis.xgroup_create(stream, group, id="0", mkstream=True)
        while True:
            response = await self._redis.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={stream: ">"},
                count=8,
                block=2000,
            )
            if not response:
                continue
            for _stream_name, entries in response:
                for _msg_id, fields in entries:
                    yield _dict_to_canonical(fields)
