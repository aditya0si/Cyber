"""Threat taxonomy + MITRE ATT&CK mapping table (docs/05 §4.1, §4.2).

`ThreatClass` enumerates the canonical labels surfaced to the user. The
`MITREMapping` table is the deterministic two-way link between a ThreatClass
and MITRE tactics/techniques, used by:
  - The normalizer (docs/07 §2 step 7) to tag canonical events
  - The RAG knowledge lookup (docs/11 §3.6) to constrain query candidates
  - The anti-hallucination guard (docs/12 §6): the analyst may only surface
    MITRE IDs that RAG actually returned for this ThreatClass

This is the canonical source: any drift requires committing to a written
override in docs/05 §4.2.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class ThreatClass(StrEnum):
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    PATH_TRAVERSAL = "path_traversal"
    AUTH_BYPASS = "auth_bypass"
    CREDENTIAL_BRUTE_FORCE = "credential_brute_force"
    CREDENTIAL_COMPROMISE = "credential_compromise"
    IDOR = "idor"
    EXCESSIVE_DATA_EXPOSURE = "excessive_data_exposure"
    RATE_ABUSE = "rate_abuse"
    BROKEN_AUTH = "broken_auth"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    LATERAL_MOVEMENT = "lateral_movement"
    PORT_SCAN = "port_scan"
    SERVICE_DISCOVERY = "service_discovery"
    SUPPLY_CHAIN = "supply_chain"
    MALICIOUS_PACKAGE = "malicious_package"
    DATA_EXFILTRATION = "data_exfiltration"
    BENIGN = "benign"


@dataclass(frozen=True)
class MitreEntry:
    tactics: tuple[str, ...]
    techniques: tuple[str, ...]
    owasp_refs: tuple[str, ...] = ()


MITRE_MAP: Mapping[ThreatClass, MitreEntry] = {
    ThreatClass.SQL_INJECTION: MitreEntry(
        tactics=("TA0001",),
        techniques=("T1190",),
        owasp_refs=("A03:2021",),
    ),
    ThreatClass.XSS: MitreEntry(
        tactics=("TA0002",),
        techniques=("T1059.007",),
        owasp_refs=("A03:2021",),
    ),
    ThreatClass.PATH_TRAVERSAL: MitreEntry(
        tactics=("TA0001",),
        techniques=(
            "T1190",
            "T1053",
        ),
        owasp_refs=("A01:2021",),
    ),
    ThreatClass.AUTH_BYPASS: MitreEntry(
        tactics=("TA0001",),
        techniques=("T1190",),
        owasp_refs=("A07:2021",),
    ),
    ThreatClass.CREDENTIAL_BRUTE_FORCE: MitreEntry(
        tactics=("TA0006",),
        techniques=("T1110",),
        owasp_refs=("A07:2021",),
    ),
    ThreatClass.CREDENTIAL_COMPROMISE: MitreEntry(
        tactics=("TA0006", "TA0001"),
        techniques=("T1078",),
        owasp_refs=("A07:2021",),
    ),
    ThreatClass.IDOR: MitreEntry(
        tactics=("TA0001",),
        techniques=("T1190",),
        owasp_refs=("A01:2021",),
    ),
    ThreatClass.EXCESSIVE_DATA_EXPOSURE: MitreEntry(
        tactics=("TA0010",),
        techniques=("T1020",),
        owasp_refs=("A01:2021", "A04:2021"),
    ),
    ThreatClass.RATE_ABUSE: MitreEntry(
        tactics=("TA0006",),
        techniques=("T1110.001",),
        owasp_refs=("A07:2021",),
    ),
    ThreatClass.BROKEN_AUTH: MitreEntry(
        tactics=("TA0001", "TA0006"),
        techniques=("T1190", "T1078"),
        owasp_refs=("A07:2021",),
    ),
    ThreatClass.PRIVILEGE_ESCALATION: MitreEntry(
        tactics=("TA0004",),
        techniques=("T1068", "T1078.011"),
        owasp_refs=("A01:2021",),
    ),
    ThreatClass.LATERAL_MOVEMENT: MitreEntry(
        tactics=("TA0008",),
        techniques=("T1021",),
        owasp_refs=(),
    ),
    ThreatClass.PORT_SCAN: MitreEntry(
        tactics=("TA0007",),
        techniques=("T1046",),
    ),
    ThreatClass.SERVICE_DISCOVERY: MitreEntry(
        tactics=("TA0007",),
        techniques=("T1046",),
    ),
    ThreatClass.SUPPLY_CHAIN: MitreEntry(
        tactics=("TA0001",),
        techniques=("T1195", "T1195.002"),
        owasp_refs=("A08:2021",),
    ),
    ThreatClass.MALICIOUS_PACKAGE: MitreEntry(
        tactics=("TA0001", "TA0002"),
        techniques=("T1195", "T1195.003", "T1059"),
        owasp_refs=("A08:2021",),
    ),
    ThreatClass.DATA_EXFILTRATION: MitreEntry(
        tactics=("TA0010",),
        techniques=("T1041", "T1567"),
    ),
    ThreatClass.BENIGN: MitreEntry(
        tactics=(),
        techniques=(),
    ),
}


def mitre_entry(threat_class: ThreatClass) -> MitreEntry:
    """Return the deterministic MITRE/OWASP entry for `threat_class`."""
    if threat_class not in MITRE_MAP:
        raise KeyError(f"no MITRE mapping defined for ThreatClass={threat_class!r}")
    return MITRE_MAP[threat_class]


def threat_classes_for_technique(technique_id: str) -> list[ThreatClass]:
    """Reverse lookup: which ThreatClasses map (inter alia) to a given MITRE T-ID?"""
    return [tc for tc, entry in MITRE_MAP.items() if technique_id in entry.techniques]


def all_techniques() -> set[str]:
    """All known MITRE T-IDs declared in this map."""
    return {t for entry in MITRE_MAP.values() for t in entry.techniques}
