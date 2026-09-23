"""A client in the single current dataset, including isolated seeds."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, SmallInteger, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, EntityMixin

if TYPE_CHECKING:
    from backend.models.edge import Edge
    from backend.models.node_assessment import NodeAssessment
    from backend.models.ranked_node import RankedNode
    from backend.models.transaction import Transaction


class Node(EntityMixin, Base):
    __tablename__ = "nodes"
    __table_args__ = (CheckConstraint("depth BETWEEN 0 AND 4", name="depth_range"),)

    gid: Mapped[str] = mapped_column(String(32), unique=True)
    depth: Mapped[int] = mapped_column(SmallInteger)
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    outgoing_edges: Mapped[list[Edge]] = relationship(
        back_populates="source", foreign_keys="Edge.src", passive_deletes="all"
    )
    incoming_edges: Mapped[list[Edge]] = relationship(
        back_populates="destination", foreign_keys="Edge.dst", passive_deletes="all"
    )
    sent_transactions: Mapped[list[Transaction]] = relationship(
        back_populates="sender", foreign_keys="Transaction.src", passive_deletes="all"
    )
    received_transactions: Mapped[list[Transaction]] = relationship(
        back_populates="recipient", foreign_keys="Transaction.dst", passive_deletes="all"
    )
    assessment: Mapped[NodeAssessment | None] = relationship(
        back_populates="node", passive_deletes="all"
    )
    ranked_node: Mapped[RankedNode | None] = relationship(
        back_populates="node", passive_deletes="all"
    )
