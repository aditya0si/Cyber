"""Event-level enumerations (docs/07 §1, docs/05 §6.1)."""

from __future__ import annotations

from enum import StrEnum


class EventCategory(StrEnum):
    NETWORK = "network"
    AUTH = "auth"
    HTTP = "http"
    DATABASE = "database"
    API = "api"
    HOST = "host"
    PACKAGE = "package"
    PROCESS = "process"
    SYSTEM = "system"
    ANALYST = "analyst"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @classmethod
    def rank(cls, sev: Severity) -> int:
        order = {
            cls.INFO: 0,
            cls.LOW: 1,
            cls.MEDIUM: 2,
            cls.HIGH: 3,
            cls.CRITICAL: 4,
        }
        return order[sev]


class AttackStage(StrEnum):
    RECON = "reconnaissance"
    INITIAL_ACCESS = "initial_access"
    EXECUTION = "execution"
    PERSISTENCE = "persistence"
    CRED_ACCESS = "credential_access"
    DISCOVERY = "discovery"
    LATERAL = "lateral_movement"
    PRIV_ESCAL = "privilege_escalation"
    EXFIL = "exfiltration"
    IMPACT = "impact"
    BENIGN = "benign"
