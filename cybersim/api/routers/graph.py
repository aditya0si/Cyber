"""Attack-graph endpoints (docs/08 §4.6)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from cybersim.api.deps import CurrentUser, get_current_user
from cybersim.infra.errors import AppError, ErrorCode
from cybersim.platform.simulation.store import SimulationStore

router = APIRouter()


@router.get("/simulations/{sim_id}/graph")
async def get_graph(
    sim_id: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    request: Request,
) -> dict[str, Any]:
    store: SimulationStore = request.app.state.sim_store
    rec = store.get(current.org_id, sim_id)
    if rec is None:
        raise AppError(ErrorCode.SIM_NOT_FOUND, f"No simulation {sim_id!r}.")
    if rec.ctx is None or getattr(rec.ctx, "graph_ref", None) is None:
        # Reconstruct a view from the env template (Phase 4 MVP): we keep the
        # built EnvironmentGraph on the sim context.
        env_graph = getattr(rec, "_env_graph", None)
        if env_graph is None:
            from cybersim.simulation.web.simulator import build_environment_graph

            env_graph = build_environment_graph(rec.scenario_id)
            rec._env_graph = env_graph  # type: ignore[attr-defined]
    else:
        env_graph = rec.ctx.graph_ref

    nodes = [
        {
            "id": nid,
            "kind": n.kind.value,
            "type": n.type.value if n.type else None,
            "label": n.label,
            "attrs": n.attrs,
            "foothold_state": n.foothold_state.value,
        }
        for nid, n in env_graph.nodes.items()
    ]
    edges = [
        {
            "id": e.edge_id,
            "from": e.from_node,
            "to": e.to_node,
            "type": e.type.value,
            "attrs": e.attrs,
            "active": e.active,
        }
        for e in env_graph.edges.values()
    ]
    return {
        "simulation_id": sim_id,
        "seq": 0,
        "nodes": nodes,
        "edges": edges,
        "overlay_footholds": [],
    }
