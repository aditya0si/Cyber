"""LangGraph analyst nodes (docs/11 §3, docs/21 Task 6.1)."""

from __future__ import annotations

from typing import Any

from cybersim.analyst.dto import DetectionProposal, EvidenceItem, RecommendedAction
from cybersim.analyst.prompting import render
from cybersim.analyst.state import AnalystState
from cybersim.analyst.tools import AnalystTools
from cybersim.analyst.validator import validate
from cybersim.events.schema import CanonicalEvent
from cybersim.graph.mitre import ThreatClass
from cybersim.graph.repo import GraphRepository
from cybersim.graph.types import EnvironmentGraph, NodeKind

# ---------------------------------------------------------------------------
# Typed state (LangGraph uses dict; we keep the keys typed here for clarity).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Node 1: event_ingestion (deterministic passthrough — window already sliced)
# ---------------------------------------------------------------------------


def event_ingestion(state: AnalystState) -> dict[str, Any]:
    """Assert the window is present; enrich with aggregate stats."""
    events: list[CanonicalEvent] = state.get("events", [])
    nonbenign = [e for e in events if not e.raw_context.get("benign", False)]
    total = max(1, len(events))
    dominant = "info"
    for e in events:
        sev = e.raw_context.get("severity_hint", "info")
        rank = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(sev, 0)
        cur = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(dominant, 0)
        if rank > cur:
            dominant = sev
    state["window_stats"] = {
        "total_events": len(events),
        "nonbenign": len(nonbenign),
        "benign_ratio": round((total - len(nonbenign)) / total, 3),
        "dominant_severity_hint": dominant,
    }
    return dict(state)


# ---------------------------------------------------------------------------
# Node 2: candidate_group (deterministic grouping by correlation_key)
# ---------------------------------------------------------------------------


def candidate_group(state: AnalystState) -> dict[str, Any]:
    events: list[CanonicalEvent] = state.get("events", [])
    groups: dict[str, list[CanonicalEvent]] = {}
    for e in events:
        if e.raw_context.get("benign", False):
            continue
        key = e.raw_context.get("correlation_key") or "<none>"
        groups.setdefault(key, []).append(e)
    # Candidate = the largest non-benign group with any threat-indicator subtype.
    from cybersim.analyst.rules_fallback import SUBTYPE_TO_THREATCLASS

    best: list[CanonicalEvent] = []
    for group in groups.values():
        if any(e.raw_context.get("subtype") in SUBTYPE_TO_THREATCLASS for e in group) and len(
            group
        ) > len(best):
            best = group
    state["candidate"] = best
    return dict(state)


# ---------------------------------------------------------------------------
# Node 3: threat_detection (LLM triage)
# ---------------------------------------------------------------------------


def threat_detection(state: AnalystState, *, llm: Any, tools: AnalystTools) -> dict[str, Any]:
    events: list[CanonicalEvent] = state.get("candidate", []) or state.get("events", [])
    stats = state.get("window_stats", {})
    payloads = [
        {
            "origin": e.raw_context.get("origin", ""),
            "raw_type": e.raw_context.get("raw_type", ""),
            "subtype": e.raw_context.get("subtype", ""),
            "severity_hint": e.raw_context.get("severity_hint", "info"),
            "attack_stage": e.raw_context.get("attack_stage"),
            "mitre_techniques": list(e.raw_context.get("mitre_techniques", [])),
            "correlation_key": e.raw_context.get("correlation_key"),
            "payload_summary": {
                k: v
                for k, v in e.raw_context.get("payload", {}).items()
                if k not in ("headers", "body")
            },
        }
        for e in events[:40]
    ]
    system = render(
        "triage.j2",
        threat_class_enum=", ".join(tc.value for tc in ThreatClass),
        events=[],
        total_events=0,
        benign_ratio=0.0,
        dominant_severity_hint="info",
    )
    user = render(
        "triage.j2",
        threat_class_enum=", ".join(tc.value for tc in ThreatClass),
        events=payloads,
        total_events=stats.get("total_events", 0),
        benign_ratio=stats.get("benign_ratio", 0.0),
        dominant_severity_hint=stats.get("dominant_severity_hint", "info"),
    )
    raw = llm.complete_json(system=system, user=user, max_tokens=512)
    suspicious = bool(raw.get("is_suspicious", False))
    tc_raw = raw.get("threat_class")
    threat_class: ThreatClass | None = None
    if tc_raw and isinstance(tc_raw, str):
        try:
            threat_class = ThreatClass(tc_raw)
        except ValueError:
            threat_class = None
    state["triage"] = {
        "is_suspicious": suspicious,
        "threat_class": threat_class.value if threat_class else None,
        "rationale_one_line": raw.get("rationale_one_line", ""),
        "confidence_signal": raw.get("confidence_signal", "low"),
        "suggested_nodes": raw.get("suggested_attack_path_node_ids", []),
    }
    # Deterministic veto: if severity_hint >= high in the candidate, treat as
    # suspicious even if the LLM hedged (docs/11 §3.3 — overrule both ways).
    if not suspicious:
        for e in events:
            if e.raw_context.get("severity_hint", "info") in (
                "high",
                "critical",
            ) and not e.raw_context.get("benign", False):
                suspicious = True
                threat_class = threat_class or ThreatClass.BENIGN
                break
    state["triage"]["is_suspicious"] = suspicious
    if threat_class is not None:
        state["triage"]["threat_class"] = threat_class.value
    return dict(state)


