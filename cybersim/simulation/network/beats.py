"""Network simulator beats (docs/06 §5.3-§5.4): scan → service discovery →
brute → foothold → lateral → exfil. Deterministic via ctx.rng/clock."""

from __future__ import annotations

from collections.abc import Iterator

from cybersim.simulation.base import RawEvent, SimBeat
from cybersim.simulation.core.context import SimContext

ATTACKER_IP = "203.0.113.42"
INTERNAL_NETS = ("10.0.0.5", "10.0.0.15", "10.0.0.25", "10.0.0.35")


def _scan_beats(ctx: SimContext) -> Iterator[SimBeat]:
    """Port scan across the internal /24 (docs/06 §5.4 t0)."""
    ports = (22, 80, 443, 3389, 5432, 6379, 8080, 9200, 8443, 27017)
    t = ctx.clock.now_ms()
    for i in range(3):
        target = INTERNAL_NETS[i % len(INTERNAL_NETS)]
        events = [
            RawEvent(
                id=ctx.rng.uuid_v7(t),
                sim_time_ms=t,
                origin="network",
                type="net.scan_probe",
                src_ip=ATTACKER_IP,
                node_ref=target,
                payload={
                    "target_host": target,
                    "ports": list(ports),
                    "script": "syn_scan",
                },
            )
        ]
        yield SimBeat(sim_time_ms=t, events=events)
        t += ctx.rng.randint(300, 800)
    # Service discovery on the first two hosts.
    for host in INTERNAL_NETS[:2]:
        events = [
            RawEvent(
                id=ctx.rng.uuid_v7(t),
                sim_time_ms=t,
                origin="network",
                type="net.service_discovered",
                src_ip=ATTACKER_IP,
                node_ref=host,
                payload={
                    "host": host,
                    "port": 22,
                    "service": "ssh",
                    "banner_fingerprint": f"OpenSSH_{ctx.rng.randint(7, 9)}.{ctx.rng.randint(0, 9)}",
                },
            )
        ]
        yield SimBeat(sim_time_ms=t, events=events)
        t += ctx.rng.randint(200, 400)


def _brute_beats(ctx: SimContext) -> Iterator[SimBeat]:
    """SSH brute-force against the first discovered host (docs/06 §5.4 t1)."""
    target = INTERNAL_NETS[0]
    t = ctx.clock.now_ms()
    for i in range(14):
        events = [
            RawEvent(
                id=ctx.rng.uuid_v7(t),
                sim_time_ms=t,
                origin="network",
                type="host.login_attempt",
                src_ip=ATTACKER_IP,
                node_ref=target,
                payload={
                    "host": target,
                    "account": f"admin{i % 5}",
                    "success": False,
                    "method": "ssh",
                },
            )
        ]
        yield SimBeat(sim_time_ms=t, events=events)
        t += ctx.rng.randint(20, 60)


def _foothold_and_lateral_beats(ctx: SimContext) -> Iterator[SimBeat]:
    """Successful login → foothold → lateral hop (docs/06 §5.4 t2-t3)."""
    t = ctx.clock.now_ms()
    host0 = INTERNAL_NETS[0]
    host1 = INTERNAL_NETS[1]
    events = [
        RawEvent(
            id=ctx.rng.uuid_v7(t),
            sim_time_ms=t,
            origin="network",
            type="host.login_attempt",
            src_ip=ATTACKER_IP,
            node_ref=host0,
            payload={"host": host0, "account": "admin", "success": True, "method": "ssh"},
        ),
        RawEvent(
            id=ctx.rng.uuid_v7(t),
            sim_time_ms=t,
            origin="network",
            type="host.session",
            src_ip=ATTACKER_IP,
            node_ref=host0,
            payload={
                "host": host0,
                "role": "root",
                "creds": "admin_creds",
                "access_scope": ["host"],
            },
        ),
        RawEvent(
            id=ctx.rng.uuid_v7(t),
            sim_time_ms=t,
            origin="network",
            type="host.process_spawn",
            src_ip=ATTACKER_IP,
            node_ref=host0,
            payload={
                "host": host0,
                "caller": "ssh",
                "cmdline": "ssh admin@10.0.0.15",
                "target": host1,
            },
        ),
        RawEvent(
            id=ctx.rng.uuid_v7(t),
            sim_time_ms=t,
            origin="network",
            type="net.lateral_hop",
            src_ip=ATTACKER_IP,
            node_ref=host1,
            payload={"from_host": host0, "to_host": host1, "method": "ssh_reuse"},
        ),
    ]
    yield SimBeat(sim_time_ms=t, events=events)


def _exfil_beats(ctx: SimContext) -> Iterator[SimBeat]:
    """Bulk data egress from the DB host (docs/06 §5.4 t4)."""
    t = ctx.clock.now_ms()
    yield SimBeat(
        sim_time_ms=t,
        events=[
            RawEvent(
                id=ctx.rng.uuid_v7(t),
                sim_time_ms=t,
                origin="network",
                type="evidence.data_exfil",
                src_ip=ATTACKER_IP,
                node_ref="10.0.0.35",
                payload={
                    "bytes": ctx.rng.randint(50_000_000, 300_000_000),
                    "dst_ext": "198.51.100.200",
                    "host_src": "10.0.0.35",
                },
            )
        ],
    )


def phases(ctx: SimContext) -> Iterator[SimBeat]:
    """Drive the network sim through the recon → lateral → exfil chain."""
    yield from _scan_beats(ctx)
    yield from _brute_beats(ctx)
    yield from _foothold_and_lateral_beats(ctx)
    yield from _exfil_beats(ctx)


__all__ = ["ATTACKER_IP", "INTERNAL_NETS", "phases"]
