"""Raw-event → (category, subtype) dispatch table (docs/07 §3).

The Normalizer (Phase 3) keys this table on `(origin, raw_type)` to populate
the canonical event's `category` and `subtype`. Every Key slot below is
normative; the order groups by simulator origin for readability.
"""

from __future__ import annotations

from typing import Final

from cybersim.events.types import EventCategory

#: Mapping {(origin, raw_type): (EventCategory, carrier_subtype)}
#  Carrier subtypes describe the *event nature*, not the *semantic suspicion*
#  (which is layered by indicator detectors into separate subtypes like
#  `sql_injection_indicator`).
RAW_TYPE_TO_SUBTYPE: Final[dict[tuple[str, str], tuple[EventCategory, str]]] = {
    # ---- Web (origin="web") ----
    ("web", "http.request"): (EventCategory.HTTP, "http_request"),
    ("web", "http.error"): (EventCategory.HTTP, "http_error"),
    ("web", "db.query"): (EventCategory.DATABASE, "db_query"),
    ("web", "db.error"): (EventCategory.DATABASE, "db_error"),
    ("web", "auth.attempt"): (EventCategory.AUTH, "auth_attempt"),
    ("web", "auth.success"): (EventCategory.AUTH, "auth_success"),
    ("web", "session.created"): (EventCategory.AUTH, "session_created"),
    ("web", "payload.detected"): (EventCategory.HTTP, "payload_detected"),
    # ---- API (origin="api") ----
    ("api", "api.request"): (EventCategory.API, "api_request"),
    ("api", "api.authz"): (EventCategory.API, "api_authz"),
    ("api", "api.rate.window"): (EventCategory.API, "api_rate_window"),
    ("api", "api.data_response"): (EventCategory.API, "api_data_response"),
    # ---- Network (origin="network") ----
    ("network", "net.connection"): (EventCategory.NETWORK, "net_connection"),
    ("network", "net.scan_probe"): (EventCategory.NETWORK, "net_scan_probe"),
    ("network", "net.service_discovered"): (
        EventCategory.NETWORK,
        "net_service_discovered",
    ),
    ("network", "host.login_attempt"): (EventCategory.HOST, "host_login_attempt"),
    ("network", "host.session"): (EventCategory.HOST, "host_session"),
    ("network", "host.process_spawn"): (EventCategory.HOST, "host_process_spawn"),
    ("network", "net.lateral_hop"): (EventCategory.HOST, "net_lateral_hop"),
    ("network", "evidence.data_exfil"): (
        EventCategory.NETWORK,
        "evidence_data_exfil",
    ),
    # ---- Supply Chain (origin="supply") ----
    ("supply", "build.dependency_resolve"): (
        EventCategory.PACKAGE,
        "build_dependency_resolve",
    ),
    ("supply", "package.installed"): (EventCategory.PACKAGE, "package_installed"),
    ("supply", "package.lifecycle.hook"): (
        EventCategory.PACKAGE,
        "package_lifecycle_hook",
    ),
    ("supply", "process.exec"): (EventCategory.PROCESS, "process_exec"),
    ("supply", "process.env_exfil"): (EventCategory.PROCESS, "process_env_exfil"),
    ("supply", "net.connection"): (EventCategory.NETWORK, "net_connection"),
    # ---- Executor / system (origin="exec") ----
    ("exec", "response.applied"): (EventCategory.SYSTEM, "response_applied"),
    # ---- Analyst mirror (origin="analyst") ----
    ("analyst", "detection.created"): (EventCategory.ANALYST, "detection_created"),
}


def normalize_lookup(origin: str, raw_type: str) -> tuple[EventCategory, str]:
    """Return `(category, subtype)` for a raw event or raise KeyError."""
    key = (origin, raw_type)
    if key not in RAW_TYPE_TO_SUBTYPE:
        raise KeyError(f"no canonical mapping for raw event (origin={origin!r}, type={raw_type!r})")
    return RAW_TYPE_TO_SUBTYPE[key]
