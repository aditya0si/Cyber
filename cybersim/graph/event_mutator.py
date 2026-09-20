"""Event -> Graph Mutation Dispatcher (docs/02 §4, 02b §Part 1+2).

Rules:
- Every mutation goes through the `GraphRepository` protocol — NO direct
  access to NetworkX internals (`_require`, `.env`, `.overlay`).
- Overlay-layer node kinds (USER, ATTACK, EVENT) are used per 00 §Section 6
  and 02b §Step 2.
"""

from __future__ import annotations

import contextlib
from typing import Any

from cybersim.analyst.dto import RecommendedAction
from cybersim.events.schema import CanonicalEvent
from cybersim.graph.repo import GraphRepository
from cybersim.graph.types import (
    FootholdState,
    GraphNode,
    NodeKind,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _ensure_node(
    repo: GraphRepository,
    sim_id: str,
    node_id: str,
    kind: NodeKind,
    label: str,
    attrs: dict[str, Any] | None = None,
    foothold_state: FootholdState = FootholdState.CLEAN,
) -> None:
    """Upsert a node only if it does not already exist."""
    if repo.get_node(sim_id, node_id) is None:
        repo.upsert_node(
            sim_id,
            GraphNode(
                node_id=node_id,
                kind=kind,
                type=None,
                label=label,
                attrs=attrs or {},
                foothold_state=foothold_state,
            ),
        )


# ── main dispatcher ───────────────────────────────────────────────────────────


def apply_event_to_graph(
    event: CanonicalEvent,
    repo: GraphRepository,
    sim_id: str,
) -> None:
    """Mutate the attack graph based on a single CanonicalEvent.

    All mutations go through the ``GraphRepository`` protocol.  Direct
    NetworkX access is strictly forbidden here.
    """

    # ── Attacker source node (NETWORK_ZONE) ──────────────────────────────────
    attacker_id = f"attacker_{event.source_ip}"
    _ensure_node(repo, sim_id, attacker_id, NodeKind.NETWORK_ZONE, f"Attacker ({event.source_ip})")

    # ── EVENT overlay node for this specific event ────────────────────────────
    event_node_id = f"event_{event.event_id}"
    _ensure_node(
        repo,
        sim_id,
        event_node_id,
        NodeKind.EVENT,
        f"Event ({event.event_type})",
        attrs={"event_type": event.event_type, "severity": event.severity},
    )

    # ── Per-event-type mutations ──────────────────────────────────────────────

    if event.event_type == "LOGIN_FAILED":
        _handle_login_failed(event, repo, sim_id, event_node_id)

    elif event.event_type == "LOGIN_SUCCESS":
        _handle_login_success(event, repo, sim_id, event_node_id)

    elif event.event_type == "PRIVILEGE_ESCALATION":
        _handle_privilege_escalation(event, repo, sim_id)

    elif event.event_type == "DB_ACCESS":
        _handle_db_access(event, repo, sim_id)

    elif event.event_type == "DATA_TRANSFER":
        _handle_data_transfer(event, repo, sim_id)


def _handle_login_failed(
    event: CanonicalEvent,
    repo: GraphRepository,
    sim_id: str,
    event_node_id: str,
) -> None:
    """LOGIN_FAILED → ATTACK node (brute_force) with attempt count."""
    attack_node_id = f"attack_bruteforce_{event.target_asset}"
    existing = repo.get_node(sim_id, attack_node_id)
    if existing is not None:
        # Increment attempt counter via upsert with updated attrs
        new_attrs = dict(existing.attrs)
        new_attrs["attempt_count"] = new_attrs.get("attempt_count", 0) + 1
        repo.upsert_node(
            sim_id,
            GraphNode(
                node_id=attack_node_id,
                kind=NodeKind.ATTACK,
                type=None,
                label="Attack (brute_force)",
                attrs=new_attrs,
                foothold_state=existing.foothold_state,
            ),
        )
    else:
        repo.upsert_node(
            sim_id,
            GraphNode(
                node_id=attack_node_id,
                kind=NodeKind.ATTACK,
                type=None,
                label="Attack (brute_force)",
                attrs={"attempt_count": 1, "attack_type": "brute_force"},
            ),
        )
        # Attacker --LAUNCHED--> Attack (anchors the attack path origin)
        repo.add_overlay_edge(
            sim_id,
            kind="LAUNCHED",
            from_id=f"attacker_{event.source_ip}",
            to_id=attack_node_id,
            evidence_event_id=event.event_id,
        )
        # Event --INDICATES--> Attack
        repo.add_overlay_edge(
            sim_id,
            kind="INDICATES",
            from_id=event_node_id,
            to_id=attack_node_id,
            evidence_event_id=event.event_id,
        )
        # Attack --TARGETS--> Service (target_asset node)
        repo.add_overlay_edge(
            sim_id,
            kind="TARGETS",
            from_id=attack_node_id,
            to_id=event.target_asset,
            evidence_event_id=event.event_id,
        )


def _handle_login_success(
    event: CanonicalEvent,
    repo: GraphRepository,
    sim_id: str,
    event_node_id: str,
) -> None:
    """LOGIN_SUCCESS → USER node (compromised account)."""
    user_node_id = f"user_{event.actor}"
    if repo.get_node(sim_id, user_node_id) is None:
        repo.upsert_node(
            sim_id,
            GraphNode(
                node_id=user_node_id,
                kind=NodeKind.USER,
                type=None,
                label=f"User ({event.actor})",
                foothold_state=FootholdState.COMPROMISED,
                attrs={"status": "compromised", "account_id": event.actor},
            ),
        )

    attack_node_id = f"attack_bruteforce_{event.target_asset}"
    # Attack --RESULTED_IN--> User
    repo.add_overlay_edge(
        sim_id,
        kind="RESULTED_IN",
        from_id=attack_node_id,
        to_id=user_node_id,
        evidence_event_id=event.event_id,
    )
    # User --USES--> Service
    repo.add_overlay_edge(
        sim_id,
        kind="USES",
        from_id=user_node_id,
        to_id=event.target_asset,
        evidence_event_id=event.event_id,
    )


def _handle_privilege_escalation(
    event: CanonicalEvent,
    repo: GraphRepository,
    sim_id: str,
) -> None:
    """PRIVILEGE_ESCALATION → update User node, create/link Credential."""
    user_node_id = f"user_{event.actor}"
    existing = repo.get_node(sim_id, user_node_id)
    if existing is not None:
        new_attrs = dict(existing.attrs)
        new_attrs["privilege"] = "admin"
        repo.upsert_node(
            sim_id,
            GraphNode(
                node_id=user_node_id,
                kind=existing.kind,
                type=existing.type,
                label=existing.label,
                attrs=new_attrs,
                foothold_state=existing.foothold_state,
            ),
        )

    # Ensure admin CREDENTIAL node
    cred_node_id = "cred_admin"
    _ensure_node(repo, sim_id, cred_node_id, NodeKind.CREDENTIAL, "Credential (admin)")

    # User --GAINED--> Credential
    repo.add_overlay_edge(
        sim_id,
        kind="GAINED",
        from_id=user_node_id,
        to_id=cred_node_id,
        evidence_event_id=event.event_id,
    )

    # Mark target service as compromised if it exists
    with contextlib.suppress(KeyError):
        repo.update_foothold(sim_id, event.target_asset, FootholdState.COMPROMISED)


def _handle_db_access(
    event: CanonicalEvent,
    repo: GraphRepository,
    sim_id: str,
) -> None:
    """DB_ACCESS → User --ACCESSED--> Asset(database), mark at_risk."""
    user_node_id = f"user_{event.actor}"
    _ensure_node(
        repo,
        sim_id,
        user_node_id,
        NodeKind.USER,
        f"User ({event.actor})",
    )

    # User --ACCESSED--> database node
    repo.add_overlay_edge(
        sim_id,
        kind="ACCESSED",
        from_id=user_node_id,
        to_id=event.target_asset,
        evidence_event_id=event.event_id,
    )

    # Mark target node at_risk
    with contextlib.suppress(KeyError):
        repo.update_foothold(
            sim_id,
            event.target_asset,
            FootholdState.COMPROMISED,
            flags={"status": "at_risk"},
        )


def _handle_data_transfer(
    event: CanonicalEvent,
    repo: GraphRepository,
    sim_id: str,
) -> None:
    """DATA_TRANSFER → mark target as exfiltration_suspected."""
    with contextlib.suppress(KeyError):
        repo.update_foothold(
            sim_id,
            event.target_asset,
            FootholdState.COMPROMISED,
            flags={"status": "exfiltration_suspected"},
        )


# ── response actions (PROTOCOL-ONLY, no direct NetworkX access) ───────────────


def apply_response_actions(
    repo: GraphRepository,
    sim_id: str,
    actions: list[RecommendedAction],
) -> None:
    """Apply containment actions. Every mutation goes through the protocol.

    No direct NetworkX access, no ``_require``, no ``.env``/``.overlay``.
    """
    for action in actions:
        if action.action_id == "isolate_account":
            _isolate_accounts(repo, sim_id)
        elif action.action_id == "revoke_sessions":
            _revoke_sessions(repo, sim_id)
        elif action.action_id == "block_database":
            _block_database(repo, sim_id)
        elif action.action_id == "rotate_credentials":
            _rotate_credentials(repo, sim_id)
        elif action.action_id in ("block_source_ip", "rate_limit_endpoint", "quarantine_host"):
            # Generic: mark all compromised NETWORK_ZONE, ASSET or USER nodes contained
            _quarantine_compromised(repo, sim_id)


def _isolate_accounts(repo: GraphRepository, sim_id: str) -> None:
    """Mark all compromised USER nodes as isolated via upsert_node."""
    for node in repo.find_nodes_by_kind(sim_id, NodeKind.USER):
        if node.foothold_state == FootholdState.COMPROMISED:
            new_attrs = dict(node.attrs)
            new_attrs["status"] = "isolated"
            repo.upsert_node(
                sim_id,
                GraphNode(
                    node_id=node.node_id,
                    kind=node.kind,
                    type=node.type,
                    label=node.label,
                    attrs=new_attrs,
                    foothold_state=FootholdState.CONTAINED,
                ),
            )
    # Also cover CREDENTIAL-kind nodes that have "compromised" status (legacy compat)
    for node in repo.find_nodes_by_kind(sim_id, NodeKind.CREDENTIAL):
        if node.foothold_state == FootholdState.COMPROMISED:
            new_attrs = dict(node.attrs)
            new_attrs["status"] = "isolated"
            repo.upsert_node(
                sim_id,
                GraphNode(
                    node_id=node.node_id,
                    kind=node.kind,
                    type=node.type,
                    label=node.label,
                    attrs=new_attrs,
                    foothold_state=FootholdState.CONTAINED,
                ),
            )


def _revoke_sessions(repo: GraphRepository, sim_id: str) -> None:
    """Remove all USES overlay edges (session revocation)."""
    for edge_rec in repo.find_overlay_edges(sim_id, kind="USES"):
        with contextlib.suppress(KeyError):
            repo.remove_overlay_edge(sim_id, edge_rec["key"])


def _block_database(repo: GraphRepository, sim_id: str) -> None:
    """Mark all DATA nodes blocked and remove ACCESSED overlay edges."""
    # Mark DATA-kind nodes
    for node in repo.find_nodes_by_kind(sim_id, NodeKind.DATA):
        new_attrs = dict(node.attrs)
        new_attrs["status"] = "blocked"
        repo.upsert_node(
            sim_id,
            GraphNode(
                node_id=node.node_id,
                kind=node.kind,
                type=node.type,
                label=node.label,
                attrs=new_attrs,
                foothold_state=FootholdState.CONTAINED,
            ),
        )
    # Also mark ASSET nodes whose type is "database" or id contains "db"/"database"
    for node in repo.find_nodes_by_kind(sim_id, NodeKind.ASSET):
        nid = node.node_id
        if "database" in nid or "db" in nid or str(node.attrs.get("type", "")) == "database":
            new_attrs = dict(node.attrs)
            new_attrs["status"] = "blocked"
            repo.upsert_node(
                sim_id,
                GraphNode(
                    node_id=nid,
                    kind=node.kind,
                    type=node.type,
                    label=node.label,
                    attrs=new_attrs,
                    foothold_state=FootholdState.CONTAINED,
                ),
            )
    # Remove ACCESSED overlay edges
    for edge_rec in repo.find_overlay_edges(sim_id, kind="ACCESSED"):
        with contextlib.suppress(KeyError):
            repo.remove_overlay_edge(sim_id, edge_rec["key"])


def _quarantine_compromised(repo: GraphRepository, sim_id: str) -> None:
    """Generic: mark compromised NETWORK_ZONE, ASSET or USER nodes contained.

    Compromised USER accounts are the attacker's foothold — quarantine them
    as *isolated* so the dashboard visibly flips the account to a contained
    state (02 §Step 5: Isolate account → `status: isolated`).
    """
    for kind in (NodeKind.NETWORK_ZONE, NodeKind.ASSET, NodeKind.USER):
        for node in repo.find_nodes_by_kind(sim_id, kind):
            if node.foothold_state == FootholdState.COMPROMISED:
                flags = {"status": "isolated"} if kind == NodeKind.USER else None
                repo.update_foothold(sim_id, node.node_id, FootholdState.CONTAINED, flags=flags)


def _rotate_credentials(repo: GraphRepository, sim_id: str) -> None:
    """Mark all CREDENTIAL nodes rotated (invalidated) and contained."""
    for node in repo.find_nodes_by_kind(sim_id, NodeKind.CREDENTIAL):
        new_attrs = dict(node.attrs)
        new_attrs["status"] = "rotated"
        repo.upsert_node(
            sim_id,
            GraphNode(
                node_id=node.node_id,
                kind=node.kind,
                type=node.type,
                label=node.label,
                attrs=new_attrs,
                foothold_state=FootholdState.CONTAINED,
            ),
        )
