"""Request and response schemas for a node's current analytical assessment."""

from pydantic import Field

from backend.models.enums import NodeRole
from backend.schemas.base import EntityResponse, Schema
from backend.schemas.types import Gid, KztAmount, Score


class NodeAssessmentBase(Schema):
    gid: Gid
    role: NodeRole
    role_score: Score
    cluster_id: int
    priority_score: Score
    evidence: str = Field(max_length=200)
    in_deg: int = Field(ge=0)
    out_deg: int = Field(ge=0)
    in_tx: int = Field(ge=0)
    out_tx: int = Field(ge=0)
    in_kzt: KztAmount
    out_kzt: KztAmount
    pagerank: float = Field(ge=0)
    pass_through: float | None = Field(default=None, ge=0)
    truncated_by_depth: bool


class NodeAssessmentCreate(NodeAssessmentBase):
    pass


class NodeAssessmentUpdate(Schema):
    gid: Gid | None = None
    role: NodeRole | None = None
    role_score: Score | None = None
    cluster_id: int | None = None
    priority_score: Score | None = None
    evidence: str | None = Field(default=None, max_length=200)
    in_deg: int | None = Field(default=None, ge=0)
    out_deg: int | None = Field(default=None, ge=0)
    in_tx: int | None = Field(default=None, ge=0)
    out_tx: int | None = Field(default=None, ge=0)
    in_kzt: KztAmount | None = None
    out_kzt: KztAmount | None = None
    pagerank: float | None = Field(default=None, ge=0)
    pass_through: float | None = Field(default=None, ge=0)
    truncated_by_depth: bool | None = None


class NodeAssessmentResponse(NodeAssessmentBase, EntityResponse):
    pass