# ---------------------------------------------------------------------------
# Node 4: graph_retrieval (tools → attack paths)
# ---------------------------------------------------------------------------


def graph_retrieval(state: AnalystState, *, tools: AnalystTools) -> dict[str, Any]:
    # Prefer the first event's source_node_id (attacker ingress anchor) so
    # path queries start where the events say the attacker is.
    src: str | None = None
    for ev in state.get("events", []):
        if ev.raw_context.get("source_node_id"):
            src = ev.raw_context.get("source_node_id")
            break
    paths = tools.get_attack_paths(node_kinds=("DATA",), hops=4, max_paths=5, src=src)
    state["graph_paths"] = paths
    state["attack_path_summary"] = [
        {"nodes": p["nodes"], "closes_at": p["closes_at"], "length": p["length"]} for p in paths
    ]
    return dict(state)


# ---------------------------------------------------------------------------
# Node 5: rag_lookup (deterministic retrieval — knowledge repo)
# ---------------------------------------------------------------------------


def rag_lookup(
    state: AnalystState,
    *,
    knowledge_repo: Any,
    threat_class_hint: str | None = None,
) -> dict[str, Any]:
    tc = threat_class_hint or (state.get("triage") or {}).get("threat_class")
    query = tc or "suspicious security event"
    hits = knowledge_repo.retrieve(query=query, k=4, filters={"source": None})
    state["knowledge_hits"] = [
        {
            "entry_id": h.entry.entry_id,
            "source_id": h.entry.source_id,
            "title": h.entry.title,
            "score": round(h.score, 3),
        }
        for h in hits
    ]
    return dict(state)


# ---------------------------------------------------------------------------
# Node 6: evidence_analysis (LLM builds the evidence trail)
# ---------------------------------------------------------------------------


def evidence_analysis(
    state: AnalystState, *, llm: Any, events: list[CanonicalEvent]
) -> dict[str, Any]:
    attack_path = state.get("attack_path_summary", [])
    knowledge_hits = state.get("knowledge_hits", [])
    events_out = []
    for e in events:
        if e.raw_context.get("benign", False):
            continue
        events_out.append(
            {
                "event_id": e.event_id,
                "subtype": e.raw_context.get("subtype", ""),
                "severity_hint": e.raw_context.get("severity_hint", "info"),
                "correlation_key": e.raw_context.get("correlation_key"),
                "target_node_ids": list(e.raw_context.get("target_node_ids", [])),
            }
        )
    system = render("evidence.j2", attack_path=[], knowledge_hits=[], events=[])
    user = render(
        "evidence.j2",
        attack_path=attack_path,
        knowledge_hits=knowledge_hits,
        events=events_out,
    )
    raw = llm.complete_json(system=system, user=user, max_tokens=1024)
    candidate_ids = [e.event_id for e in events if not e.raw_context.get("benign", False)]
    evidence: list[EvidenceItem] = []
    for item in raw.get("evidence", []):
        # Normalize: strip empty ref lists, then backfill orphans with a real
        # event id from the window (docs/11 §3.9-2 no-orphans rule).
        cleaned = dict(item)
        for ref_key in ("event_ids", "graph_node_ids", "citation_refs"):
            if not cleaned.get(ref_key):
                cleaned.pop(ref_key, None)
        if not (
            cleaned.get("event_ids")
            or cleaned.get("graph_node_ids")
            or cleaned.get("citation_refs")
        ):
            if candidate_ids:
                cleaned["event_ids"] = (candidate_ids[0],)
            else:
                continue
        try:
            evidence.append(EvidenceItem(**cleaned))
        except Exception:
            continue
    state["evidence"] = evidence
    return dict(state)


