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
        "simulation_id": ev.simulation_id,
        "org_id": ev.org_id,
        "sequence": str(ev.sequence),
        "sim_time_ms": str(ev.sim_time_ms),
        "received_at_ms": str(ev.received_at_ms),
        "origin": ev.origin,
        "raw_type": ev.raw_type,
        "category": ev.category.value,
        "subtype": ev.subtype,
        "severity_hint": ev.severity_hint.value,
        "attack_stage": ev.attack_stage.value if ev.attack_stage else "",
        "target_node_ids": json.dumps(list(ev.target_node_ids)),
        "source_node_id": ev.source_node_id or "",
        "via_edge_ids": json.dumps(list(ev.via_edge_ids)),
        "mitre_tactics": json.dumps(list(ev.mitre_tactics)),
        "mitre_techniques": json.dumps(list(ev.mitre_techniques)),
        "owasp_refs": json.dumps(list(ev.owasp_refs)),
        "payload": json.dumps(ev.payload, default=str),
        "raw_ref": ev.raw_ref or "",
        "correlation_key": ev.correlation_key or "",
        "benign": "1" if ev.benign else "",
    }


def _dict_to_canonical(data: dict[str, Any]) -> CanonicalEvent:
    from cybersim.events.types import AttackStage, EventCategory, Severity

    payload_field = data.get("payload", "")
    if isinstance(payload_field, str) and payload_field:
        payload = json.loads(payload_field)
    else:
        payload = payload_field or {}

    attack_stage_field = data.get("attack_stage") or ""
    return CanonicalEvent(
        event_id=data["event_id"],
        simulation_id=data["simulation_id"],
        org_id=data["org_id"],
        sequence=int(data["sequence"]),
        sim_time_ms=int(data["sim_time_ms"]),
        received_at_ms=int(data["received_at_ms"]),
        origin=data["origin"],
        raw_type=data["raw_type"],
        category=EventCategory(data["category"]),
        subtype=data["subtype"],
        severity_hint=Severity(data["severity_hint"]),
        attack_stage=AttackStage(attack_stage_field) if attack_stage_field else None,
        target_node_ids=tuple(json.loads(data.get("target_node_ids", "[]"))),
        source_node_id=data.get("source_node_id") or None,
        via_edge_ids=tuple(json.loads(data.get("via_edge_ids", "[]"))),
        mitre_tactics=tuple(json.loads(data.get("mitre_tactics", "[]"))),
        mitre_techniques=tuple(json.loads(data.get("mitre_techniques", "[]"))),
        owasp_refs=tuple(json.loads(data.get("owasp_refs", "[]"))),
        payload=payload,
        raw_ref=data.get("raw_ref") or None,
        correlation_key=data.get("correlation_key") or None,
        benign=bool(data.get("benign")),
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

    async def publish_canonical(self, ev: CanonicalEvent) -> bool:
        dedup_key = f"dedup.canonical.{ev.event_id}"
        if not await self._redis.set(dedup_key, "1", ex=86400, nx=True):
            return False
        stream = canonical_stream_name(ev.org_id, ev.simulation_id)
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
