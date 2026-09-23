"""Directed aggregate edges CRUD routes delegated to the service layer."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from backend.api.dependencies import get_edge_service
from backend.schemas import EdgeCreate, EdgeResponse, EdgeUpdate
from backend.services import EdgeService


router = APIRouter(prefix="/edges", tags=["edges"])


@router.post("/", response_model=EdgeResponse, status_code=status.HTTP_201_CREATED)
def create_edge(
    data: EdgeCreate,
    service: Annotated[EdgeService, Depends(get_edge_service)],
):
    return service.create(data)


@router.get("/", response_model=list[EdgeResponse])
def list_edges(
    service: Annotated[EdgeService, Depends(get_edge_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=0, le=100)] = 100,
):
    return service.get_all(skip=skip, limit=limit)


@router.get("/{id}", response_model=EdgeResponse)
def get_edge(
    id: int,
    service: Annotated[EdgeService, Depends(get_edge_service)],
):
    return service.get_by_id(id)


@router.patch("/{id}", response_model=EdgeResponse)
def update_edge(
    id: int,
    data: EdgeUpdate,
    service: Annotated[EdgeService, Depends(get_edge_service)],
):
    return service.update(id, data)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_edge(
    id: int,
    service: Annotated[EdgeService, Depends(get_edge_service)],
) -> Response:
    service.delete(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
