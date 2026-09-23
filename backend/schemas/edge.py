"""Request and response schemas for aggregate directed edges."""

from pydantic import Field

from backend.schemas.base import EntityResponse, Schema
from backend.schemas.types import Gid, KztAmount


class EdgeBase(Schema):
    src: Gid
    dst: Gid
    sum_kzt: KztAmount
    n_tx: int = Field(gt=0)
    depth: int = Field(ge=1, le=4)


class EdgeCreate(EdgeBase):
    pass


class EdgeUpdate(Schema):
    src: Gid | None = None
    dst: Gid | None = None
    sum_kzt: KztAmount | None = None
    n_tx: int | None = Field(default=None, gt=0)
    depth: int | None = Field(default=None, ge=1, le=4)


class EdgeResponse(EdgeBase, EntityResponse):
    pass
