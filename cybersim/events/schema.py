"""Canonical event contract (docs/07 §1).

`CanonicalEvent` is the *normative* Pydantic v2 model used by every downstream
component (analyst, graph engine, dashboard). Constructors outside this
module are FORBIDDEN from minting them directly — the Normalizer (`cybersim.
events.normalizer`, Phase 3) is the only legitimate producer.

Phase 1 exposes the data shape plus parsers/round-trip; Phase 3 wires the
normalization pipeline.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cybersim.events.types import AttackStage, EventCategory, Severity


class CanonicalEvent(BaseModel):
    """A single normalized security event (docs/07 §1).

    Frozen: the canonical contract is immutable once minted. MUTATED state
    by response actions produces NEW events (e.g., `response.applied`); they
    never rewrite history.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # ---- Identity -----------------------------------------------------------
    event_id: str
    simulation_id: str
    org_id: str
    sequence: int = Field(ge=0)
    sim_time_ms: int = Field(ge=0)
    received_at_ms: int = Field(ge=0)

    # ---- Classification -----------------------------------------------------
    origin: str
    raw_type: str
    category: EventCategory
    subtype: str
    severity_hint: Severity = Severity.INFO
    attack_stage: AttackStage | None = None

    # ---- Graph linkage ------------------------------------------------------
    target_node_ids: tuple[str, ...] = ()
    source_node_id: str | None = None
    via_edge_ids: tuple[str, ...] = ()

    # ---- MITRE/OWASP labels -------------------------------------------------
    mitre_tactics: tuple[str, ...] = ()
    mitre_techniques: tuple[str, ...] = ()
    owasp_refs: tuple[str, ...] = ()

    # ---- Payload + provenance ----------------------------------------------
    payload: dict[str, object] = Field(default_factory=dict)
    raw_ref: str | None = None
    correlation_key: str | None = None
    benign: bool = False


def assemble(
    *,
    event_id: str,
    simulation_id: str,
    org_id: str,
    sequence: int,
    sim_time_ms: int,
    received_at_ms: int,
    origin: str,
    raw_type: str,
    category: EventCategory,
    subtype: str,
    severity_hint: Severity,
    attack_stage: AttackStage | None = None,
    target_node_ids: tuple[str, ...] = (),
    source_node_id: str | None = None,
    via_edge_ids: tuple[str, ...] = (),
    mitre_tactics: tuple[str, ...] = (),
    mitre_techniques: tuple[str, ...] = (),
    owasp_refs: tuple[str, ...] = (),
    payload: dict[str, object] | None = None,
    raw_ref: str | None = None,
    correlation_key: str | None = None,
    benign: bool = False,
) -> CanonicalEvent:
    """Construct a CanonicalEvent with kwargs. Used by the normalizer (Phase 3)."""
    return CanonicalEvent(
        event_id=event_id,
        simulation_id=simulation_id,
        org_id=org_id,
        sequence=sequence,
        sim_time_ms=sim_time_ms,
        received_at_ms=received_at_ms,
        origin=origin,
        raw_type=raw_type,
        category=category,
        subtype=subtype,
        severity_hint=severity_hint,
        attack_stage=attack_stage,
        target_node_ids=target_node_ids,
        source_node_id=source_node_id,
        via_edge_ids=via_edge_ids,
        mitre_tactics=mitre_tactics,
        mitre_techniques=mitre_techniques,
        owasp_refs=owasp_refs,
        payload=payload or {},
        raw_ref=raw_ref,
        correlation_key=correlation_key,
        benign=benign,
    )
