"""Shared CRUD orchestration; subclasses implement entity-specific rules.

Services accept Create/Update schemas and return ORM entities. Update uses only
explicitly supplied fields, then validates the merged record against Create.
No commit/rollback is performed here. Database constraint errors become
ConflictError, but still require the caller to roll back its transaction.
"""

from collections.abc import Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError as SchemaValidationError
from sqlalchemy.exc import IntegrityError

from backend.repositories.base import BaseRepository, ModelT
from backend.services.exceptions import ConflictError, NotFoundError, ValidationError


CreateT = TypeVar("CreateT", bound=BaseModel)
UpdateT = TypeVar("UpdateT", bound=BaseModel)
ResultT = TypeVar("ResultT")


class BaseService(Generic[ModelT, CreateT, UpdateT]):
    create_schema: type[CreateT]

    def __init__(self, repository: BaseRepository[ModelT]) -> None:
        self.repository = repository

    def get_by_id(self, entity_id: int) -> ModelT:
        entity = self.repository.get_by_id(entity_id)
        if entity is None:
            raise NotFoundError(self.repository.model.__name__, entity_id)
        return entity

    def get_all(self, skip: int = 0, limit: int = 100) -> list[ModelT]:
        try:
            return self.repository.get_all(skip=skip, limit=limit)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def create(self, data: CreateT) -> ModelT:
        values = self._validated_values(data.model_dump())
        self._validate(values, current=None)
        return self._write(lambda: self.repository.create(values))

    def update(self, entity_id: int, data: UpdateT) -> ModelT:
        entity = self.get_by_id(entity_id)
        changes = data.model_dump(exclude_unset=True)
        values = {field: getattr(entity, field) for field in self.create_schema.model_fields}
        values.update(changes)
        values = self._validated_values(values)
        self._validate(values, current=entity)
        updated = self._write(
            lambda: self.repository.update(entity_id, {field: values[field] for field in changes})
        )
        if updated is None:
            raise NotFoundError(self.repository.model.__name__, entity_id)
        return updated

    def delete(self, entity_id: int) -> None:
        if not self._write(lambda: self.repository.delete(entity_id)):
            raise NotFoundError(self.repository.model.__name__, entity_id)

    def _validated_values(self, values: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.create_schema.model_validate(values).model_dump()
        except SchemaValidationError as exc:
            raise ValidationError(str(exc)) from exc

    def _validate(self, values: dict[str, Any], current: ModelT | None) -> None:
        """Check business rules before mutating a persistent entity."""

    def _ensure_unique(self, current: ModelT | None, **fields: Any) -> None:
        existing = self.repository.get_by_fields(**fields)
        if existing is not None and (current is None or existing.id != current.id):
            raise ConflictError(f"{self.repository.model.__name__} already exists: {fields!r}")

    @staticmethod
    def _require_reference(repository: BaseRepository, **fields: Any) -> None:
        if repository.get_by_fields(**fields) is None:
            raise NotFoundError(repository.model.__name__, fields)

    def _write(self, operation: Callable[[], ResultT]) -> ResultT:
        try:
            return operation()
        except IntegrityError as exc:
            # Constraints remain authoritative if another transaction wins a race
            # after the service's uniqueness/reference checks.
            raise ConflictError(
                f"{self.repository.model.__name__} change violates a database constraint "
                "(a duplicate key or a referenced record)."
            ) from exc
