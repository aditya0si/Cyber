"""Web App simulator beat scheduler & payload builders (docs/06 §3.4).

The sim proceeds through deterministic phases driven by `ctx.rng` and
`ctx.clock`. In sim-time terms (which is decoupled from wall-clock):

  1. warmup           -> benign traffic only (noise_ratio * benign_users)
  2. recon            -> attacker probes /api/login with malformed SQLi payloads
  3. brute+injection  -> repeated attempts; rate doubles; correlated db.error
  4. successful_sqli   -> large rows_returned (auth.success from new geo)
  5. post_exploit      -> query widening toward user_data
  6. (optional lateral -> admin_creds via auth_svc -- guarded by attacker_skill)

Every random decision goes through `ctx.rng`; beat intervals drawn via
`ctx.rng.randint(min, max)` so the schedule is reproducible per seed.
"""

from __future__ import annotations

from collections.abc import Iterator

from cybersim.simulation.base import RawEvent, SimBeat
from cybersim.simulation.core.context import SimContext

ATTACKER_IP = "203.0.113.42"
BENIGN_IPS = ("198.51.100.10", "198.51.100.20", "198.51.100.30")

#: Top SQLi payloads per `payload_mutation_seed`; deterministic selection.
SQLI_PAYLOADS: tuple[tuple[str, str], ...] = (
    ("tautology", "' OR 1=1--"),
    ("union", "x' UNION SELECT NULL, version()--"),
    ("boolean", "admin' AND 1=1--"),
    ("error", "x' AND extractvalue(1, concat(0x7e,(SELECT version())))--"),
    ("stacked", "'; SELECT pg_sleep(0.1); --"),
    ("time", "x'; WAITFOR DELAY '0:0:2'; --"),
)


def _brief_payloads(rng_block: int) -> tuple[tuple[str, str], ...]:
    """Deterministically choose the active SQLi payload set per mutation seed."""
    base = list(SQLI_PAYLOADS)
    cut = 3 + (rng_block % 3)  # 3..5 payloads active
    rotated = base[rng_block % len(base) :] + base[: rng_block % len(base)]
    return tuple(rotated[:cut])


def _warmup_beats(ctx: SimContext, attacker_ip: str) -> Iterator[SimBeat]:
    """Yield beats of legitimate benign traffic only (noise_ratio rules how much)."""
    noise_ratio = float(ctx.params.get("noise_ratio", 0.2))
    benign = ctx.params.get("benign_users", ("alice", "bob", "carol"))
    benign_list = list(benign) if isinstance(benign, (tuple, list)) else ["alice"]
    rate_per_sec = int(ctx.params.get("request_rate_per_sec", 4))
    duration_sec = int(ctx.params.get("warmup_sec", 6))
    end_ms = duration_sec * 1000
    step_ms = max(100, round(1000 / max(1, rate_per_sec)))
    t = 0
    while t < end_ms:
        beat_events: list[RawEvent] = []
        n = ctx.rng.randint(1, max(1, round(rate_per_sec * noise_ratio)))
        for _i in range(n):
            user = ctx.rng.choice(benign_list)
            ip = ctx.rng.choice(list(BENIGN_IPS))
            path = "/index.html" if ctx.rng.bool(0.7) else "/api/login"
            body = {"username": user, "password": f"pw{ctx.rng.randint(1, 99)}"}
            # benign warmup requests succeed ~99% of the time; status == 200
            status = 200
            beat_events.append(
                RawEvent(
                    id=ctx.rng.uuid_v7(ctx.clock.now_ms() + t),
                    sim_time_ms=ctx.clock.now_ms() + t,
                    origin="web",
                    type="http.request",
                    src_ip=ip,
                    node_ref="login_ep" if path == "/api/login" else None,
                    benign=True,
                    payload={
                        "method": "GET" if path == "/index.html" else "POST",
                        "path": path,
                        "status": status,
                        "body": body if path == "/api/login" else None,
                        "ms": ctx.rng.randint(5, 40),
                    },
                )
            )
        yield SimBeat(sim_time_ms=ctx.clock.now_ms() + t, events=beat_events)
        t += step_ms


def _recon_beats(ctx: SimContext, attacker_ip: str) -> Iterator[SimBeat]:
    """Yield beats of attacker recon: malformed SQLi payloads against /api/login."""
    payloads = _brief_payloads(int(ctx.params.get("payload_mutation_seed", 7)))
    stealth = float(ctx.params.get("stealth_error_rate", 0.6))
    iter_count = len(payloads) * 2
    t = ctx.clock.now_ms()
    for _i in range(iter_count):
        kind, payload = ctx.rng.choice(list(payloads))
        body = {"username": payload, "password": "x"}
        site_warning = ctx.rng.bool(stealth)
        events: list[RawEvent] = [
            RawEvent(
                id=ctx.rng.uuid_v7(t),
                sim_time_ms=t,
                origin="web",
                type="http.request",
                src_ip=attacker_ip,
                node_ref="login_ep",
                payload={
                    "method": "POST",
                    "path": "/api/login",
                    "status": 500 if site_warning else 200,
                    "body": body,
                    "ms": ctx.rng.randint(20, 80),
                    "sqli_pattern": kind,
                },
            ),
        ]
        if site_warning:
            events.append(
                RawEvent(
                    id=ctx.rng.uuid_v7(t),
                    sim_time_ms=t,
                    origin="web",
                    type="db.error",
                    src_ip=attacker_ip,  # recon-phase db.error: same causal chain
                    node_ref="users_db",
                    payload={
                        "code": "42601",
                        "message": f"syntax error near '{payload[:8]}'",
                        "query_ref": events[0].id,
                    },
                )
            )
        yield SimBeat(sim_time_ms=t, events=events)
        t += ctx.rng.randint(150, 400)


