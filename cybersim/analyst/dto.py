"""Detection proposal DTO + EvidenceItem + RecommendedAction (docs/11 §5).

This is the contract `validate(...)` enforces — the LLM/analyst must return
this Pydantic model verbatim. The pubsub API serializes it into a Detection
row for the UI (`docs/08 §4.5`).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cybersim.events.types import Severity
from cybersim.graph.mitre import ThreatClass
from cybersim.graph.types import NodeKind


class EvidenceKind(StrEnum):
    EVENT_BURST = "event_burst"
    GRAPH_TRAVERSAL = "graph_traversal"
    CREDENTIAL_STATE = "credential_state"
    KNOWLEDGE_CITATION = "knowledge_citation"
    BEHAVIORAL_SIGNATURE = "behavioral_signature"


class EvidenceItem(BaseModel):
    """A single piece of evidence for a Detection (docs/11 §3.5 / §5).

    REQUIRED: at least one of `event_ids` / `graph_node_ids` / `citation_refs`
    must be non-empty (the validator's no-orphans rule, `docs/11 §3.9-2`).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, max_length=64)
    kind: EvidenceKind
    weight: float = Field(ge=0.0, le=1.0)
    event_ids: tuple[str, ...] = ()
    graph_node_ids: tuple[str, ...] = ()
    citation_refs: tuple[str, ...] = ()
    summary: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def _no_orphans(self) -> EvidenceItem:
        if not (self.event_ids or self.graph_node_ids or self.citation_refs):
            raise ValueError(
                "evidence item must cite any of event_ids/graph_node_ids/citation_refs"
            )
        return self


class AttackPathNode(BaseModel):
    """One hop in an `attack_path` anchor chain surfaced to the UI."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    label: str
    kind: NodeKind = NodeKind.ASSET
    foothold_state: str = "clean"


class RecommendedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: str
    order: int = Field(ge=1, le=10)
    params: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(max_length=280)


class RiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(max_length=2000)


class DetectionSource(StrEnum):
    AI = "ai"
    RULES = "rules"
    HYBRID = "hybrid"


class ConfidenceBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERIFIED = "verified"


class DetectionProposal(BaseModel):
    """The validation-envelope-contract Pydantic model (docs/11 §5)."""

    model_config = ConfigDict(extra="forbid")

    simulation_id: str
    org_id: str
    window_seq: int = Field(ge=0)
    threat_class: ThreatClass
    title: str = Field(min_length=1, max_length=140)
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_band: ConfidenceBand
    attack_path: list[AttackPathNode]
    evidence: list[EvidenceItem]
    rationale: str = Field(min_length=1, max_length=2000)
    mitre_tactics: tuple[str, ...] = ()
    mitre_techniques: tuple[str, ...] = ()
    owasp_refs: tuple[str, ...] = ()
    recommended_actions: list[RecommendedAction] = []
    source: DetectionSource


__all__ = [
    "AttackPathNode",
    "ConfidenceBand",
    "DetectionProposal",
    "DetectionSource",
    "EvidenceItem",
    "EvidenceKind",
    "RecommendedAction",
    "RiskAssessment",
]
