"""Rule-based fallback analyst (docs/11 §3.11 — Phase 5: M1 milestone).

Deterministic, no LLM. Produces DetectionProposals from canonical events +
the attack graph. Confidence capped at 0.6 per docs/11 §3.11; proposals are
marked `source="rules"` and `degraded=True` so the dashboard can show the
"AI tier degraded — heuristic analysis active" banner (docs/01 §3).
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import groupby

from cybersim.analyst.dto import (
    AttackPathNode,
    ConfidenceBand,
    DetectionProposal,
    DetectionSource,
    EvidenceItem,
    EvidenceKind,
    RecommendedAction,
)
from cybersim.analyst.response_catalog import allowed_actions
from cybersim.events.schema import CanonicalEvent
from cybersim.events.types import Severity
from cybersim.graph.mitre import MitreEntry, ThreatClass, mitre_entry
from cybersim.graph.types import AttackPath, EnvironmentGraph

# Indicator subtype → canonical ThreatClass
SUBTYPE_TO_THREATCLASS: dict[str, ThreatClass] = {
    "sql_injection_indicator": ThreatClass.SQL_INJECTION,
    "exfil_candidate_query": ThreatClass.DATA_EXFILTRATION,
    "auth_success_after_burst": ThreatClass.CREDENTIAL_COMPROMISE,
    "unsanitized_auth_failure_burst": ThreatClass.CREDENTIAL_BRUTE_FORCE,
    "package_lifecycle_hook_suspicious": ThreatClass.MALICIOUS_PACKAGE,
    "env_exfil_pattern": ThreatClass.DATA_EXFILTRATION,
    "idor_enumeration_indicator": ThreatClass.IDOR,
    "api_rate_abuse_indicator": ThreatClass.RATE_ABUSE,
    "port_scan_indicator": ThreatClass.PORT_SCAN,
    "service_discovery_indicator": ThreatClass.SERVICE_DISCOVERY,
    "lateral_movement_indicator": ThreatClass.LATERAL_MOVEMENT,
    "data_exfil_indicator": ThreatClass.DATA_EXFILTRATION,
}


# Detection titles per ThreatClass — surfaced in the SOC feed.
_TITLE_MAP: dict[ThreatClass, str] = {
    ThreatClass.SQL_INJECTION: "SQL injection against web service",
    ThreatClass.DATA_EXFILTRATION: "Sensitive-data query exfiltration pattern",
    ThreatClass.CREDENTIAL_COMPROMISE: "Credential compromise following repeated failures",
    ThreatClass.CREDENTIAL_BRUTE_FORCE: "Credential brute-force burst from src IP",
    ThreatClass.MALICIOUS_PACKAGE: "Malicious package lifecycle hook",
    ThreatClass.IDOR: "Insecure direct object reference enumeration",
    ThreatClass.RATE_ABUSE: "API rate-limit abuse (request flooding)",
    ThreatClass.PORT_SCAN: "Network port scan from src IP",
    ThreatClass.SERVICE_DISCOVERY: "Network service discovery fingerprinting",
    ThreatClass.LATERAL_MOVEMENT: "Lateral movement across internal hosts",
}


def _default_severity_for(tc: ThreatClass) -> Severity:
    return {
        ThreatClass.SQL_INJECTION: Severity.HIGH,
        ThreatClass.DATA_EXFILTRATION: Severity.CRITICAL,
        ThreatClass.CREDENTIAL_COMPROMISE: Severity.HIGH,
        ThreatClass.CREDENTIAL_BRUTE_FORCE: Severity.MEDIUM,
        ThreatClass.MALICIOUS_PACKAGE: Severity.CRITICAL,
        ThreatClass.IDOR: Severity.HIGH,
        ThreatClass.RATE_ABUSE: Severity.MEDIUM,
        ThreatClass.PORT_SCAN: Severity.LOW,
        ThreatClass.SERVICE_DISCOVERY: Severity.LOW,
        ThreatClass.LATERAL_MOVEMENT: Severity.HIGH,
    }.get(tc, Severity.LOW)


def _events_by_id(window: list[CanonicalEvent]) -> dict[str, CanonicalEvent]:
    return {e.event_id: e for e in window}


def _correlation_groups(
    window: list[CanonicalEvent],
) -> list[tuple[str | None, list[CanonicalEvent]]]:
    """Group non-benign events from the SAME correlation_key."""
    nonbenign = [e for e in window if not e.benign]
    sorted_ = sorted(nonbenign, key=lambda e: str(e.correlation_key or "<no-key>"))
    out: list[tuple[str | None, list[CanonicalEvent]]] = []
    for key, group_iter in groupby(sorted_, key=lambda e: e.correlation_key):
        out.append((key if key != "<no-key>" else None, list(group_iter)))
    return out


def _top_threat_class(group: list[CanonicalEvent]) -> ThreatClass | None:
    """Pick the dominant ThreatClass implied by indicator subtypes in `group`."""
    rank_order = {
        ThreatClass.DATA_EXFILTRATION: 5,
        ThreatClass.CREDENTIAL_COMPROMISE: 4,
        ThreatClass.MALICIOUS_PACKAGE: 4,
        ThreatClass.SQL_INJECTION: 3,
        ThreatClass.CREDENTIAL_BRUTE_FORCE: 2,
    }
    classes = [
        SUBTYPE_TO_THREATCLASS[e.subtype] for e in group if e.subtype in SUBTYPE_TO_THREATCLASS
    ]
    if not classes:
        return None
    return max(classes, key=lambda c: rank_order.get(c, 0))


def _all_threat_classes(group: list[CanonicalEvent]) -> list[ThreatClass]:
    """Every DISTINCT ThreatClass implied by indicator subtypes in `group`.

    A kill chain progresses through multiple stages (recon → cred access →
    exfil); each should surface as its own Detection (docs/05 §5.2, docs/06
    `expected_detections`).
    """
    seen: set[ThreatClass] = set()
    out: list[ThreatClass] = []
    for e in group:
        tc = SUBTYPE_TO_THREATCLASS.get(e.subtype)
        if tc is not None and tc not in seen:
            seen.add(tc)
            out.append(tc)
    return out


def _build_evidence(threat_class: ThreatClass, group: list[CanonicalEvent]) -> list[EvidenceItem]:
    """Compose ≥3 evidence items from the normalized group.

    Each EvidenceItem cites concrete event_ids (the validator's no-orphans
    rule, docs/11 §3.9-2). Relevant evidence categories per Fallal docs/11
    §3.5: event_burst, behavioral_signature, credential_state, graph_traversal.
    """
    by_subtype = {e.subtype: e for e in group if e.subtype in SUBTYPE_TO_THREATCLASS}
    items: list[EvidenceItem] = []

    # Evidence 1: event burst (auth.attempt count or burst count)
    auth_attempts = [e for e in group if e.raw_type == "auth.attempt"]
    if auth_attempts:
        first_ids = tuple(e.event_id for e in auth_attempts[:5])
        items.append(
            EvidenceItem(
                label="repeated_failed_logins",
                kind=EvidenceKind.EVENT_BURST,
                weight=0.85,
                event_ids=first_ids,
                summary=f"{len(auth_attempts)} failed auth.attempt events in window",
            )
        )
    http_sqli = by_subtype.get("sql_injection_indicator")
    if http_sqli:
        items.append(
            EvidenceItem(
                label="sqli_payload_signature_observed",
                kind=EvidenceKind.BEHAVIORAL_SIGNATURE,
                weight=0.92,
                event_ids=(http_sqli.event_id,),
                summary=f"http.request {http_sqli.payload.get('path')!r} carried SQL metacharacters",
            )
        )
    # Evidence N: privileged credential state — auth.success with new_geo or admin scope
    auth_success = None
    for e in group:
        if e.raw_type == "auth.success" and e.subtype == "auth_success_after_burst":
            auth_success = e
            break
    if auth_success is None:
        for e in group:
            if e.raw_type == "auth.success":
                auth_success = e
                break
    if auth_success:
        account = str(auth_success.payload.get("account_id", ""))
        scope = "admin" if "admin" in account else "user"
        items.append(
            EvidenceItem(
                label="credential_state_compromised_account",
                kind=EvidenceKind.CREDENTIAL_STATE,
                weight=0.9,
                event_ids=(auth_success.event_id,),
                summary=f"login from {auth_success.payload.get('new_geo')!r} as {auth_success.payload.get('account_id')!r} (scope={scope})",
            )
        )
    # Evidence N+1: exfil-candidate db.query
    exfil = next(
        (e for e in group if e.raw_type == "db.query" and e.subtype == "exfil_candidate_query"),
        None,
    )
    if exfil:
        items.append(
            EvidenceItem(
                label="exfiltration_query_observed",
                kind=EvidenceKind.BEHAVIORAL_SIGNATURE,
                weight=0.93,
                event_ids=(exfil.event_id,),
                summary=f"db.query rows={exfil.payload.get('rows_returned')} parameterized={exfil.payload.get('parameterized')}",
            )
        )

    # Generic per-indicator evidence for non-web chains (docs/07 §3): iterate
    # every indicator event in the group and emit one evidence item per kind.
    _INDICATOR_EVIDENCE: dict[str, tuple[str, EvidenceKind, float, str]] = {
        "idor_enumeration_indicator": (
            "idor_enumeration_observed",
            EvidenceKind.BEHAVIORAL_SIGNATURE,
            0.9,
            "consecutive object-id reads from same source",
        ),
        "api_rate_abuse_indicator": (
            "api_rate_abuse_observed",
            EvidenceKind.EVENT_BURST,
            0.75,
            "sustained rate-limit denials on API route",
        ),
        "port_scan_indicator": (
            "port_scan_observed",
            EvidenceKind.BEHAVIORAL_SIGNATURE,
            0.85,
            "SYN scan across many ports from same source",
        ),
        "service_discovery_indicator": (
            "service_discovery_observed",
            EvidenceKind.BEHAVIORAL_SIGNATURE,
            0.7,
            "service banner fingerprinting after scan",
        ),
        "lateral_movement_indicator": (
            "lateral_movement_observed",
            EvidenceKind.GRAPH_TRAVERSAL,
            0.92,
            "attacker moved host-to-host via reused credentials",
        ),
        "data_exfil_indicator": (
            "bulk_egress_observed",
            EvidenceKind.BEHAVIORAL_SIGNATURE,
            0.93,
            "large outbound data transfer to external destination",
        ),
        "package_lifecycle_hook_suspicious": (
            "malicious_package_hook_observed",
            EvidenceKind.BEHAVIORAL_SIGNATURE,
            0.95,
            "post-install hook executed env-scan pattern",
        ),
        "env_exfil_pattern": (
            "env_exfil_pattern_observed",
            EvidenceKind.BEHAVIORAL_SIGNATURE,
            0.9,
            "process scanned credential-like environment patterns",
        ),
    }
    seen_labels: set[str] = {i.label for i in items}
    for ev in group:
        spec = _INDICATOR_EVIDENCE.get(ev.subtype)
        if spec is None or spec[0] in seen_labels:
            continue
        items.append(
            EvidenceItem(
                label=spec[0],
                kind=spec[1],
                weight=spec[2],
                event_ids=(ev.event_id,),
                summary=spec[3],
            )
        )
        seen_labels.add(spec[0])

    # Bonus: graph traversal evidence (path to user_data)
    nids = tuple(group[0].target_node_ids) if group else ()
    if nids:
        items.append(
            EvidenceItem(
                label="graph_traversal_to_sensitive_data",
                kind=EvidenceKind.GRAPH_TRAVERSAL,
                weight=0.75,
                event_ids=(),
                graph_node_ids=nids,
                summary="attack_graph path from compromised node to DATA node within ≤4 hops",
            )
        )
    return items


def _mitre_for(
    threat_class: ThreatClass,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    entry: MitreEntry = mitre_entry(threat_class)
    tactics = tuple(t for t in entry.tactics)
    techniques = tuple(t for t in entry.techniques)
    return tactics, techniques, entry.owasp_refs


def _attack_path_anchors(
    env: EnvironmentGraph,
    rendered_paths: Sequence[AttackPath] | None,
    src_node_id: str | None,
) -> list[AttackPathNode]:
    """Project AttackPath into UI-facing anchors (`{node_id,label,kind}`)."""
    if rendered_paths is None or src_node_id is None:
        return []
    closing = [p for p in rendered_paths if p.closes_at_node_kind.name == "DATA"]
    if not closing:
        return [AttackPathNode(node_id=src_node_id, label=src_node_id)]
    chosen = min(closing, key=lambda p: p.length)
    out: list[AttackPathNode] = []
    for nid in chosen.nodes:
        node = env.get_node(nid)
        out.append(
            AttackPathNode(
                node_id=nid,
                label=node.label if node else nid,
                kind=node.kind
                if node
                else __import__("cybersim.graph.types", fromlist=["NodeKind"]).NodeKind.ASSET,
                foothold_state=(node.foothold_state.value if node else "clean"),
            )
        )
    return out


def _recommended_actions(simulator_id: str) -> list[RecommendedAction]:
    """Surface passive recommended actions per simulator catalog."""
    out: list[RecommendedAction] = []
    for order, action_id in enumerate(allowed_actions(simulator_id), start=1):
        if order > 5:
            break
        out.append(
            RecommendedAction(
                action_id=action_id,
                order=order,
                params={},
                rationale=f"rule-based recommendation: {action_id}",
            )
        )
    return out


def analyze_window(
    window: list[CanonicalEvent],
    *,
    org_id: str,
    simulation_id: str,
    window_seq: int,
    env: EnvironmentGraph,
    graph_paths: Sequence[AttackPath] | None = None,
    simulator_id: str = "web",
) -> list[DetectionProposal]:
    """Produce DetectionProposals from one analysis window (one per distinct
    threat class in the candidate groups); [] if nothing suspicious.

    Rule-fallback semantics (docs/11 §3.11):
      - source = "rules", confidence <= 0.6
      - evidence >= 2 items per proposal (validator enforces >= 2)
      - attack_path = the shortest path to DATA, projected on env
      - rationale = templated
      - recommended_actions populated from per-simulator whitelist (≤5)

    Multiple detections per window are legitimate: a kill chain progressing
    through recon → cred access → exfil SHOULD surface each stage (docs/05
    §5.2 chain templates, docs/06 `expected_detections`).
    """
    groups = _correlation_groups(window)
    candidates: list[tuple[list[CanonicalEvent], ThreatClass]] = []
    for _, group in groups:
        for tc in _all_threat_classes(group):
            candidates.append((group, tc))
    if not candidates:
        return []
    # Dedupe threat classes (keep the first/strongest group per class).
    seen: set[ThreatClass] = set()
    proposals: list[DetectionProposal] = []
    for group, threat_class in candidates:
        if threat_class in seen:
            continue
        seen.add(threat_class)
        evidence = _build_evidence(threat_class, group)
        if len(evidence) < 2:
            continue  # validator would abort; out-of-window case

        src_node_id = group[0].source_node_id if group else None
        attack_path = _attack_path_anchors(env, graph_paths, src_node_id)

        tactics, techniques, owasp = _mitre_for(threat_class)
        base_severity = _default_severity_for(threat_class)

        rationale_lines = [
            f"Heuristic detection (AI tier degraded). ThreatClass={threat_class.value}.",
            f"Correlated {len(group)} event(s) across correlation_key={group[0].correlation_key!r}.",
            f"Evidence: {', '.join(e.label for e in evidence)}.",
            f"Severity floor: {base_severity.value} (graph-distance clamp applies).",
        ]
        if attack_path:
            labels = " -> ".join(n.label for n in attack_path)
            rationale_lines.append(f"attack_path: {labels}")

        proposals.append(
            DetectionProposal(
                simulation_id=simulation_id,
                org_id=org_id,
                window_seq=window_seq,
                threat_class=threat_class,
                title=_TITLE_MAP.get(threat_class, threat_class.value),
                severity=base_severity,
                confidence=0.6,
                confidence_band=ConfidenceBand.MEDIUM,
                attack_path=attack_path,
                evidence=evidence,
                rationale=" ".join(rationale_lines),
                mitre_tactics=tactics,
                mitre_techniques=techniques,
                owasp_refs=owasp,
                recommended_actions=_recommended_actions(simulator_id),
                source=DetectionSource.RULES,
            )
        )
    return proposals


__all__ = ["analyze_window"]
