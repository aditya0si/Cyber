import uuid
import datetime
import time
from typing import List
from cybersim.events.schema import CanonicalEvent

class CredentialCompromiseScenario:
    def __init__(self):
        self.events: List[CanonicalEvent] = []
        self.current_stage = 0

    def start(self, delay: float = 1.0):
        self.reset()
        stages = [
            self._stage_1_brute_force,
            self._stage_2_account_compromise,
            self._stage_3_privilege_escalation,
            self._stage_4_db_access,
        ]
        
        for stage in stages:
            stage_events = stage()
            for event in stage_events:
                self.events.append(event)
                time.sleep(delay)

    def reset(self):
        self.events = []
        self.current_stage = 0

    def get_events(self) -> List[CanonicalEvent]:
        return self.events

    def _now(self) -> str:
        return datetime.datetime.utcnow().isoformat() + "Z"

    def _stage_1_brute_force(self) -> List[CanonicalEvent]:
        events = []
        for i in range(3):
            events.append(CanonicalEvent(
                event_id=str(uuid.uuid4()),
                timestamp=self._now(),
                event_type="LOGIN_FAILED",
                severity="LOW" if i < 2 else "MEDIUM",
                source_ip="192.168.1.100",
                target_asset="auth-api",
                actor="unknown",
                raw_context={"attempt": i + 1, "reason": "invalid_credentials", "raw_type": "auth.attempt", "subtype": "unsanitized_auth_failure_burst"}
            ))
        return events

    def _stage_2_account_compromise(self) -> List[CanonicalEvent]:
        return [CanonicalEvent(
            event_id=str(uuid.uuid4()),
            timestamp=self._now(),
            event_type="LOGIN_SUCCESS",
            severity="HIGH",
            source_ip="192.168.1.100",
            target_asset="auth-api",
            actor="admin_service_account",
            raw_context={"auth_method": "password", "raw_type": "auth.success", "subtype": "auth_success_after_burst"}
        )]

    def _stage_3_privilege_escalation(self) -> List[CanonicalEvent]:
        return [CanonicalEvent(
            event_id=str(uuid.uuid4()),
            timestamp=self._now(),
            event_type="PRIVILEGE_ESCALATION",
            severity="HIGH",
            source_ip="192.168.1.100",
            target_asset="auth-api",
            actor="admin_service_account",
            raw_context={"new_role": "superuser"}
        )]

    def _stage_4_db_access(self) -> List[CanonicalEvent]:
        return [CanonicalEvent(
            event_id=str(uuid.uuid4()),
            timestamp=self._now(),
            event_type="DB_ACCESS",
            severity="CRITICAL",
            source_ip="192.168.1.100",
            target_asset="database",
            actor="admin_service_account",
            raw_context={"query": "SELECT * FROM users", "raw_type": "db.query", "subtype": "exfil_candidate_query"}
        )]
