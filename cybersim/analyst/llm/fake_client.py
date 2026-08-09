"""Deterministic Fake LLM client for tests + degraded demo (docs/20 §3).

Returns scripted JSON responses so the AI pipeline is testable without a
provider key; `mode` selects the canned scenario.
"""

from __future__ import annotations

from typing import Any


class FakeLLMClient:
    """Scripted structured-output client (tests + no-key dev runs)."""

    def __init__(
        self, *, script: list[dict[str, Any]] | None = None, model: str = "fake-1"
    ) -> None:
        self._script = list(script or [])
        self._calls = 0
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        if not self._script:
            return {}
        idx = self._calls % len(self._script)
        self._calls += 1
        entry = self._script[idx]
        if callable(entry):
            return dict(entry(user=user, system=system))
        return dict(entry)


def sql_injection_script() -> list[dict[str, Any]]:
    """Canned analyst responses for the SQLi FinBank scenario (deterministic)."""
    return [
        # triage (threat_detection)
        {
            "is_suspicious": True,
            "threat_class": "sql_injection",
            "rationale_one_line": "SQL metacharacters in login payload.",
            "confidence_signal": "high",
            "suggested_attack_path_node_ids": ["login_ep"],
        },
        # evidence analysis
        {
            "evidence": [
                {
                    "label": "repeated_failed_logins",
                    "kind": "event_burst",
                    "weight": 0.85,
                    "event_ids": [],
                    "summary": "repeated failed logins from src",
                },
                {
                    "label": "sqli_payload_signature_observed",
                    "kind": "behavioral_signature",
                    "weight": 0.9,
                    "event_ids": [],
                    "summary": "SQLi pattern in login body",
                },
                {
                    "label": "credential_state_compromised_account",
                    "kind": "credential_state",
                    "weight": 0.8,
                    "event_ids": [],
                    "summary": "successful login from new geo",
                },
            ],
        },
        # risk scoring
        {
            "severity": "high",
            "confidence": 0.91,
            "rationale": "Path to DATA within 2 hops.",
        },
        # response planning
        {
            "recommended_actions": [
                {
                    "action_id": "block_source_ip",
                    "order": 1,
                    "params": {},
                    "rationale": "Block the source IP.",
                },
                {
                    "action_id": "rate_limit_endpoint",
                    "order": 2,
                    "params": {},
                    "rationale": "Rate limit the login endpoint.",
                },
                {
                    "action_id": "rotate_credentials",
                    "order": 3,
                    "params": {},
                    "rationale": "Rotate exposed credentials.",
                },
            ],
        },
    ]
