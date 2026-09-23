"""Ranked nodes CRUD routes delegated to the service layer."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from backend.api.dependencies import get_ranked_node_service
from backend.schemas import RankedNodeCreate, RankedNodeResponse, RankedNodeUpdate
from backend.services import RankedNodeService


router = APIRouter(prefix="/ranked-nodes", tags=["ranked-nodes"])


@router.post("/", response_model=RankedNodeResponse, status_code=status.HTTP_201_CREATED)
def create_ranked_node(
    data: RankedNodeCreate,
    service: Annotated[RankedNodeService, Depends(get_ranked_node_service)],
):
    return service.create(data)


@router.get("/", response_model=list[RankedNodeResponse])
def list_ranked_nodes(
    service: Annotated[RankedNodeService, Depends(get_ranked_node_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=0)] = 100,
):
    return service.get_all(skip=skip, limit=limit)


@router.get("/{id}", response_model=RankedNodeResponse)
def get_ranked_node(
    id: int,
    service: Annotated[RankedNodeService, Depends(get_ranked_node_service)],
):
    return service.get_by_id(id)


@router.patch("/{id}", response_model=RankedNodeResponse)
def update_ranked_node(
    id: int,
    data: RankedNodeUpdate,
    service: Annotated[RankedNodeService, Depends(get_ranked_node_service)],
):
    return service.update(id, data)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ranked_node(
    id: int,
    service: Annotated[RankedNodeService, Depends(get_ranked_node_service)],
) -> Response:
    service.delete(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
