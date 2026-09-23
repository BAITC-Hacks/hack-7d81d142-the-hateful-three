"""Request and response schemas for individual source transfers."""

from datetime import date as DateValue

from pydantic import Field

from backend.schemas.base import EntityResponse, Schema
from backend.schemas.types import Gid, KztAmount


class TransactionBase(Schema):
    row_id: int = Field(ge=0)
    src: Gid
    dst: Gid
    date: DateValue
    sum_kzt: KztAmount


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(Schema):
    row_id: int | None = Field(default=None, ge=0)
    src: Gid | None = None
    dst: Gid | None = None
    date: DateValue | None = None
    sum_kzt: KztAmount | None = None


class TransactionResponse(TransactionBase, EntityResponse):
    pass
