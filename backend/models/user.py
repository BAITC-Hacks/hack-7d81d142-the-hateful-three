"""Registered identities; plaintext passwords are never persisted."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, EntityMixin


class User(EntityMixin, Base):
    __tablename__ = "users"
    # Deleted identities must not be reused while an old JWT can still exist.
    __table_args__ = {"sqlite_autoincrement": True}

    email: Mapped[str] = mapped_column(String(254), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
