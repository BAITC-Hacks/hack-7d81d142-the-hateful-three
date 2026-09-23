"""Business rules for a node's current role and metrics."""

from typing import Any

from backend.models import NodeAssessment
from backend.repositories import ClusterRepository, NodeRepository, RankedNodeRepository
from backend.schemas import NodeAssessmentCreate, NodeAssessmentUpdate
from backend.services.base import BaseService
from backend.services.exceptions import ValidationError
from backend.services.graph_semantics import is_depth_boundary


class NodeAssessmentService(BaseService[NodeAssessment, NodeAssessmentCreate, NodeAssessmentUpdate]):
    create_schema = NodeAssessmentCreate

    def create(self, data: NodeAssessmentCreate) -> NodeAssessment:
        ranking = RankedNodeRepository(self.repository.session)
        ranking.lock_ranking()
        entity = super().create(data)
        self._write(ranking.synchronize)
        return entity

    def update(self, entity_id: int, data: NodeAssessmentUpdate) -> NodeAssessment:
        ranking = RankedNodeRepository(self.repository.session)
        ranking.lock_ranking()
        old = self.get_by_id(entity_id)
        ranked = ranking.get_by_fields(gid=old.gid)
        derived_explanation = ranked is not None and ranked.why == old.evidence
        entity = super().update(entity_id, data)
        if derived_explanation:
            ranked.why = entity.evidence
        self._write(ranking.synchronize)
        return entity

    def delete(self, entity_id: int) -> None:
        ranking = RankedNodeRepository(self.repository.session)
        ranking.lock_ranking()
        super().delete(entity_id)
        self._write(ranking.synchronize)

    def _validate(self, values: dict[str, Any], current: NodeAssessment | None) -> None:
        self._ensure_unique(current, gid=values["gid"])
        self._require_reference(NodeRepository(self.repository.session), gid=values["gid"])
        self._require_reference(
            ClusterRepository(self.repository.session), cluster_id=values["cluster_id"]
        )
        node = NodeRepository(self.repository.session).get_by_fields(gid=values["gid"])
        if node.is_seed != (node.depth == 0):
            raise ValidationError("Node is_seed must be true exactly when depth is 0")
        expected = is_depth_boundary(self.repository.session, node.gid, node.depth)
        if values["truncated_by_depth"] != expected:
            raise ValidationError("truncated_by_depth must match depth 4 with no observed outgoing edges")
