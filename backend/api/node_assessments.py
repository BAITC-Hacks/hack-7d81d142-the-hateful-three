"""Node assessments CRUD routes delegated to the service layer."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from backend.api.dependencies import get_node_assessment_service
from backend.schemas import NodeAssessmentCreate, NodeAssessmentResponse, NodeAssessmentUpdate
from backend.services import NodeAssessmentService


router = APIRouter(prefix="/node-assessments", tags=["node-assessments"])


@router.post("/", response_model=NodeAssessmentResponse, status_code=status.HTTP_201_CREATED)
def create_node_assessment(
    data: NodeAssessmentCreate,
    service: Annotated[NodeAssessmentService, Depends(get_node_assessment_service)],
):
    return service.create(data)


@router.get("/", response_model=list[NodeAssessmentResponse])
def list_node_assessments(
    service: Annotated[NodeAssessmentService, Depends(get_node_assessment_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=0, le=100)] = 100,
):
    return service.get_all(skip=skip, limit=limit)


@router.get("/{id}", response_model=NodeAssessmentResponse)
def get_node_assessment(
    id: int,
    service: Annotated[NodeAssessmentService, Depends(get_node_assessment_service)],
):
    return service.get_by_id(id)


@router.patch("/{id}", response_model=NodeAssessmentResponse)
def update_node_assessment(
    id: int,
    data: NodeAssessmentUpdate,
    service: Annotated[NodeAssessmentService, Depends(get_node_assessment_service)],
):
    return service.update(id, data)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node_assessment(
    id: int,
    service: Annotated[NodeAssessmentService, Depends(get_node_assessment_service)],
) -> Response:
    service.delete(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
