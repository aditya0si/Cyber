"""Normalizer — raw → canonical event transformation (docs/07 §2).

The Normalizer is the SOLE legitimate producer of `CanonicalEvent`s. It:
  1. dedups by `raw.id` (idempotent re-delivery),
  2. assigns a strictly-increasing per-sim `sequence`,
  3. dispatches `(origin, raw_type)` → (category, subtype) via `mapping.py`,
  4. runs lightweight "indicator detectors" that *upgrade* the subtype when
     a payload matches a known attack signature (e.g., SQLi tautology in
     http.request body → subtype=`sql_injection_indicator`),
  5. derives MITRE/OWASP tags from the upgraded threat_class,
  6. attaches severity_hint per docs/07 §2.2 rubric,
  7. resolves graph node linkage from raw.node_ref + payload.common keys,
  8. computes a correlation_key (src_ip / cred_id / token_id / package).

The persistence + Redis consumer wiring live in `normalizer_tasks.py` (so
unit tests of the transform never touch a real bus or DB).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from cybersim.events.mapping import normalize_lookup
from cybersim.events.schema import CanonicalEvent, assemble
from cybersim.events.types import AttackStage, EventCategory, Severity
from cybersim.graph.mitre import MITRE_MAP, ThreatClass
from cybersim.graph.types import EnvironmentGraph
from cybersim.simulation.base import RawEvent

# ----- indicator detectors (docs/07 §3) --------------------------------

#: Subtype → ThreatClass upgrade path for "indicator" subtypes that capture the
#: *semantic suspicion* of a carrier event. When an indicator fires, we both
#: rewrite the subtype (e.g., `http_request` -> `sql_injection_indicator`) and
#: tag the event with the corresponding MITRE entry.
INDICATOR_TO_THREATCLASS: dict[str, ThreatClass] = {
    "sql_injection_indicator": ThreatClass.SQL_INJECTION,
    "auth_success_after_burst": ThreatClass.CREDENTIAL_COMPROMISE,
    "exfil_candidate_query": ThreatClass.DATA_EXFILTRATION,
    "unsanitized_auth_failure_burst": ThreatClass.CREDENTIAL_BRUTE_FORCE,
    "package_lifecycle_hook_suspicious": ThreatClass.MALICIOUS_PACKAGE,
    "env_exfil_pattern": ThreatClass.DATA_EXFILTRATION,
}

#: Stage mapping (docs/07 §2 step 6). Per-indicator shortcut; defaults to None
#: for non-attack carriers.
INDICATOR_TO_STAGE: dict[str, AttackStage] = {
    "sql_injection_indicator": AttackStage.INITIAL_ACCESS,
    "auth_success_after_burst": AttackStage.CRED_ACCESS,
    "exfil_candidate_query": AttackStage.EXFIL,
    "unsanitized_auth_failure_burst": AttackStage.CRED_ACCESS,
    "package_lifecycle_hook_suspicious": AttackStage.EXECUTION,
    "env_exfil_pattern": AttackStage.EXFIL,
}

#: Pre-compiled attack-signature regexes. Each `Indicator` returns the
#: upgraded subtype string or None (= keep carrier subtype).
_SQLO_PATTERN = re.compile(
    r"(\b(OR|UNION|SELECT|INSERT|UPDATE|DELETE)\b.*--"
    r"|'\s*OR\s*1=1|--|\bUNION\s+SELECT\b|;\s*DROP\b|;\s*SELECT\b|SLEEP\(|WAITFOR\s+DELAY|AND\s+1=1)",
    re.IGNORECASE,
)
_ENV_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*(=|_TOKEN|_KEY|_SECRET)")


@dataclass
class _BurstTracker:
    """Per-sim counters to detect auth.attempt followed by auth.success bursts."""

    last_fail_by_src: dict[str, list[int]] = field(default_factory=dict)

    def add_failure(self, src_ip: str, sim_time_ms: int) -> int:
        bucket = self.last_fail_by_src.setdefault(src_ip, [])
        bucket.append(sim_time_ms)
        # Drop events older than 60s
        cutoff = sim_time_ms - 60_000
        self.last_fail_by_src[src_ip] = [t for t in bucket if t >= cutoff]
        return len(self.last_fail_by_src[src_ip])


class Normalizer:
    """Idempotent transformer from RawEvent → CanonicalEvent (docs/07 §2)."""

    def __init__(self) -> None:
        self._seen_raw_ids: set[str] = set()
        self._seq_counters: dict[str, int] = {}
        self._burst_trkr: dict[str, _BurstTracker] = {}
        self._idor_trkr: dict[tuple[str, str], dict[str, int]] = {}

    def reset(self) -> None:
        self._seen_raw_ids.clear()
        self._seq_counters.clear()
        self._burst_trkr.clear()
        self._idor_trkr.clear()

    def normalize(
        self,
        raw: RawEvent,
        *,
        org_id: str,
        simulation_id: str,
        env: EnvironmentGraph,
        received_at_ms: int,
    ) -> CanonicalEvent | None:
        """Return the CanonicalEvent for `raw`, or None if deduped.

        Idempotent: re-normalizing the same raw.id returns None.
        """
        if raw.id in self._seen_raw_ids:
            return None
        self._seen_raw_ids.add(raw.id)

        try:
            category, carrier_subtype = normalize_lookup(raw.origin, raw.type)
        except KeyError:
            # Unknown raw types are dropped with a sentinel marker so the
            # pipeline can flag simulator drift via metrics (Phase 9).
            return self._canonical_sentinel(raw, org_id, simulation_id, received_at_ms)

        subtype, threat_class = self._detect_indicator(raw, carrier_subtype)
        mitre: tuple[str, ...] = ()
        owasp: tuple[str, ...] = ()
        if threat_class is not None:
            entry = MITRE_MAP[threat_class]
            mitre = entry.tactics + entry.techniques
            owasp = entry.owasp_refs

        severity_hint = self._severity_hint(raw, subtype, threat_class)
        attack_stage = INDICATOR_TO_STAGE.get(subtype)

        target_nodes, via_edges = self._link_graph(raw, env)
        source_node = self._source_node(env)

        corr_key = self._correlation_key(raw, env)

        seq = self._next_seq(simulation_id)
        return assemble(
            event_id=raw.id,
            simulation_id=simulation_id,
            org_id=org_id,
            sequence=seq,
            sim_time_ms=raw.sim_time_ms,
            received_at_ms=received_at_ms,
            origin=raw.origin,
            raw_type=raw.type,
            category=category,
            subtype=subtype,
            severity_hint=severity_hint,
            attack_stage=attack_stage,
            target_node_ids=tuple(target_nodes),
            source_node_id=source_node,
            via_edge_ids=tuple(via_edges),
            mitre_tactics=tuple(t for t in mitre if t.startswith("TA")),
            mitre_techniques=tuple(
                t for t in mitre if t.startswith("T") and not t.startswith("TA")
            ),
            owasp_refs=owasp,
            payload=_scrub_payload(raw.payload),
            raw_ref=raw.id,
            correlation_key=corr_key,
            benign=bool(raw.benign),
        )

    # ----- public: stream helper -----------------------------------------

    def normalize_many(
        self,
        raws: Iterator[RawEvent],
        *,
        org_id: str,
        simulation_id: str,
        env: EnvironmentGraph,
        received_at_ms_fn: Any = lambda: 0,
    ) -> Iterator[CanonicalEvent]:
        for raw in raws:
            ce = self.normalize(
                raw,
                org_id=org_id,
                simulation_id=simulation_id,
                env=env,
                received_at_ms=int(received_at_ms_fn()),
            )
            if ce is not None:
                yield ce

    # ----- internals ------------------------------------------------------

    def _detect_indicator(
        self, raw: RawEvent, carrier_subtype: str
    ) -> tuple[str, ThreatClass | None]:
        """Apply pattern detectors; return (upgraded_subtype, threat_class_or_None)."""
        if raw.benign:
            return carrier_subtype, None

        # SQLi indicator on http.request payloads
        if raw.origin == "web" and raw.type == "http.request":
            body = raw.payload.get("body")
            if isinstance(body, dict):
                # All bodies with a `sqli_pattern` attribute pre-marked by simulator
                pat = raw.payload.get("sqli_pattern")
                username = body.get("username") or body.get("email")
                if pat or (isinstance(username, str) and _SQLO_PATTERN.search(username)):
                    return "sql_injection_indicator", ThreatClass.SQL_INJECTION
        # SQLi indicator on db.query (non-parameterized + exfil flag)
        if (
            raw.origin == "web"
            and raw.type == "db.query"
            and not bool(raw.payload.get("parameterized", True))
            and (
                raw.payload.get("exfil_candidate")
                or _SQLO_PATTERN.search(str(raw.payload.get("statement", "")))
            )
        ):
            return "exfil_candidate_query", ThreatClass.DATA_EXFILTRATION
        # auth.attempt bursts (>=5/min from same src) flag a brute-force lead.
        if raw.origin == "web" and raw.type == "auth.attempt":
            src_ip = raw.src_ip or "unknown"
            trkr = self._burst_trkr.setdefault(src_ip, _BurstTracker())
            cnt = trkr.add_failure(src_ip, raw.sim_time_ms)
            if cnt >= 5:
                return "unsanitized_auth_failure_burst", ThreatClass.CREDENTIAL_BRUTE_FORCE
        # auth.success immediately after a recent burst on the same src ⇒ compromise.
        if raw.origin == "web" and raw.type == "auth.success":
            src_ip = raw.src_ip or "unknown"
            trkr = self._burst_trkr.setdefault(src_ip, _BurstTracker())
            recent_failures = len(trkr.last_fail_by_src.get(src_ip, []))
            if recent_failures > 0 and raw.payload.get("new_geo"):
                return "auth_success_after_burst", ThreatClass.CREDENTIAL_COMPROMISE
        # Supply-chain lifecycle hook + outbound net → malicious package lead.
        if (
            raw.origin == "supply"
            and raw.type == "package.lifecycle.hook"
            and (raw.payload.get("cmdline") or raw.payload.get("env_patterns_seen"))
        ):
            return "package_lifecycle_hook_suspicious", ThreatClass.MALICIOUS_PACKAGE
        if raw.origin == "supply" and raw.type == "process.env_exfil":
            return "env_exfil_pattern", ThreatClass.DATA_EXFILTRATION

        # API: IDOR — consecutive successful reads of incrementing object IDs
        # from the same src against a resource route (docs/06 §4.4).
        if raw.origin == "api" and raw.type == "api.request" and raw.payload.get("status") == 200:
            route = str(raw.payload.get("route", ""))
            if "{" in route:  # parameterized route e.g. /api/orders/{id}
                raw_id = raw.payload.get("route_params")
                src_ip = raw.src_ip or "unknown"
                if isinstance(raw_id, dict):
                    id_val = raw_id.get("id")
                    try:
                        obj_id = int(id_val) if id_val is not None else -1
                    except (TypeError, ValueError):
                        obj_id = -1
                    key = (src_ip, route)
                    tracker = self._idor_trkr.setdefault(key, {"last": -1, "streak": 0})
                    if obj_id == tracker["last"] + 1:
                        tracker["streak"] += 1
                    else:
                        tracker["streak"] = 1
                    tracker["last"] = obj_id
                    if tracker["streak"] >= 4:
                        return "idor_enumeration_indicator", ThreatClass.IDOR
        # API: brute-force on auth routes — >=5/min failed 401s from same src.
        if (
            raw.origin == "api"
            and raw.type == "api.request"
            and raw.payload.get("status") == 401
            and "auth" in str(raw.payload.get("route", ""))
        ):
            src_ip = raw.src_ip or "unknown"
            trkr = self._burst_trkr.setdefault(f"api:{src_ip}", _BurstTracker())
            cnt = trkr.add_failure(src_ip, raw.sim_time_ms)
            if cnt >= 5:
                return "unsanitized_auth_failure_burst", ThreatClass.CREDENTIAL_BRUTE_FORCE
        # API: rate-window abuse — sustained deny counts above threshold.
        if raw.origin == "api" and raw.type == "api.rate.window":
            denied = int(raw.payload.get("denied", 0))
            if denied >= 20:
                return "api_rate_abuse_indicator", ThreatClass.RATE_ABUSE

        # Network: port scan — SYN probes across >5 distinct ports, same src.
        if raw.origin == "network" and raw.type == "net.scan_probe":
            ports = raw.payload.get("ports") or ()
            if isinstance(ports, (tuple, list)) and len(ports) > 5:
                return "port_scan_indicator", ThreatClass.PORT_SCAN
        # Network: service discovery after scan (correlated, same src).
        if (
            raw.origin == "network"
            and raw.type == "net.service_discovered"
            and raw.payload.get("banner_fingerprint")
        ):
            return "service_discovery_indicator", ThreatClass.SERVICE_DISCOVERY
        # Network: lateral hop — attacker moving host-to-host.
        if raw.origin == "network" and raw.type == "net.lateral_hop":
            return "lateral_movement_indicator", ThreatClass.LATERAL_MOVEMENT
        # Network: bulk egress (exfiltration evidence).
        if raw.origin == "network" and raw.type == "evidence.data_exfil":
            return "data_exfil_indicator", ThreatClass.DATA_EXFILTRATION

        return carrier_subtype, None

    def _severity_hint(
        self,
        raw: RawEvent,
        subtype: str,
        threat_class: ThreatClass | None,
    ) -> Severity:
        if raw.benign:
            return Severity.INFO
        if subtype in {
            "auth_success_after_burst",
            "package_lifecycle_hook_suspicious",
            "env_exfil_pattern",
            "exfil_candidate_query",
            "data_exfil_indicator",
        }:
            return Severity.CRITICAL
        if subtype == "sql_injection_indicator":
            return Severity.HIGH
        if subtype == "unsanitized_auth_failure_burst":
            return Severity.MEDIUM
        # generic per docs/07 §2.2: subtype that maps to a threat_class with
        # MITRE technique → at least medium
        if threat_class is not None:
            return Severity.MEDIUM
        return Severity.INFO

    def _link_graph(self, raw: RawEvent, env: EnvironmentGraph) -> tuple[list[str], list[str]]:
        """Resolve raw.node_ref into canonical graph node ids + traverse edge ids."""
        targets: list[str] = []
        via_edges: list[str] = []
        if raw.node_ref and raw.node_ref in env.nodes:
            targets.append(raw.node_ref)
        # Look at other payload-embedded refs
        for key in (
            "target_node",
            "asset",
            "service",
            "host",
            "package",
            "store",
            "db",
            "account_id",
        ):
            val = raw.payload.get(key)
            if isinstance(val, str) and val in env.nodes and val not in targets:
                targets.append(val)
        # Walk env to find edges from raw.node_ref to the inferred targets
        for tid in list(targets):
            if raw.node_ref and raw.node_ref in env.nodes:
                for edge in env.edges.values():
                    if (
                        edge.from_node == raw.node_ref
                        and edge.to_node == tid
                        and edge.active
                        and edge.edge_id not in via_edges
                    ):
                        via_edges.append(edge.edge_id)
        return targets, via_edges

    def _source_node(self, env: EnvironmentGraph) -> str | None:
        """Return the internet-side attacker anchor if present.

        We match (in priority): a NETWORK_ZONE with `zone=internet`, any node
        labeled 'Internet'/'WAN', or any public ingress asset (gateway /
        load_balancer / bastion) carrying a `vip` attribute. The latter covers
        the realistic `web.finbank` env template (`lb1` LB with vip).
        """
        for nid, node in env.nodes.items():
            attrs = node.attrs or {}
            zone = attrs.get("zone")
            if zone == "internet" or node.label.lower() in ("internet", "wan"):
                return nid
            if (
                node.type
                and node.type.value in ("gateway", "load_balancer", "bastion")
                and attrs.get("vip")
            ):
                return nid
        return None

    def _correlation_key(self, raw: RawEvent, env: EnvironmentGraph) -> str | None:
        if raw.src_ip:
            return f"src_ip={raw.src_ip}"
        for key in ("cred_id", "token_id", "session_id", "package", "account_id"):
            val = raw.payload.get(key)
            if isinstance(val, str) and val:
                return f"{key}={val}"
        if raw.node_ref and raw.node_ref in env.nodes:
            return f"node={raw.node_ref}"
        return None

    def _next_seq(self, simulation_id: str) -> int:
        n = self._seq_counters.get(simulation_id, -1) + 1
        self._seq_counters[simulation_id] = n
        return n

    def _canonical_sentinel(
        self,
        raw: RawEvent,
        org_id: str,
        simulation_id: str,
        received_at_ms: int,
    ) -> CanonicalEvent:
        """Drop unknown raw types into a SYSTEM 'unknown_raw_type' event."""
        seq = self._next_seq(simulation_id)
        return assemble(
            event_id=raw.id,
            simulation_id=simulation_id,
            org_id=org_id,
            sequence=seq,
            sim_time_ms=raw.sim_time_ms,
            received_at_ms=received_at_ms,
            origin=raw.origin,
            raw_type=raw.type,
            category=EventCategory.SYSTEM,
            subtype=f"unknown_raw_type:{raw.origin}:{raw.type}",
            severity_hint=Severity.LOW,
            payload={"raw": raw.model_dump()},
            raw_ref=raw.id,
            correlation_key=None,
            benign=False,
        )


_SECRET_PATTERNS = re.compile(r"(?i)(password|secret|api[_-]?key|bearer)")


def _scrub_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip values whose KEY matches a secret pattern (docs/15 §8, docs/06 §6.4)."""
    clean: dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(k, str) and _SECRET_PATTERNS.search(k) and v:
            clean[k] = "***scrub***"
        else:
            clean[k] = v
    return clean


__all__ = ["Normalizer"]
