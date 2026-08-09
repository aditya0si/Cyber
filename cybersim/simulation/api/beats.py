"""API simulator beats (docs/06 §4.3-§4.4). Deterministic via ctx.rng/clock."""

from __future__ import annotations

from collections.abc import Iterator

from cybersim.simulation.base import RawEvent, SimBeat
from cybersim.simulation.core.context import SimContext

ATTACKER_IP = "203.0.113.42"
BENIGN_IPS = ("198.51.100.40", "198.51.100.50")


def _id_resource_pool(ctx: SimContext) -> range:
    pool_size = int(ctx.params.get("id_resource_pool", 1000))
    return range(1000, 1000 + pool_size)


def _benign_api_beats(ctx: SimContext) -> Iterator[SimBeat]:
    """Legitimate API traffic (low volume, random non-sequential object ids)."""
    rate = max(1, int(ctx.params.get("request_rate_per_sec", 2)))
    pool = _id_resource_pool(ctx)
    t = ctx.clock.now_ms()
    step = max(100, round(1000 / rate))
    end = int(ctx.params.get("warmup_sec", 4)) * 1000
    while t < end:
        events: list[RawEvent] = []
        for _ in range(rate):
            ip = ctx.rng.choice(list(BENIGN_IPS))
            obj_id = ctx.rng.choice(list(pool))
            events.append(
                RawEvent(
                    id=ctx.rng.uuid_v7(t),
                    sim_time_ms=t,
                    origin="api",
                    type="api.request",
                    src_ip=ip,
                    node_ref="orders_api",
                    benign=True,
                    payload={
                        "method": "GET",
                        "route": "/api/orders/{id}",
                        "route_params": {"id": obj_id},
                        "status": 200,
                        "ms": ctx.rng.randint(4, 30),
                    },
                )
            )
        yield SimBeat(sim_time_ms=t, events=events)
        t += step


def _idor_beats(ctx: SimContext) -> Iterator[SimBeat]:
    """IDOR: attacker walks object ids 1000,1001,1002,... (docs/06 §4.4)."""
    pool = _id_resource_pool(ctx)
    t = ctx.clock.now_ms()
    for obj_id in pool:
        events = [
            RawEvent(
                id=ctx.rng.uuid_v7(t),
                sim_time_ms=t,
                origin="api",
                type="api.request",
                src_ip=ATTACKER_IP,
                node_ref="orders_api",
                payload={
                    "method": "GET",
                    "route": "/api/orders/{id}",
                    "route_params": {"id": obj_id},
                    "status": 200,
                    "ms": ctx.rng.randint(6, 25),
                },
            ),
            RawEvent(
                id=ctx.rng.uuid_v7(t),
                sim_time_ms=t,
                origin="api",
                type="api.data_response",
                src_ip=ATTACKER_IP,
                node_ref="orders_api",
                payload={
                    "route": "/api/orders/{id}",
                    "fields_returned": ["id", "customer", "cvv", "address"],
                    "rows": 1,
                    "scope_exceeded": True,
                },
            ),
        ]
        yield SimBeat(sim_time_ms=t, events=events)
        t += ctx.rng.randint(40, 90)
        if ctx.clock.duration_ms and t >= ctx.clock.duration_ms:
            break


def _brute_force_beats(ctx: SimContext) -> Iterator[SimBeat]:
    """Brute-force attempts against /api/auth (docs/06 §4.2)."""
    t = ctx.clock.now_ms()
    burst = int(ctx.params.get("auth_failure_rate", 1.0)) * 12
    for i in range(max(12, int(burst))):
        events = [
            RawEvent(
                id=ctx.rng.uuid_v7(t),
                sim_time_ms=t,
                origin="api",
                type="api.request",
                src_ip=ATTACKER_IP,
                node_ref="auth_check",
                payload={
                    "method": "POST",
                    "route": "/api/auth/login",
                    "status": 401,
                    "ms": ctx.rng.randint(10, 40),
                    "username": f"admin{i:03d}",
                },
            )
        ]
        yield SimBeat(sim_time_ms=t, events=events)
        t += ctx.rng.randint(15, 60)
        if ctx.clock.duration_ms and t >= ctx.clock.duration_ms:
            break


def phases(ctx: SimContext) -> Iterator[SimBeat]:
    """Drive the API sim through benign → IDOR (+ brute force interleave)."""
    yield from _benign_api_beats(ctx)
    yield from _idor_beats(ctx)
    yield from _brute_force_beats(ctx)


__all__ = ["ATTACKER_IP", "BENIGN_IPS", "phases"]
