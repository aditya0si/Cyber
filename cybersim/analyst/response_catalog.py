"""Immutable response-action whitelist per simulator (docs/06 §3.6, docs/11 §3.8).

The rule-fallback uses the catalog to suggest *passive* actions (no
mutating_action_id rally — the executor still validates per-action params).
The full executor-side validation lives in Phase 4+.
"""

from __future__ import annotations

from collections.abc import Mapping

# Per-simulator allowed action ids (the validator (Phase 4) double-checks).
_ALLOWED: Mapping[str, tuple[str, ...]] = {
    "web": (
        "block_source_ip",
        "rate_limit_endpoint",
        "disable_endpoint",
        "patch_sqli",
        "rotate_credentials",
        "quarantine_host",
        "isolate_account",
        "revoke_sessions",
        "block_database",
    ),
    "api": (
        "block_source_ip",
        "rate_limit_route",
        "fix_idor_authz",
        "restrict_returned_fields",
        "revoke_token",
    ),
    "network": (
        "isolate_host",
        "block_egress",
        "rotate_credentials_host",
        "sinkhole_scan_domain",
    ),
    "supply": (
        "pin_dependency_version",
        "remove_malicious_package",
        "block_registry_source",
        "block_post_install_hook",
        "force_reproducible_build",
    ),
}


def allowed_actions(simulator_id: str) -> tuple[str, ...]:
    """Return the whitelisted action slug list for `simulator_id`."""
    if simulator_id not in _ALLOWED:
        return ()
    return _ALLOWED[simulator_id]


__all__ = ["allowed_actions"]
