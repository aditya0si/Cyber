"""Supply Chain simulator beats (docs/06 §6.4): transitive dependency →
malicious package → lifecycle hook → env exfil. Deterministic."""

from __future__ import annotations

from collections.abc import Iterator

from cybersim.simulation.base import RawEvent, SimBeat
from cybersim.simulation.core.context import SimContext


def _resolve_beats(ctx: SimContext) -> Iterator[SimBeat]:
    """Build dependency resolution chain (docs/06 §6.4 t0-t1)."""
    depth = int(ctx.params.get("dependency_depth", 3))
    chain = ["app", "dep_a", "dep_b", "lib-jwt@1.2.3"]
    t = ctx.clock.now_ms()
    for i in range(min(depth + 1, len(chain))):
        name = chain[i]
        resolved = tuple(chain[i + 1 : i + 2])
        yield SimBeat(
            sim_time_ms=t,
            events=[
                RawEvent(
                    id=ctx.rng.uuid_v7(t),
                    sim_time_ms=t,
                    origin="supply",
                    type="build.dependency_resolve",
                    node_ref="app_build",
                    payload={
                        "name": name,
                        "version": "1.0.0",
                        "resolved_tree": resolved,
                        "package": "lib-jwt@1.2.3",
                    },
                )
            ],
        )
        t += ctx.rng.randint(50, 150)
    # Malicious package installed (with integrity hash).
    yield SimBeat(
        sim_time_ms=t,
        events=[
            RawEvent(
                id=ctx.rng.uuid_v7(t),
                sim_time_ms=t,
                origin="supply",
                type="package.installed",
                node_ref="app_build",
                payload={
                    "name": "lib-jwt",
                    "version": "1.2.3",
                    "integrity_hash": "sha512-abcdef0123456789",
                    "registry": "registry.npmjs.org",
                },
            )
        ],
    )


def _hook_beats(ctx: SimContext) -> Iterator[SimBeat]:
    """Malicious lifecycle hook: env scan + process spawn (docs/06 §6.4 t2-t3)."""
    t = ctx.clock.now_ms()
    delay = int(ctx.params.get("delay_before_activation_ms", 0))
    t += delay
    yield SimBeat(
        sim_time_ms=t,
        events=[
            RawEvent(
                id=ctx.rng.uuid_v7(t),
                sim_time_ms=t,
                origin="supply",
                type="package.lifecycle.hook",
                node_ref="app_build",
                payload={
                    "hook": "postinstall",
                    "cmdline": "node scrape.js",
                    "package": "lib-jwt@1.2.3",
                    "env_patterns_seen": ["AWS_", "_TOKEN", "API_KEY"],
                },
            ),
            RawEvent(
                id=ctx.rng.uuid_v7(t),
                sim_time_ms=t,
                origin="supply",
                type="process.exec",
                node_ref="app_build",
                payload={
                    "caller_package": "lib-jwt@1.2.3",
                    "cmdline": "node scrape.js ~/.config/credentials.json",
                    "cwd": "/opt/app/node_modules/lib-jwt",
                    "package": "lib-jwt@1.2.3",
                },
            ),
            RawEvent(
                id=ctx.rng.uuid_v7(t),
                sim_time_ms=t,
                origin="supply",
                type="process.env_exfil",
                node_ref="app_build",
                payload={
                    "var_patterns_seen": ["AWS_", "_TOKEN", "API_KEY"],
                    "path_touched": "~/.config/credentials.json",
                    "package": "lib-jwt@1.2.3",
                },
            ),
        ],
    )


def _exfil_beat(ctx: SimContext) -> SimBeat:
    """Outbound connection to the simulated C2 (docs/06 §6.4 t4)."""
    t = ctx.clock.now_ms()
    return SimBeat(
        sim_time_ms=t,
        events=[
            RawEvent(
                id=ctx.rng.uuid_v7(t),
                sim_time_ms=t,
                origin="supply",
                type="net.connection",
                node_ref="app_build",
                payload={
                    "src": "10.1.1.5",
                    "dst": "198.51.100.77",
                    "port": 443,
                    "proto": "tcp",
                    "state": "established",
                    "package": "lib-jwt@1.2.3",
                },
            )
        ],
    )


def phases(ctx: SimContext) -> Iterator[SimBeat]:
    """Drive the supply-chain sim through the malicious package chain."""
    yield from _resolve_beats(ctx)
    yield from _hook_beats(ctx)
    yield _exfil_beat(ctx)


__all__ = ["phases"]
