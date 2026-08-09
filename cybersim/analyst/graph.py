"""LangGraph state machine for the AI analyst (docs/11 §1, §3).

The graph mirrors the docs/11 §1 mermaid:

    START -> event_ingestion -> candidate_group -> threat_detection
        -> (is_suspicious? no -> benign closure -> END)
        -> (yes) graph_retrieval -> evidence_analysis -> rag_lookup
        -> risk_scoring -> response_planning -> validation_gate
        -> (ok) emit_detection -> END
        -> (fatal) rule_fallback -> emit_detection -> END
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from cybersim.analyst import nodes as analyst_nodes
from cybersim.analyst.llm.client import LLMClient
from cybersim.analyst.state import AnalystState
from cybersim.analyst.tools import AnalystTools
from cybersim.events.schema import CanonicalEvent
from cybersim.graph.repo_nx import NetworkXGraphRepository
from cybersim.graph.types import EnvironmentGraph


class LangGraphAnalyst:
    """Compiles the LangGraph pipeline once; runs per window."""

    def __init__(
        self,
        *,
        llm: LLMClient,
        repo: NetworkXGraphRepository,
        env: EnvironmentGraph,
        knowledge_repo: Any,
        simulator_id: str,
        allowed_action_ids: list[str],
    ) -> None:
        self._llm = llm
        self._repo = repo
        self._env = env
        self._knowledge = knowledge_repo
        self._simulator_id = simulator_id
        self._allowed = allowed_action_ids
        self._tools = AnalystTools(repo=repo, simulation_id="<set-per-run>")
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        g = StateGraph(AnalystState)

        g.add_node("event_ingestion", analyst_nodes.event_ingestion)
        g.add_node("candidate_group", analyst_nodes.candidate_group)
        g.add_node("threat_detection", self._wrap_threat_detection)
        g.add_node("graph_retrieval", self._wrap_graph_retrieval)
        g.add_node("evidence_analysis", self._wrap_evidence_analysis)
        g.add_node("rag_lookup", self._wrap_rag_lookup)
        g.add_node("risk_scoring", self._wrap_risk_scoring)
        g.add_node("response_planning", self._wrap_response_planning)
        g.add_node("validation_gate", self._wrap_validation_gate)
        g.add_node("emit_detection", analyst_nodes.emit_detection)
        g.add_node("rule_fallback", self._wrap_rule_fallback)

        g.add_edge(START, "event_ingestion")
        g.add_edge("event_ingestion", "candidate_group")
        g.add_edge("candidate_group", "threat_detection")
        g.add_conditional_edges(
            "threat_detection",
            self._route_after_triage,
            {"graph": "graph_retrieval", "benign": END},
        )
        g.add_edge("graph_retrieval", "evidence_analysis")
        g.add_edge("evidence_analysis", "rag_lookup")
        g.add_edge("rag_lookup", "risk_scoring")
        g.add_edge("risk_scoring", "response_planning")
        g.add_edge("response_planning", "validation_gate")
        g.add_conditional_edges(
            "validation_gate",
            self._route_after_validation,
            {"emit": "emit_detection", "fallback": "rule_fallback", "benign": END},
        )
        g.add_edge("rule_fallback", "emit_detection")
        g.add_edge("emit_detection", END)
        return g.compile()

    # ---- wrappers (bind per-run dependencies) --------------------------------

    def _wrap_threat_detection(self, state: AnalystState) -> dict[str, Any]:
        return analyst_nodes.threat_detection(state, llm=self._llm, tools=self._tools)

    def _wrap_graph_retrieval(self, state: AnalystState) -> dict[str, Any]:
        return analyst_nodes.graph_retrieval(state, tools=self._tools)

    def _wrap_evidence_analysis(self, state: AnalystState) -> dict[str, Any]:
        events: list[CanonicalEvent] = state.get("events", [])
        return analyst_nodes.evidence_analysis(state, llm=self._llm, events=events)

    def _wrap_rag_lookup(self, state: AnalystState) -> dict[str, Any]:
        return analyst_nodes.rag_lookup(state, knowledge_repo=self._knowledge)

    def _wrap_risk_scoring(self, state: AnalystState) -> dict[str, Any]:
        return analyst_nodes.risk_scoring(state, llm=self._llm)

    def _wrap_response_planning(self, state: AnalystState) -> dict[str, Any]:
        return analyst_nodes.response_planning(state, llm=self._llm, allowed_actions=self._allowed)

    def _wrap_validation_gate(self, state: AnalystState) -> dict[str, Any]:
        events: list[CanonicalEvent] = state.get("events", [])
        return analyst_nodes.validation_gate(
            state,
            env=self._env,
            repo=self._repo,
            events=events,
            allowed_action_ids=self._allowed,
        )

    def _wrap_rule_fallback(self, state: AnalystState) -> dict[str, Any]:
        return analyst_nodes.rule_fallback(state, repo=self._repo, env=self._env)

    # ---- routing ------------------------------------------------------------

    def _route_after_triage(self, state: AnalystState) -> Literal["graph", "benign"]:
        triage = state.get("triage", {})
        if triage.get("is_suspicious"):
            return "graph"
        return "benign"

    def _route_after_validation(self, state: AnalystState) -> Literal["emit", "fallback", "benign"]:
        validation = state.get("validation", {})
        if validation.get("ok"):
            return "emit"
        if validation.get("fatal"):
            return "fallback"
        return "benign"

    # ---- public entry --------------------------------------------------------

    def run(
        self, window: list[CanonicalEvent], *, org_id: str, simulation_id: str, window_seq: int
    ) -> dict[str, Any]:
        """Run the analyst over a window; returns the final state dict."""
        initial: AnalystState = {
            "org_id": org_id,
            "simulation_id": simulation_id,
            "window_seq": window_seq,
            "events": window,
            "simulator_id": self._simulator_id,
            "degraded": False,
        }
        self._tools = AnalystTools(repo=self._repo, simulation_id=simulation_id)
        result = self._graph.invoke(initial)
        return dict(result)
