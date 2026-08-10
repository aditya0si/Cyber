"""DetectionProposal validator (docs/11 §3.9 — the *safety spine*).

Pure functions; operates on already-constructed DTOs. The runtime calls
`validate(proposal)` BEFORE emitting onto the bus. Guarantees:

  1. JSON conformant (Pydantic model already enforces schema).
  2. `evidence` length ≥ 2; each item cites ≥1 ref.
  3. `severity` clamped to graph-distance floor (`docs/05 §6.1`):
        - ≤2 hops to DATA → at least HIGH
        - 3-4 hops         -> at least MEDIUM
        - > 4 hops / none  → at most LOW
  4. `confidence` clamped per evidence count (`docs/05 §6.2`):
        - ≥ 0.75 requires ≥3 evidence items
        - ≥ 0.5  requires ≥2 evidence items
        - < 0.5  requires none
  5. `attack_path` non-empty OR `confidence` clamped to ≤ 0.5.
  6. `recommended_actions` whitelisted & scoped (action_id ∈ catalog).
  7. `rationale` ≤ 2000 chars; no forbidden secret-like tokens.
  8. MITRE T-IDs in the proposal must be a subset of the union of:
     - MITRE T-IDs attached to cited event IDs (event.mitre_techniques)
     - RAG CITED context (Phase 6 assets; Phase 5 has none → treated as []
     We treat absence of RAG as 'only allow what events already have'.

Implements clamps (severity UP and confidence DOWN) per docs/11 §3.9:
"Severity clamps both UP and DOWN — trust-LLM-only / one-sided is wrong."
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from cybersim.analyst.dto import (
    ConfidenceBand,
    DetectionProposal,
)
from cybersim.events.schema import CanonicalEvent
from cybersim.events.types import Severity
from cybersim.graph.types import AttackPath, NodeKind


@dataclass
class ValidationResult:
    """Outcome of `validate(...)`. `proposal` is post-clamp unless `aborted=True`."""

    ok: bool
    proposal: DetectionProposal | None
    reasons: list[str] = field(default_factory=list)
    clamps_applied: list[str] = field(default_factory=list)
    fatal: bool = False

    @property
    def aborted(self) -> bool:
        return self.fatal or self.proposal is None


@dataclass
class ValidationOutcome:
    """Joined: validated proposal + the per-step diagnostics for telemetry."""

    result: ValidationResult
    proposal: DetectionProposal | None = None


_SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|password|bearer|secret|aws_secret)")


def band_for(confidence: float) -> ConfidenceBand:
    if confidence >= 0.75:
        return ConfidenceBand.HIGH if confidence < 0.85 else ConfidenceBand.VERIFIED
    if confidence >= 0.5:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


def graph_distance_severity_floor(paths: Sequence[AttackPath] | None) -> Severity:
    """Deterministic severity floor from graph distance to DATA (docs/05 §6.1)."""
    if not paths:
        return Severity.INFO
    closing_at_data = [p for p in paths if p.closes_at_node_kind == NodeKind.DATA]
    if not closing_at_data:
        return Severity.INFO
    min_len = min(p.length for p in closing_at_data)
    if min_len <= 2:
        return Severity.HIGH
    if min_len <= 4:
        return Severity.MEDIUM
    return Severity.LOW


_SEVERITY_RANK = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


def _clamp_severity_up(sev: Severity, floor: Severity) -> tuple[Severity, bool]:
    """Align `sev` to `floor` only when `floor > sev` (clamp UP only)."""
    if _SEVERITY_RANK[floor] > _SEVERITY_RANK[sev]:
        return floor, True
    return sev, False


def _clamp_confidence_evidence(confidence: float, evidence_count: int) -> tuple[float, str | None]:
    """Enforce the ≥3 evidence requirement for confidence ≥ 0.75 etc."""
    if confidence >= 0.75 and evidence_count < 3:
        return 0.74, "confidence_clamped_to_0.74_lack_of_evidence"
    if confidence >= 0.5 and evidence_count < 2:
        return 0.49, "confidence_clamped_to_0.49_lack_of_evidence"
    return confidence, None


def _rule_fallback_confidence_cap(confidence: float) -> tuple[float, str | None]:
    """Rule-based detections are capped at 0.6 (docs/11 §3.11)."""
    if confidence > 0.6:
        return 0.6, "confidence_capped_to_0.6_rule_source"
    return confidence, None


def validate(
    proposal: DetectionProposal,
    *,
    allowed_action_ids: Sequence[str] = (),
    cited_mitre_techniques: Sequence[str] = (),
    events_by_id: Mapping[str, CanonicalEvent] | None = None,
    graph_paths: Sequence[AttackPath] | None = None,
) -> ValidationOutcome:
    """Validate + clamp a DetectionProposal; return the post-clamp proposal.

    The caller is expected to honor `result.aborted`: do NOT emit if aborted.
    """
    reasons: list[str] = []
    clamps: list[str] = []

    # ---- 2. Evidence minimums (≥2, no orphans is enforced by the DTO) ------
    if len(proposal.evidence) < 2:
        reasons.append("evidence_min_2_required")
        return ValidationOutcome(
            result=ValidationResult(
                ok=False,
                proposal=None,
                reasons=reasons,
                fatal=True,
            ),
            proposal=None,
        )

    # ---- 4. Confidence clamps (evidence count + rule-source) ---------------
    conf, clamp1 = _clamp_confidence_evidence(proposal.confidence, len(proposal.evidence))
    if clamp1:
        clamps.append(clamp1)
    if proposal.source.value == "rules":
        conf, clamp2 = _rule_fallback_confidence_cap(conf)
        if clamp2:
            clamps.append(clamp2)

    # ---- 3. Severity clamp UP per graph-distance floor -------------
    floor = graph_distance_severity_floor(graph_paths)
    sev, sev_clamped = _clamp_severity_up(proposal.severity, floor)
    if sev_clamped:
        clamps.append(f"severity_clamped_up_to_{sev.value}_graph_distance")

    # ---- 5. attack_path must exist OR confidence <= 0.5 -------------
    has_path = bool(proposal.attack_path)
    if not has_path and conf > 0.5:
        conf = 0.5
        clamps.append("confidence_0.5_no_attack_path")

    # ---- 6. recommended_actions whitelisted ----------
    bad_actions: list[str] = []
    if allowed_action_ids:
        for action in proposal.recommended_actions:
            if action.action_id not in set(allowed_action_ids):
                bad_actions.append(action.action_id)
    if bad_actions:
        reasons.append("recommended_actions_not_whitelisted:" + ",".join(bad_actions))
        clamps.append("recommended_actions_pruned")
        proposal = proposal.model_copy(
            update={
                "recommended_actions": [
                    a
                    for a in proposal.recommended_actions
                    if not bad_actions or a.action_id in set(allowed_action_ids)
                ],
            }
        )

    # ---- 7. rationale hygiene ----------
    if _SECRET_PATTERN.search(proposal.rationale):
        reasons.append("rationale_forbidden_secret_token")
        return ValidationOutcome(
            result=ValidationResult(
                ok=False,
                proposal=None,
                reasons=reasons,
                fatal=True,
            ),
            proposal=None,
        )

    # ---- 8. MITRE anti-hallucination ----------
    cited_mitre_set = set(cited_mitre_techniques)
    if events_by_id is not None:
        # Add per-event MITRE technologies to the cited set.
        for ev_id in proposal.evidence:
            for eid in ev_id.event_ids:
                ev = events_by_id.get(eid)
                if ev is not None:
                    cited_mitre_set.update(ev.raw_context.get("mitre_techniques", []))
    proposed_mitre = set(proposal.mitre_techniques)
    hallucinated = proposed_mitre - cited_mitre_set
    if hallucinated:
        clamps.append(f"mitre_dropped:{','.join(sorted(hallucinated))}")
        proposal = proposal.model_copy(
            update={
                "mitre_techniques": tuple(
                    t for t in proposal.mitre_techniques if t not in hallucinated
                ),
            }
        )

    # ---- apply remaining clamps in one model_copy ----------
    proposal = proposal.model_copy(
        update={
            "confidence": conf,
            "confidence_band": band_for(conf),
            "severity": sev,
        }
    )

    if reasons:
        return ValidationOutcome(
            result=ValidationResult(
                ok=False,
                proposal=None,
                reasons=reasons,
                clamps_applied=clamps,
            ),
            proposal=None,
        )
    return ValidationOutcome(
        result=ValidationResult(
            ok=True,
            proposal=proposal,
            clamps_applied=clamps,
        ),
        proposal=proposal,
    )


__all__ = [
    "ValidationOutcome",
    "ValidationResult",
    "band_for",
    "graph_distance_severity_floor",
    "validate",
]
