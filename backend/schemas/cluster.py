"""Request and response schemas for analysis cluster summaries."""

from pydantic import Field

from backend.schemas.base import EntityResponse, Schema
from backend.schemas.types import Gid, KztAmount


class ClusterBase(Schema):
    cluster_id: int
    n_nodes: int = Field(ge=0)
    n_seed: int = Field(ge=0)
    sum_kzt_internal: KztAmount
    top_gids: list[Gid] = Field(default_factory=list)
    hypothesis: str


class ClusterCreate(ClusterBase):
    pass


class ClusterUpdate(Schema):
    cluster_id: int | None = None
    n_nodes: int | None = Field(default=None, ge=0)
    n_seed: int | None = Field(default=None, ge=0)
    sum_kzt_internal: KztAmount | None = None
    top_gids: list[Gid] | None = None
    hypothesis: str | None = None


class ClusterResponse(ClusterBase, EntityResponse):
    pass