# ---------------------------------------------------------------------------
# Node 7: risk_scoring (LLM; validator clamps later)
# ---------------------------------------------------------------------------


def risk_scoring(state: AnalystState, *, llm: Any) -> dict[str, Any]:
    system = render("risk.j2", attack_path=[])
    user = render("risk.j2", attack_path=state.get("attack_path_summary", []))
    raw = llm.complete_json(system=system, user=user, max_tokens=512)
    severity = raw.get("severity", "medium")
    confidence = float(raw.get("confidence", 0.5))
    state["risk"] = {
        "severity": severity,
        "confidence": confidence,
        "rationale": raw.get("rationale", ""),
    }
    return dict(state)


# ---------------------------------------------------------------------------
# Node 8: response_planning (LLM constrained to whitelist)
# ---------------------------------------------------------------------------


def response_planning(
    state: AnalystState,
    *,
    llm: Any,
    allowed_actions: list[str],
) -> dict[str, Any]:
    system = render("response_plan.j2", allowed_actions=allowed_actions, threat_summary="")
    user = render(
        "response_plan.j2",
        allowed_actions=allowed_actions,
        threat_summary=(state.get("triage") or {}).get("rationale_one_line", ""),
    )
    raw = llm.complete_json(system=system, user=user, max_tokens=512)
    actions: list[RecommendedAction] = []
    for item in raw.get("recommended_actions", []):
        try:
            actions.append(RecommendedAction(**item))
        except Exception:
            continue
    # whitelist filter (deterministic backstop)
    allowed = set(allowed_actions)
    actions = [a for a in actions if a.action_id in allowed][:5]
    state["recommended_actions"] = actions
    return dict(state)


# ---------------------------------------------------------------------------
# Node 9: validation_gate (deterministic — reuse Phase 5 validator)
# ---------------------------------------------------------------------------


