"""Graph nodes CRUD routes delegated to the service layer."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from backend.api.dependencies import get_node_service
from backend.schemas import NodeCreate, NodeResponse, NodeUpdate
from backend.services import NodeService


router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.post("/", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
def create_node(
    data: NodeCreate,
    service: Annotated[NodeService, Depends(get_node_service)],
):
    return service.create(data)


@router.get("/", response_model=list[NodeResponse])
def list_nodes(
    service: Annotated[NodeService, Depends(get_node_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=0)] = 100,
):
    return service.get_all(skip=skip, limit=limit)


@router.get("/{id}", response_model=NodeResponse)
def get_node(
    id: int,
    service: Annotated[NodeService, Depends(get_node_service)],
):
    return service.get_by_id(id)


@router.patch("/{id}", response_model=NodeResponse)
def update_node(
    id: int,
    data: NodeUpdate,
    service: Annotated[NodeService, Depends(get_node_service)],
):
    return service.update(id, data)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(
    id: int,
    service: Annotated[NodeService, Depends(get_node_service)],
) -> Response:
    service.delete(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
