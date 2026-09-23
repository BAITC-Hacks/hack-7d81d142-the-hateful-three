"""A source row; identical transfers remain distinct via row_id."""

from __future__ import annotations

from datetime import date as DateValue
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, EntityMixin

if TYPE_CHECKING:
    from backend.models.edge import Edge
    from backend.models.node import Node


class Transaction(EntityMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["src", "dst"], ["edges.src", "edges.dst"],
            name="fk_transactions_src_dst_edges", ondelete="RESTRICT",
        ),
        Index("ix_transactions_src_dst", "src", "dst"),
        CheckConstraint("row_id >= 0", name="row_id_nonnegative"),
        CheckConstraint("sum_kzt >= 0", name="sum_kzt_nonnegative"),
    )

    row_id: Mapped[int] = mapped_column(Integer, unique=True)
    src: Mapped[str] = mapped_column(String(32), ForeignKey("nodes.gid", ondelete="RESTRICT"))
    dst: Mapped[str] = mapped_column(
        String(32), ForeignKey("nodes.gid", ondelete="RESTRICT"), index=True
    )
    date: Mapped[DateValue] = mapped_column(Date, index=True)
    sum_kzt: Mapped[Decimal] = mapped_column(Numeric(20, 2))

    sender: Mapped[Node] = relationship(back_populates="sent_transactions", foreign_keys=[src])
    recipient: Mapped[Node] = relationship(back_populates="received_transactions", foreign_keys=[dst])
    # Derived from src/dst: write those fields (or sender/recipient), never a second pair.
    # Insert the aggregate edge before flushing its transactions.
    edge: Mapped[Edge] = relationship(back_populates="transactions", viewonly=True)
