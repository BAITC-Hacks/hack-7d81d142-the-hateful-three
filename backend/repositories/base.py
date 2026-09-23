"""SQLAlchemy persistence without HTTP, business rules or transaction ownership.

Writes flush, but never commit or roll back. The caller owns the Session and
must roll it back after a failed flush (normally via ``with session.begin()``).
All ID arguments refer to the technical primary key, not a business key.
"""

from collections.abc import Mapping
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.base import EntityMixin


ModelT = TypeVar("ModelT", bound=EntityMixin)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, entity_id: int) -> ModelT | None:
        return self.session.get(self.model, entity_id)

    def get_all(self, skip: int = 0, limit: int = 100) -> list[ModelT]:
        """Return a stable page ordered by primary key; limit=0 returns []."""
        for name, value in (("skip", skip), ("limit", limit)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        statement = select(self.model).order_by(self.model.id).offset(skip).limit(limit)
        return list(self.session.scalars(statement))

    def get_by_fields(self, **fields: Any) -> ModelT | None:
        """Look up a business key, including composite keys such as src/dst."""
        if not fields:
            raise ValueError("At least one lookup field is required")
        statement = select(self.model).filter_by(**fields).limit(1)
        return self.session.scalar(statement)

    def create(self, data: Mapping[str, Any]) -> ModelT:
        self._check_writable_fields(data)
        entity = self.model(**data)
        self.session.add(entity)
        self.session.flush()
        self.session.refresh(entity)
        return entity

    def update(self, entity_id: int, data: Mapping[str, Any]) -> ModelT | None:
        self._check_writable_fields(data)
        entity = self.get_by_id(entity_id)
        if entity is None:
            return None
        if data:
            for field, value in data.items():
                setattr(entity, field, value)
            self.session.flush()
            self.session.refresh(entity)
        return entity

    def delete(self, entity_id: int) -> bool:
        entity = self.get_by_id(entity_id)
        if entity is None:
            return False
        self.session.delete(entity)
        self.session.flush()
        return True

    def _check_writable_fields(self, data: Mapping[str, Any]) -> None:
        columns = set(self.model.__table__.columns.keys())
        writable = columns - {"id", "created_at", "updated_at"}
        invalid = set(data) - writable
        if invalid:
            raise ValueError(f"Fields cannot be written: {', '.join(sorted(invalid))}")
