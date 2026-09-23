"""Request and response schemas for graph nodes."""

from pydantic import Field

from backend.schemas.base import EntityResponse, Schema
from backend.schemas.types import Gid


class NodeBase(Schema):
    gid: Gid
    depth: int = Field(ge=0, le=4)
    is_seed: bool = False


class NodeCreate(NodeBase):
    pass


class NodeUpdate(Schema):
    gid: Gid | None = None
    depth: int | None = Field(default=None, ge=0, le=4)
    is_seed: bool | None = None


class NodeResponse(NodeBase, EntityResponse):
    pass
