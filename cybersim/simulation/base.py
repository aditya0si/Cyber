"""Simulator base interface + RawEvent/SimBeat/ResponseCommand (docs/06 §1)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol, TypeAlias, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from cybersim.simulation.core.context import SimContext

RawEventPayload: TypeAlias = dict[str, Any]


class RawEvent(BaseModel):
    """A simulator-emitted event, pre-normalization (docs/06 §1.3, docs/07 §1.3).

    Simulators emit `RawEvent`s into the Redis `events.raw.<org>.<sim>` stream;
    the Normalizer transforms them into `CanonicalEvent`s. Raw events never
    reach the analyst or UI directly.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    sim_time_ms: int = Field(ge=0)
    origin: str = Field(min_length=1)
    type: str = Field(min_length=1)
    node_ref: str | None = None
    src_ip: str | None = None
    payload: RawEventPayload = Field(default_factory=dict)
    benign: bool = False


class SimBeat(BaseModel):
    """A timed batch of RawEvents emitted together (docs/06 §1.1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sim_time_ms: int = Field(ge=0)
    events: list[RawEvent] = Field(default_factory=list)


class ResponseCommand(BaseModel):
    """An Execute-Response command issued by the executor to a simulator (docs/06 §3.6)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    requested_at_ms: int | None = None


@runtime_checkable
class Simulator(Protocol):
    """A synthetic event producer bounded by a scenario (docs/06 §1).

    Implementations MUST be deterministic: given the same `SimContext.seed` and
    `SimContext.params`, `beats(ctx)` yields the SAME event sequence modulo
    non-determining sidebands (`received_at_ms`, RNG-derived UUIDv7 bits).
    """

    id: str

    def init(self, ctx: SimContext) -> None: ...

    def beats(self, ctx: SimContext) -> Iterator[SimBeat]: ...

    def apply_command(self, cmd: ResponseCommand, ctx: SimContext) -> list[RawEvent]: ...
