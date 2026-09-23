"""Bounded real subgraphs and details addressed by exact GID."""

from fastapi import APIRouter, Query
from sqlalchemy import select

from backend.api.dependencies import DbSession
from backend.models import Edge, Node, NodeAssessment
from backend.services.exceptions import NotFoundError

router = APIRouter(prefix="/graph", tags=["graph"])


def node_payload(node, assessment) -> dict:
    result = {"gid": node.gid, "depth": node.depth, "is_seed": node.is_seed,
              "role": None, "priority_score": 0, "cluster_id": None, "evidence": "Анализ ещё не выполнен."}
    if assessment:
        result.update({name: getattr(assessment, name) for name in (
            "role", "role_score", "priority_score", "cluster_id", "evidence", "in_deg", "out_deg",
            "in_tx", "out_tx", "in_kzt", "out_kzt", "pagerank", "pass_through", "truncated_by_depth",
        )})
        result["in_kzt"] = str(result["in_kzt"])
        result["out_kzt"] = str(result["out_kzt"])
    return result


@router.get("/nodes/{gid}")
def get_node(gid: str, session: DbSession) -> dict:
    row = session.execute(select(Node, NodeAssessment).outerjoin(
        NodeAssessment, Node.gid == NodeAssessment.gid,
    ).where(Node.gid == gid)).first()
    if row is None:
        raise NotFoundError("Node", gid)
    return node_payload(*row)


@router.get("")
def get_graph(
    session: DbSession, gid: str | None = None, cluster_id: int | None = None,
    hops: int = Query(default=1, ge=1, le=4),
    limit: int = Query(default=250, ge=1, le=500),
) -> dict:
    rows = list(session.execute(select(Node, NodeAssessment).outerjoin(
        NodeAssessment, Node.gid == NodeAssessment.gid,
    ).order_by(Node.gid)))
    by_gid = {node.gid: (node, assessment) for node, assessment in rows}
    edges = list(session.scalars(select(Edge).order_by(Edge.src, Edge.dst)))
    selected = set(by_gid)
    if cluster_id is not None:
        selected = {node.gid for node, a in rows if a and a.cluster_id == cluster_id}
    if gid is not None:
        if gid not in by_gid:
            raise NotFoundError("Node", gid)
        neighborhood = frontier = {gid}
        for _ in range(hops):
            next_frontier = {endpoint for edge in edges if edge.src in frontier or edge.dst in frontier
                             for endpoint in (edge.src, edge.dst)} - neighborhood
            neighborhood = neighborhood | next_frontier
            frontier = next_frontier
        selected &= neighborhood
    ordered = sorted(selected, key=lambda key: (
        key != gid, -(by_gid[key][1].priority_score if by_gid[key][1] else 0), key,
    ))
    visible = set(ordered[:limit])
    return {"nodes": [node_payload(*by_gid[key]) for key in ordered[:limit]],
            "edges": [{"src": e.src, "dst": e.dst, "sum_kzt": str(e.sum_kzt), "n_tx": e.n_tx}
                      for e in edges if e.src in visible and e.dst in visible],
            "total_nodes": len(selected), "shown_nodes": len(visible),
            "truncated": len(selected) > limit}
