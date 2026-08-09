"""Payload parsers â€” reject malformed (docs/07 Â§1.2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cybersim.events.payloads import (
    AuthAttemptPayload,
    DBErrorPayload,
    DBQueryPayload,
    HostLoginAttemptPayload,
    HTTPErrorPayload,
    HTTPRequestPayload,
    NetScanProbePayload,
    ProcessEnvExfilPayload,
)


def test_http_request_requires_method_and_path() -> None:
    with pytest.raises(ValidationError):
        HTTPRequestPayload(path="/login")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        HTTPRequestPayload(method="POST")  # type: ignore[call-arg]


def test_http_request_allows_extra() -> None:
    p = HTTPRequestPayload(
        method="POST",
        path="/api/login",
        body={"username": "' OR 1=1--"},
        sqli_pattern="tautology",
    )
    assert p.method == "POST"
    assert p.path == "/api/login"


def test_auth_attempt_requires_username_and_success() -> None:
    with pytest.raises(ValidationError):
        AuthAttemptPayload(username="alice")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        AuthAttemptPayload(success=True)  # type: ignore[call-arg]


def test_db_query_parameterized_defaults_true() -> None:
    p = DBQueryPayload(statement="SELECT 1")  # type: ignore[call-arg]
    assert p.parameterized is True


def test_db_error_status_unused_but_path_required() -> None:
    p = DBErrorPayload(message="syntax error")
    assert p.message == "syntax error"
    with pytest.raises(ValidationError):
        DBErrorPayload()  # type: ignore[call-arg]


def test_net_scan_probe_ports_tuple() -> None:
    p = NetScanProbePayload(target_host="10.0.0.5", ports=(22, 80, 5432))
    assert tuple(p.ports) == (22, 80, 5432)


def test_host_login_attempt_default_method_ssh() -> None:
    p = HostLoginAttemptPayload(host="10.0.0.5", account="admin", success=False)
    assert p.method == "ssh"


def test_rate_window_field_constraints() -> None:
    from cybersim.events.payloads import APIRateWindowPayload

    valid = APIRateWindowPayload(route="/api/auth", hits=10, denied=3)
    assert valid.denied == 3
    with pytest.raises(ValidationError):
        APIRateWindowPayload(route="/api/auth", hits=10, denied=-1)


def test_process_env_exfil_does_not_carry_values() -> None:
    # `ProcessEnvExfilPayload` carries patterns only â€” never the values
    # (docs/06 Â§6.4 safety promise).
    p = ProcessEnvExfilPayload(
        var_patterns_seen=("AWS_", "_TOKEN"), path_touched="/.config/credentials"
    )
    assert "AWS_" in p.var_patterns_seen
    assert p.path_touched is not None


def test_http_error_rejects_status_under_400() -> None:
    with pytest.raises(ValidationError):
        HTTPErrorPayload(path="/", status=200)
