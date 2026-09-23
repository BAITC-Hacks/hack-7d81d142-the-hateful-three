"""Read or rebuild the review queue from saved node assessments."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from backend.api.dependencies import DbSession, get_ranked_node_service
from backend.models import NodeAssessment, RankedNode
from backend.models.enums import NodeRole
from backend.schemas import RankedNodeResponse
from backend.services import RankedNodeService

router = APIRouter(prefix="/ranking", tags=["ranking"])


@router.get("/search")
def search_ranking(
    session: DbSession, q: str = Query(default="", max_length=100),
    role: NodeRole | None = None, cluster_id: int | None = None,
    skip: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
    sort: Literal["rank", "gid", "role", "priority", "cluster"] = "rank",
    direction: Literal["asc", "desc"] = "asc",
) -> dict:
    stmt = select(RankedNode, NodeAssessment.cluster_id).outerjoin(
        NodeAssessment, RankedNode.gid == NodeAssessment.gid,
    )
    if q:
        stmt = stmt.where(RankedNode.gid.contains(q, autoescape=True))
    if role:
        stmt = stmt.where(RankedNode.role == role)
    if cluster_id is not None:
        stmt = stmt.where(NodeAssessment.cluster_id == cluster_id)
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    column = {"rank": RankedNode.rank, "gid": RankedNode.gid, "role": RankedNode.role,
              "priority": RankedNode.priority_score, "cluster": NodeAssessment.cluster_id}[sort]
    stmt = stmt.order_by(column.desc() if direction == "desc" else column.asc(), RankedNode.rank)
    return {"total": total, "skip": skip, "limit": limit, "items": [
        {"rank": row.rank, "gid": row.gid, "role": row.role.value,
         "priority_score": row.priority_score, "cluster_id": cluster, "evidence": row.why}
        for row, cluster in session.execute(stmt.offset(skip).limit(limit))
    ]}


@router.get("", response_model=list[RankedNodeResponse])
def ranking(
    service: Annotated[RankedNodeService, Depends(get_ranked_node_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=0, le=100)] = 100,
):
    return service.get_all(skip=skip, limit=limit)


@router.post("/rebuild")
def rebuild_ranking(service: Annotated[RankedNodeService, Depends(get_ranked_node_service)]):
    rows = service.rebuild()
    return {"ranked_nodes": len(rows)}