def validation_gate(
    state: AnalystState,
    *,
    env: EnvironmentGraph,
    repo: GraphRepository,
    events: list[CanonicalEvent],
    allowed_action_ids: list[str],
) -> dict[str, Any]:
    triage = state.get("triage", {})
    evidence: list[EvidenceItem] = state.get("evidence", [])
    risk = state.get("risk", {})
    actions: list[RecommendedAction] = state.get("recommended_actions", [])
    threat_class_raw = triage.get("threat_class")
    if not threat_class_raw or threat_class_raw == "benign":
        state["validation"] = {"ok": False, "fatal": False, "reason": "benign-or-none"}
        return dict(state)
    # Attack path anchors from graph paths (best path to DATA).
    graph_paths = state.get("graph_paths", [])
    attack_path_anchors: list[dict[str, Any]] = []
    for p in graph_paths:
        if p.get("closes_at") != "DATA":
            continue
        nodes = p.get("nodes", [])
        for nid in nodes[:8]:
            node = env.get_node(nid)
            attack_path_anchors.append(
                {
                    "node_id": nid,
                    "label": node.label if node else nid,
                    "kind": node.kind.value if node else "ASSET",
                    "foothold_state": node.foothold_state.value if node else "clean",
                }
            )
        if attack_path_anchors:
            break

    cited: set[str] = set()
    for e in events:
        cited.update(e.raw_context.get("mitre_techniques", []))
    for hit in state.get("knowledge_hits", []):
        cited.add(hit.get("source_id", ""))

    try:
        proposal = DetectionProposal(
            simulation_id=state["simulation_id"],
            org_id=state["org_id"],
            window_seq=state.get("window_seq", 0),
            threat_class=ThreatClass(threat_class_raw),
            title=_title_for(threat_class_raw),
            severity=risk.get("severity", "medium"),
            confidence=float(risk.get("confidence", 0.5)),
            confidence_band="medium",
            attack_path=[_anchor_node(a) for a in attack_path_anchors],
            evidence=evidence,
            rationale=str(risk.get("rationale", "")),
            mitre_tactics=(),
            mitre_techniques=tuple(sorted(cited)),
            owasp_refs=(),
            recommended_actions=actions,
            source="ai",
        )
    except Exception:
        state["validation"] = {"ok": False, "fatal": True, "reason": "proposal-build-failed"}
        return dict(state)
    try:
        paths_for_validator = None
        outcome = validate(
            proposal,
            allowed_action_ids=allowed_action_ids,
            cited_mitre_techniques=sorted(cited),
            events_by_id={e.event_id: e for e in events},
            graph_paths=paths_for_validator,
        )
    except Exception:
        outcome = None
    if outcome is None or not outcome.result.ok:
        state["validation"] = {
            "ok": False,
            "fatal": bool(outcome and outcome.result.fatal),
            "reason": (outcome.result.reasons if outcome else ["validator-error"]),
            "clamps": (outcome.result.clamps_applied if outcome else []),
        }
        return dict(state)
    state["proposal"] = outcome.proposal
    state["validation"] = {"ok": True, "clamps": outcome.result.clamps_applied}
    return dict(state)


def _title_for(tc_raw: str) -> str:
    return {
        "sql_injection": "SQL injection against web service",
        "data_exfiltration": "Sensitive-data query exfiltration pattern",
        "credential_compromise": "Credential compromise following repeated failures",
        "credential_brute_force": "Credential brute-force burst from src IP",
        "malicious_package": "Malicious package lifecycle hook",
    }.get(tc_raw, f"Threat: {tc_raw}")


def _anchor_node(a: dict[str, Any]) -> Any:
    from cybersim.analyst.dto import AttackPathNode

    return AttackPathNode(
        node_id=a.get("node_id", ""),
        label=a.get("label", a.get("node_id", "")),
        kind=NodeKind(a.get("kind", "ASSET")),
        foothold_state=a.get("foothold_state", "clean"),
    )


# ---------------------------------------------------------------------------
# Node 10: rule_fallback (deterministic; docs/11 §3.11)
# ---------------------------------------------------------------------------


def rule_fallback(
    state: AnalystState, *, repo: GraphRepository, env: EnvironmentGraph
) -> dict[str, Any]:
    from cybersim.analyst.rules_fallback import analyze_window

    events: list[CanonicalEvent] = state.get("events", [])
    proposal = analyze_window(
        events,
        org_id=state["org_id"],
        simulation_id=state["simulation_id"],
        window_seq=state.get("window_seq", 0),
        env=env,
        graph_paths=_repo_paths(repo, state),
        simulator_id=state.get("simulator_id", "web"),
    )
    if proposal is not None:
        state["proposal"] = proposal
        state["degraded"] = True
    return dict(state)


def _repo_paths(repo: GraphRepository, state: AnalystState) -> list[Any]:
    try:
        src = None
        events: list[CanonicalEvent] = state.get("events", [])
        for e in events:
            if e.raw_context.get("source_node_id"):
                src = e.raw_context.get("source_node_id")
                break
        return repo.attack_paths(
            state["simulation_id"],
            src=src,
            dst_kinds=(NodeKind.DATA,),
            max_paths=5,
            hops=4,
        )
    except KeyError:
        return []


# ---------------------------------------------------------------------------
# Node 11: emit_detection (finalize)
# ---------------------------------------------------------------------------


def emit_detection(state: AnalystState) -> dict[str, Any]:
    proposal = state.get("proposal")
    if proposal is None:
        state["validation"] = {"ok": False, "fatal": False, "reason": "no-proposal"}
    return dict(state)
