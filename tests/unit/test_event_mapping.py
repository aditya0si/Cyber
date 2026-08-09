"""Raw-to-canonical mapping dispatch (docs/07 §3)."""

from __future__ import annotations

import pytest

from cybersim.events.mapping import RAW_TYPE_TO_SUBTYPE, normalize_lookup
from cybersim.events.types import EventCategory


def test_lookup_for_web_sqli_carriers() -> None:
    assert normalize_lookup("web", "http.request") == (
        EventCategory.HTTP,
        "http_request",
    )
    assert normalize_lookup("web", "db.error") == (
        EventCategory.DATABASE,
        "db_error",
    )


def test_lookup_for_api_idor_carriers() -> None:
    assert normalize_lookup("api", "api.request") == (
        EventCategory.API,
        "api_request",
    )
    assert normalize_lookup("api", "api.data_response") == (
        EventCategory.API,
        "api_data_response",
    )


def test_lookup_for_network_recon_carriers() -> None:
    assert normalize_lookup("network", "net.scan_probe") == (
        EventCategory.NETWORK,
        "net_scan_probe",
    )
    assert normalize_lookup("network", "host.session") == (
        EventCategory.HOST,
        "host_session",
    )


def test_lookup_for_supply_chain_carriers() -> None:
    assert normalize_lookup("supply", "package.lifecycle.hook") == (
        EventCategory.PACKAGE,
        "package_lifecycle_hook",
    )
    assert normalize_lookup("supply", "process.env_exfil") == (
        EventCategory.PROCESS,
        "process_env_exfil",
    )


def test_lookup_for_executor_events() -> None:
    assert normalize_lookup("exec", "response.applied") == (
        EventCategory.SYSTEM,
        "response_applied",
    )


def test_lookup_rejects_unknown_raw_type() -> None:
    with pytest.raises(KeyError):
        normalize_lookup("web", "nonexistent.raw.type")
    with pytest.raises(KeyError):
        normalize_lookup("alien", "http.request")


def test_table_covers_each_canonical_category() -> None:
    categories_seen = {cat for cat, _ in RAW_TYPE_TO_SUBTYPE.values()}
    expected = {
        EventCategory.NETWORK,
        EventCategory.AUTH,
        EventCategory.HTTP,
        EventCategory.DATABASE,
        EventCategory.API,
        EventCategory.HOST,
        EventCategory.PACKAGE,
        EventCategory.PROCESS,
        EventCategory.SYSTEM,
        EventCategory.ANALYST,
    }
    missing = expected - categories_seen
    assert not missing, f"categories missing from RAW_TYPE_TO_SUBTYPE: {missing}"
