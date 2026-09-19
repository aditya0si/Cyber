from datetime import datetime

import pytest
from pydantic import ValidationError

from cybersim.events.schema import CanonicalEvent


def test_canonical_event_has_exactly_8_fields():
    fields = set(CanonicalEvent.model_fields.keys())
    expected = {
        "event_id",
        "timestamp",
        "event_type",
        "severity",
        "source_ip",
        "target_asset",
        "actor",
        "raw_context",
    }
    assert fields == expected, f"Expected {expected}, got {fields}"


def test_valid_event_constructs():
    event = CanonicalEvent(
        event_id="123",
        timestamp=datetime.now().isoformat(),
        event_type="LOGIN_FAILED",
        severity="LOW",
        source_ip="1.2.3.4",
        target_asset="auth-api",
        actor="unknown",
    )
    assert event.event_id == "123"


def test_severity_must_be_one_of_enum():
    with pytest.raises(ValidationError):
        CanonicalEvent(
            event_id="123",
            timestamp=datetime.now().isoformat(),
            event_type="LOGIN_FAILED",
            severity="SUPER_HIGH",
            source_ip="1.2.3.4",
            target_asset="auth-api",
            actor="unknown",
        )


def test_timestamp_is_iso8601():
    with pytest.raises(ValidationError):
        CanonicalEvent(
            event_id="123",
            timestamp="not-iso8601",
            event_type="LOGIN_FAILED",
            severity="LOW",
            source_ip="1.2.3.4",
            target_asset="auth-api",
            actor="unknown",
        )
    # Valid
    CanonicalEvent(
        event_id="123",
        timestamp=datetime.now().isoformat(),
        event_type="LOGIN_FAILED",
        severity="LOW",
        source_ip="1.2.3.4",
        target_asset="auth-api",
        actor="unknown",
    )


def test_raw_context_accepts_arbitrary_dict():
    event = CanonicalEvent(
        event_id="123",
        timestamp=datetime.now().isoformat(),
        event_type="LOGIN_FAILED",
        severity="LOW",
        source_ip="1.2.3.4",
        target_asset="auth-api",
        actor="unknown",
        raw_context={"attempt_count": 5},
    )
    assert event.raw_context == {"attempt_count": 5}
    event2 = CanonicalEvent(
        event_id="123",
        timestamp=datetime.now().isoformat(),
        event_type="LOGIN_FAILED",
        severity="LOW",
        source_ip="1.2.3.4",
        target_asset="auth-api",
        actor="unknown",
        raw_context={},
    )
    assert event2.raw_context == {}


def test_missing_required_field_raises():
    with pytest.raises(ValidationError):
        CanonicalEvent(
            timestamp=datetime.now().isoformat(),
            event_type="LOGIN_FAILED",
            severity="LOW",
            source_ip="1.2.3.4",
            target_asset="auth-api",
            actor="unknown",
        )
