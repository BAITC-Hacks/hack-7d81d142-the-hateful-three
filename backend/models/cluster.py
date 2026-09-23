"""Cluster summary for the single current analysis."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, CheckConstraint, Integer, JSON, Numeric, String, Text
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, EntityMixin

if TYPE_CHECKING:
    from backend.models.node_assessment import NodeAssessment


class Cluster(EntityMixin, Base):
    __tablename__ = "clusters"
    __table_args__ = (
        CheckConstraint("n_nodes >= 0", name="n_nodes_nonnegative"),
        CheckConstraint("n_seed >= 0 AND n_seed <= n_nodes", name="n_seed_range"),
        CheckConstraint("sum_kzt_internal >= 0", name="sum_kzt_internal_nonnegative"),
    )

    cluster_id: Mapped[int] = mapped_column(Integer, unique=True)
    n_nodes: Mapped[int] = mapped_column(Integer)
    n_seed: Mapped[int] = mapped_column(Integer)
    sum_kzt_internal: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    top_gids: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(ARRAY(String(32)).with_variant(JSON(), "sqlite")), default=list
    )
    hypothesis: Mapped[str] = mapped_column(Text)

    assessments: Mapped[list[NodeAssessment]] = relationship(
        back_populates="cluster", passive_deletes="all"
    )
