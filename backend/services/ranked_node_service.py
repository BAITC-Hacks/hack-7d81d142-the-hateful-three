"""A selected review queue kept consistent with current assessments."""

from typing import Any

from backend.models import RankedNode
from backend.repositories import NodeAssessmentRepository
from backend.schemas import RankedNodeCreate, RankedNodeUpdate
from backend.services.base import BaseService
from backend.services.exceptions import ValidationError


class RankedNodeService(BaseService[RankedNode, RankedNodeCreate, RankedNodeUpdate]):
    create_schema = RankedNodeCreate

    def create(self, data: RankedNodeCreate) -> RankedNode:
        self.repository.lock_ranking()
        # rank remains accepted for older clients, but the server assigns places.
        data = data.model_copy(update={"rank": self.repository.free_rank()})
        entity = super().create(data)
        self._write(self.repository.synchronize)
        return entity

    def update(self, entity_id: int, data: RankedNodeUpdate) -> RankedNode:
        self.repository.lock_ranking()
        entity = self.get_by_id(entity_id)
        if "rank" in data.model_fields_set:
            if data.rank is None:
                raise ValidationError("rank cannot be null")
            data = data.model_copy(update={"rank": entity.rank})
        entity = super().update(entity_id, data)
        self._write(self.repository.synchronize)
        return entity

    def delete(self, entity_id: int) -> None:
        self.repository.lock_ranking()
        super().delete(entity_id)
        self._write(self.repository.synchronize)

    def rebuild(self) -> list[RankedNode]:
        self.repository.lock_ranking()
        return self._write(lambda: self.repository.synchronize(include_missing=True))

    def _validate(self, values: dict[str, Any], current: RankedNode | None) -> None:
        self._ensure_unique(current, gid=values["gid"])
        assessments = NodeAssessmentRepository(self.repository.session)
        self._require_reference(assessments, gid=values["gid"])
        assessment = assessments.get_by_fields(gid=values["gid"])
        if values["role"] != assessment.role or values["priority_score"] != assessment.priority_score:
            raise ValidationError("role and priority_score must match the node assessment")
