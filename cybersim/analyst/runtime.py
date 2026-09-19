"""AnalystRuntime — wires rule-fallback + LangGraph AI into one facade (docs/11).

Phase 5 shipped `mode="rules"` (rule-based fallback). Phase 6 adds `mode="ai"`
driven by the LangGraph state machine; any fatal validator failure routes to
the rule-based fallback (docs/11 §3.9 fail-fatal). The public API
(`ingest_window`) is unchanged across modes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cybersim.analyst.llm.client import LLMClient
from cybersim.analyst.validator import ValidationOutcome
from cybersim.events.schema import CanonicalEvent
from cybersim.graph.repo import GraphRepository
from cybersim.graph.types import EnvironmentGraph, NodeKind


@dataclass
class AnalystRuntime:
    """Ingests windows of canonical events and emits validated DetectionProposals.

    `mode="rules"` → Phase 5 rule-based fallback only.
    `mode="ai"`    → LangGraph analyst (Phase 6); falls back to rules on
                     fatal validation failure or LLM unavailability.
    """

    repo: GraphRepository
    simulator_id: str = "web"
    window_size: int = 32
    mode: str = "rules"
    llm: LLMClient | None = None
    knowledge_repo: Any = None
    allowed_action_ids: tuple[str, ...] = ()

    telemetry: dict[str, Any] = field(default_factory=dict)

    def ingest_window(
        self,
        window: list[CanonicalEvent],
        *,
        org_id: str,
        simulation_id: str,
        window_seq: int,
        env: EnvironmentGraph,
    ) -> ValidationOutcome | None:
        """Analyze one window; returns the STRONGEST validated outcome (or None).

        Prefer `ingest_window_all` when every distinct detection matters
        (missions, SOC feed).
        """
        outcomes = self.ingest_window_all(
            window,
            org_id=org_id,
            simulation_id=simulation_id,
            window_seq=window_seq,
            env=env,
        )
        if not outcomes:
            return None
        return max(
            outcomes,
            key=lambda o: _severity_rank(o.proposal.severity) if o.proposal is not None else -1,
        )

    def ingest_window_all(
        self,
        window: list[CanonicalEvent],
        *,
        org_id: str,
        simulation_id: str,
        window_seq: int,
        env: EnvironmentGraph,
    ) -> list[ValidationOutcome]:
        """Analyze one window; returns ALL validated outcomes (or [])."""
        if not window:
            return []

        if self.mode == "ai" and self.llm is not None and self.knowledge_repo is not None:
            outcome = self._ingest_via_langgraph(
                window,
                org_id=org_id,
                simulation_id=simulation_id,
                window_seq=window_seq,
                env=env,
            )
            if outcome is not None and outcome.result.ok:
                return [outcome]
            self.telemetry["ai_fallback_to_rules"] = (
                self.telemetry.get("ai_fallback_to_rules", 0) + 1
            )

        return self._ingest_via_rules_all(
            window,
            org_id=org_id,
            simulation_id=simulation_id,
            window_seq=window_seq,
            env=env,
        )

    # ------------------------------------------------------------------
    # Phase 5 rules path (preserved)
    # ------------------------------------------------------------------

    def _ingest_via_rules_all(
        self,
        window: list[CanonicalEvent],
        *,
        org_id: str,
        simulation_id: str,
        window_seq: int,
        env: EnvironmentGraph,
    ) -> list[ValidationOutcome]:
        from cybersim.analyst.response_catalog import allowed_actions
        from cybersim.analyst.rules_fallback import analyze_window
        from cybersim.analyst.validator import validate

        try:
            paths = self.repo.attack_paths(
                simulation_id,
                src=_first_source_node(window),
                dst_kinds=(NodeKind.DATA,),
                max_paths=5,
                hops=4,
            )
        except KeyError:
            paths = []

        proposals = analyze_window(
            window,
            org_id=org_id,
            simulation_id=simulation_id,
            window_seq=window_seq,
            env=env,
            graph_paths=paths,
            simulator_id=self.simulator_id,
        )
        if not proposals:
            self.telemetry["windows_without_detection"] = (
                self.telemetry.get("windows_without_detection", 0) + 1
            )
            return []

        # Validate every proposal; keep each one that passes (docs/11 §3.9).
        # Missions + the SOC feed surface the full set of chain stages.
        cited: set[str] = set()
        for ev in window:
            cited.update(ev.raw_context.get("mitre_techniques", []))
        accepted: list[ValidationOutcome] = []
        for proposal in proposals:
            outcome = validate(
                proposal,
                allowed_action_ids=allowed_actions(self.simulator_id),
                cited_mitre_techniques=sorted(cited),
                events_by_id={e.event_id: e for e in window},
                graph_paths=paths,
            )
            if not outcome.result.ok:
                self.telemetry["detections_rejected"] = (
                    self.telemetry.get("detections_rejected", 0) + 1
                )
                self.telemetry.setdefault("rejection_reasons", []).extend(outcome.result.reasons)
                continue
            accepted.append(outcome)
        if accepted:
            self.telemetry["detections_emitted"] = self.telemetry.get(
                "detections_emitted", 0
            ) + len(accepted)
        return accepted

    # ------------------------------------------------------------------
    # Phase 6 AI path (LangGraph)
    # ------------------------------------------------------------------

    def _ingest_via_langgraph(
        self,
        window: list[CanonicalEvent],
        *,
        org_id: str,
        simulation_id: str,
        window_seq: int,
        env: EnvironmentGraph,
    ) -> ValidationOutcome | None:
        from cybersim.analyst.graph import LangGraphAnalyst
        from cybersim.analyst.validator import validate

        analyst = LangGraphAnalyst(
            llm=self.llm,  # type: ignore[arg-type]
            repo=self.repo,
            env=env,
            knowledge_repo=self.knowledge_repo,
            simulator_id=self.simulator_id,
            allowed_action_ids=list(self.allowed_action_ids),
        )
        result = analyst.run(
            window,
            org_id=org_id,
            simulation_id=simulation_id,
            window_seq=window_seq,
        )
        proposal = result.get("proposal")
        if proposal is None:
            return None
        # Defense in depth: re-validate at the runtime boundary (docs/11 §3.9).
        cited: set[str] = set()
        for ev in window:
            cited.update(ev.raw_context.get("mitre_techniques", []))
        return validate(
            proposal,
            allowed_action_ids=list(self.allowed_action_ids),
            cited_mitre_techniques=sorted(cited),
            events_by_id={e.event_id: e for e in window},
        )


def _severity_rank(sev: Any) -> int:
    from cybersim.events.types import Severity

    try:
        return Severity.rank(Severity(sev.value if hasattr(sev, "value") else sev))
    except (ValueError, TypeError):
        return 0


def _first_source_node(window: list[CanonicalEvent]) -> str | None:
    for ev in window:
        if ev.raw_context.get("source_node_id"):
            return ev.raw_context.get("source_node_id")
    return None
