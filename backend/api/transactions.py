"""Source transactions CRUD routes delegated to the service layer."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from backend.api.dependencies import get_transaction_service
from backend.schemas import TransactionCreate, TransactionResponse, TransactionUpdate
from backend.services import TransactionService


router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(
    data: TransactionCreate,
    service: Annotated[TransactionService, Depends(get_transaction_service)],
):
    return service.create(data)


@router.get("/", response_model=list[TransactionResponse])
def list_transactions(
    service: Annotated[TransactionService, Depends(get_transaction_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=0, le=100)] = 100,
):
    return service.get_all(skip=skip, limit=limit)


@router.get("/{id}", response_model=TransactionResponse)
def get_transaction(
    id: int,
    service: Annotated[TransactionService, Depends(get_transaction_service)],
):
    return service.get_by_id(id)


@router.patch("/{id}", response_model=TransactionResponse)
def update_transaction(
    id: int,
    data: TransactionUpdate,
    service: Annotated[TransactionService, Depends(get_transaction_service)],
):
    return service.update(id, data)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    id: int,
    service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> Response:
    service.delete(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
