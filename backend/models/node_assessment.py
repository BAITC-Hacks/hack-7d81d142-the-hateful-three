"""One current role, cluster and set of metrics per node."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, EntityMixin
from backend.models.enums import NodeRole, node_role_type

if TYPE_CHECKING:
    from backend.models.cluster import Cluster
    from backend.models.node import Node


class NodeAssessment(EntityMixin, Base):
    __tablename__ = "node_assessments"
    __table_args__ = (
        CheckConstraint("role_score BETWEEN 0 AND 1", name="role_score_range"),
        CheckConstraint("priority_score BETWEEN 0 AND 1", name="priority_score_range"),
        CheckConstraint("length(evidence) <= 200", name="evidence_length"),
        CheckConstraint("in_deg >= 0 AND out_deg >= 0", name="degrees_nonnegative"),
        CheckConstraint("in_tx >= 0 AND out_tx >= 0", name="tx_counts_nonnegative"),
        CheckConstraint("in_kzt >= 0 AND out_kzt >= 0", name="amounts_nonnegative"),
        CheckConstraint("pagerank >= 0", name="pagerank_nonnegative"),
        CheckConstraint("pass_through IS NULL OR pass_through >= 0", name="pass_through_nonnegative"),
    )

    gid: Mapped[str] = mapped_column(
        String(32), ForeignKey("nodes.gid", ondelete="RESTRICT"), unique=True
    )
    role: Mapped[NodeRole] = mapped_column(node_role_type())
    role_score: Mapped[float] = mapped_column(Float)
    cluster_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clusters.cluster_id", ondelete="RESTRICT"), index=True
    )
    priority_score: Mapped[float] = mapped_column(Float, index=True)
    evidence: Mapped[str] = mapped_column(String(200))
    in_deg: Mapped[int] = mapped_column(Integer)
    out_deg: Mapped[int] = mapped_column(Integer)
    in_tx: Mapped[int] = mapped_column(Integer)
    out_tx: Mapped[int] = mapped_column(Integer)
    in_kzt: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    out_kzt: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    pagerank: Mapped[float] = mapped_column(Float)
    pass_through: Mapped[float | None] = mapped_column(Float, nullable=True)
    truncated_by_depth: Mapped[bool] = mapped_column(Boolean)

    node: Mapped[Node] = relationship(back_populates="assessment")
    cluster: Mapped[Cluster] = relationship(back_populates="assessments")
