"""Register entity CRUD routes and the remaining feature routers."""

from fastapi import APIRouter, Depends

from backend.api import (
    analysis,
    auth,
    clusters,
    dataset,
    edges,
    exports,
    graph,
    node_assessments,
    nodes,
    ranked_nodes,
    ranking,
    transactions,
)
from backend.api.dependencies import get_current_user


protected_router = APIRouter(dependencies=[Depends(get_current_user)])
protected_router.include_router(dataset.router)
protected_router.include_router(analysis.router)
protected_router.include_router(nodes.router)
protected_router.include_router(edges.router)
protected_router.include_router(transactions.router)
protected_router.include_router(node_assessments.router)
protected_router.include_router(ranked_nodes.router)
protected_router.include_router(ranking.router)
protected_router.include_router(graph.router)
protected_router.include_router(clusters.router)
protected_router.include_router(exports.router)

router = APIRouter()
router.include_router(auth.router)
router.include_router(protected_router)
