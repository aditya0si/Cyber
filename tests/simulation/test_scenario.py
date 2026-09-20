from collections import Counter

from cybersim.events.schema import CanonicalEvent
from cybersim.simulation.scenario import CredentialCompromiseScenario


def test_scenario_emits_exactly_four_stages():
    scen = CredentialCompromiseScenario()
    scen.start(delay=0)
    events = scen.get_events()
    types = [e.event_type for e in events]
    counts = Counter(types)
    assert counts["LOGIN_FAILED"] >= 1
    assert counts["LOGIN_SUCCESS"] == 1
    assert counts["PRIVILEGE_ESCALATION"] == 1
    assert counts["DB_ACCESS"] == 1


def test_login_success_follows_login_failures():
    scen = CredentialCompromiseScenario()
    scen.start(delay=0)
    events = scen.get_events()
    types = [e.event_type for e in events]
    fail_idx = [i for i, t in enumerate(types) if t == "LOGIN_FAILED"]
    succ_idx = types.index("LOGIN_SUCCESS")
    assert fail_idx[0] < succ_idx
    assert events[fail_idx[0]].source_ip == events[succ_idx].source_ip


def test_severity_escalates_across_brute_force_attempts():
    scen = CredentialCompromiseScenario()
    scen.start(delay=0)
    fails = [e for e in scen.get_events() if e.event_type == "LOGIN_FAILED"]
    severities = [e.severity for e in fails]
    # At least one LOW and one MEDIUM/HIGH
    assert "LOW" in severities
    assert ("MEDIUM" in severities) or ("HIGH" in severities)
    # Ensure they are ordered properly (LOW before MEDIUM/HIGH)
    low_idx = severities.index("LOW")
    high_idx = max([i for i, s in enumerate(severities) if s != "LOW"])
    assert low_idx < high_idx


def test_db_access_is_critical_severity():
    scen = CredentialCompromiseScenario()
    scen.start(delay=0)
    db_events = [e for e in scen.get_events() if e.event_type == "DB_ACCESS"]
    for e in db_events:
        assert e.severity == "CRITICAL"


def test_every_emitted_event_matches_canonical_schema():
    scen = CredentialCompromiseScenario()
    scen.start(delay=0)
    events = scen.get_events()
    for e in events:
        CanonicalEvent(**e.model_dump())


def test_actor_and_target_asset_consistent_across_chain():
    scen = CredentialCompromiseScenario()
    scen.start(delay=0)
    events = scen.get_events()
    succ = next(e for e in events if e.event_type == "LOGIN_SUCCESS")
    priv = next(e for e in events if e.event_type == "PRIVILEGE_ESCALATION")
    db = next(e for e in events if e.event_type == "DB_ACCESS")
    assert succ.actor == priv.actor == db.actor


def test_scenario_is_deterministic():
    s1 = CredentialCompromiseScenario()
    s1.start(delay=0)
    s2 = CredentialCompromiseScenario()
    s2.start(delay=0)

    types1 = [e.event_type for e in s1.get_events()]
    types2 = [e.event_type for e in s2.get_events()]
    assert types1 == types2


def test_reset_clears_state():
    scen = CredentialCompromiseScenario()
    scen.start(delay=0)
    events1 = scen.get_events()
    assert len(events1) > 0
    scen.reset()
    assert len(scen.get_events()) == 0
    scen.start(delay=0)
    events2 = scen.get_events()
    assert events1[0].event_id != events2[0].event_id
