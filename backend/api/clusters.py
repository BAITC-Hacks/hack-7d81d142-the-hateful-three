"""Analysis clusters CRUD routes delegated to the service layer."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from backend.api.dependencies import get_cluster_service
from backend.schemas import ClusterCreate, ClusterResponse, ClusterUpdate
from backend.services import ClusterService


router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.post("/", response_model=ClusterResponse, status_code=status.HTTP_201_CREATED)
def create_cluster(
    data: ClusterCreate,
    service: Annotated[ClusterService, Depends(get_cluster_service)],
):
    return service.create(data)


@router.get("/", response_model=list[ClusterResponse])
def list_clusters(
    service: Annotated[ClusterService, Depends(get_cluster_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=0)] = 100,
):
    return service.get_all(skip=skip, limit=limit)


@router.get("/{id}", response_model=ClusterResponse)
def get_cluster(
    id: int,
    service: Annotated[ClusterService, Depends(get_cluster_service)],
):
    return service.get_by_id(id)


@router.patch("/{id}", response_model=ClusterResponse)
def update_cluster(
    id: int,
    data: ClusterUpdate,
    service: Annotated[ClusterService, Depends(get_cluster_service)],
):
    return service.update(id, data)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cluster(
    id: int,
    service: Annotated[ClusterService, Depends(get_cluster_service)],
) -> Response:
    service.delete(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
