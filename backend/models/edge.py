"""Directed aggregate of all transactions for one (src, dst) pair."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, EntityMixin

if TYPE_CHECKING:
    from backend.models.node import Node
    from backend.models.transaction import Transaction


class Edge(EntityMixin, Base):
    __tablename__ = "edges"
    __table_args__ = (
        UniqueConstraint("src", "dst", name="uq_edges_src_dst"),
        CheckConstraint("sum_kzt >= 0", name="sum_kzt_nonnegative"),
        CheckConstraint("n_tx > 0", name="n_tx_positive"),
        CheckConstraint("depth BETWEEN 1 AND 4", name="depth_range"),
    )

    src: Mapped[str] = mapped_column(String(32), ForeignKey("nodes.gid", ondelete="RESTRICT"))
    dst: Mapped[str] = mapped_column(
        String(32), ForeignKey("nodes.gid", ondelete="RESTRICT"), index=True
    )
    sum_kzt: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    n_tx: Mapped[int] = mapped_column(Integer)
    depth: Mapped[int] = mapped_column(SmallInteger)

    source: Mapped[Node] = relationship(back_populates="outgoing_edges", foreign_keys=[src])
    destination: Mapped[Node] = relationship(back_populates="incoming_edges", foreign_keys=[dst])
    transactions: Mapped[list[Transaction]] = relationship(back_populates="edge", viewonly=True)
