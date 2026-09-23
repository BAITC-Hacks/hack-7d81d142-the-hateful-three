"""Stored snapshot of the current derived top_nodes.csv ranking."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, EntityMixin
from backend.models.enums import NodeRole, node_role_type

if TYPE_CHECKING:
    from backend.models.node import Node


class RankedNode(EntityMixin, Base):
    __tablename__ = "ranked_nodes"
    __table_args__ = (
        CheckConstraint("rank >= 1", name="rank_positive"),
        CheckConstraint("priority_score BETWEEN 0 AND 1", name="priority_score_range"),
    )

    rank: Mapped[int] = mapped_column(Integer, unique=True)
    gid: Mapped[str] = mapped_column(
        String(32), ForeignKey("nodes.gid", ondelete="RESTRICT"), unique=True
    )
    role: Mapped[NodeRole] = mapped_column(node_role_type())
    priority_score: Mapped[float] = mapped_column(Float)
    why: Mapped[str] = mapped_column(Text)

    node: Mapped[Node] = relationship(back_populates="ranked_node")