def _injection_burst_beats(ctx: SimContext, attacker_ip: str) -> Iterator[SimBeat]:
    """Yield beats with intentionally-form `repeated_failed_logins` burst + `db.error`."""
    payloads = _brief_payloads(int(ctx.params.get("payload_mutation_seed", 7)) + 1)
    burst_count = 17
    t = ctx.clock.now_ms()
    failed_attempts: list[RawEvent] = []
    for _i in range(burst_count):
        kind, payload = ctx.rng.choice(list(payloads))
        site_warning = ctx.rng.bool(0.85)
        attempt = RawEvent(
            id=ctx.rng.uuid_v7(t),
            sim_time_ms=t,
            origin="web",
            type="auth.attempt",
            node_ref="login_ep",
            src_ip=attacker_ip,
            payload={
                "username": f"admin{payload}",
                "success": False,
                "user_agent": "SimBot/1.0",
                "mfa_used": False,
            },
        )
        req = RawEvent(
            id=ctx.rng.uuid_v7(t),
            sim_time_ms=t,
            origin="web",
            type="http.request",
            src_ip=attacker_ip,
            node_ref="login_ep",
            payload={
                "method": "POST",
                "path": "/api/login",
                "status": 500 if site_warning else 401,
                "body": {"username": f"admin{payload}", "password": "x"},
                "ms": ctx.rng.randint(20, 90),
                "sqli_pattern": kind,
            },
        )
        failed_attempts.append(attempt)
        events = [req, attempt]
        if site_warning:
            events.append(
                RawEvent(
                    id=ctx.rng.uuid_v7(t),
                    sim_time_ms=t,
                    origin="web",
                    type="db.error",
                    src_ip=attacker_ip,  # SQLi-chain db.error: trace back to attacker
                    node_ref="users_db",
                    payload={
                        "code": "42703",
                        "message": "column does not exist",
                        "query_ref": req.id,
                    },
                )
            )
        yield SimBeat(sim_time_ms=t, events=events)
        t += ctx.rng.randint(20, 80)


def _successful_sqli_beat(ctx: SimContext, attacker_ip: str) -> SimBeat:
    """The successful SQLi: large rows_returned + auth.success from new geo."""
    t = ctx.clock.now_ms()
    rows = ctx.rng.randint(2_000, 9_000)
    req = RawEvent(
        id=ctx.rng.uuid_v7(t),
        sim_time_ms=t,
        origin="web",
        type="http.request",
        src_ip=attacker_ip,
        node_ref="login_ep",
        payload={
            "method": "POST",
            "path": "/api/login",
            "status": 200,
            "body": {"username": "' OR 1=1--", "password": "x"},
            "ms": ctx.rng.randint(120, 240),
            "rows_returned": rows,
            "sqli_pattern": "tautology",
        },
    )
    db_q = RawEvent(
        id=ctx.rng.uuid_v7(t),
        sim_time_ms=t,
        origin="web",
        type="db.query",
        src_ip=attacker_ip,
        node_ref="users_db",
        payload={
            "db": "users_db",
            "statement": "SELECT id,username,email FROM users;",
            "rows_returned": rows,
            "parameterized": False,
            "exfil_candidate": True,
        },
    )
    auth = RawEvent(
        id=ctx.rng.uuid_v7(t),
        sim_time_ms=t,
        origin="web",
        type="auth.success",
        node_ref="auth_svc",
        src_ip=attacker_ip,
        payload={"account_id": "admin@finbank", "factor": "password", "new_geo": "sim:CN"},
    )
    sess = RawEvent(
        id=ctx.rng.uuid_v7(t),
        sim_time_ms=t,
        origin="web",
        type="session.created",
        node_ref="auth_svc",
        payload={"account_id": "admin@finbank", "session_id": "s-1", "scope": ["admin"]},
    )
    return SimBeat(sim_time_ms=t, events=[req, db_q, auth, sess])


def _post_exploit_beats(ctx: SimContext, attacker_ip: str) -> Iterator[SimBeat]:
    """Query widening targeting user_data; indicates privilege escalation behavior."""
    payloads = (
        "SELECT * FROM users;",
        "SELECT * FROM users, payments;",
        "COPY users TO '/tmp/dump';",
    )
    t = ctx.clock.now_ms()
    for _i in range(4):
        stmt = payloads[_i % len(payloads)]
        events = [
            RawEvent(
                id=ctx.rng.uuid_v7(t),
                sim_time_ms=t,
                origin="web",
                type="db.query",
                src_ip=attacker_ip,  # post-exploit queries continue attacker's session
                node_ref="users_db",
                payload={
                    "db": "users_db",
                    "statement": stmt,
                    "rows_returned": ctx.rng.randint(5_000, 50_000),
                    "parameterized": False,
                    "exfil_candidate": True,
                },
            ),
        ]
        yield SimBeat(sim_time_ms=t, events=events)
        t += ctx.rng.randint(800, 2000)


def phases(ctx: SimContext, attacker_ip: str) -> Iterator[SimBeat]:
    """Top-level generator: drive the sim through phases (reproducibly)."""
    yield from _warmup_beats(ctx, attacker_ip)
    yield from _recon_beats(ctx, attacker_ip)
    yield from _injection_burst_beats(ctx, attacker_ip)
    yield _successful_sqli_beat(ctx, attacker_ip)
    yield from _post_exploit_beats(ctx, attacker_ip)


__all__ = [
    "ATTACKER_IP",
    "BENIGN_IPS",
    "phases",
]
