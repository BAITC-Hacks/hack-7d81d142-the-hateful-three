"""Request and response schemas for stored ranking entries."""

from pydantic import Field

from backend.models.enums import NodeRole
from backend.schemas.base import EntityResponse, Schema
from backend.schemas.types import Gid, Score


class RankedNodeBase(Schema):
    rank: int = Field(default=1, ge=1, description="Assigned by the server; input is ignored")
    gid: Gid
    role: NodeRole
    priority_score: Score
    why: str


class RankedNodeCreate(RankedNodeBase):
    pass


class RankedNodeUpdate(Schema):
    rank: int | None = Field(default=None, ge=1, description="Assigned by the server; input is ignored")
    gid: Gid | None = None
    role: NodeRole | None = None
    priority_score: Score | None = None
    why: str | None = None


class RankedNodeResponse(RankedNodeBase, EntityResponse):
    pass
