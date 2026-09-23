"""Business rules for a node's current role and metrics."""

from typing import Any

from backend.models import NodeAssessment
from backend.repositories import ClusterRepository, NodeRepository
from backend.schemas import NodeAssessmentCreate, NodeAssessmentUpdate
from backend.services.base import BaseService


class NodeAssessmentService(BaseService[NodeAssessment, NodeAssessmentCreate, NodeAssessmentUpdate]):
    create_schema = NodeAssessmentCreate

    def _validate(self, values: dict[str, Any], current: NodeAssessment | None) -> None:
        self._ensure_unique(current, gid=values["gid"])
        self._require_reference(NodeRepository(self.repository.session), gid=values["gid"])
        self._require_reference(
            ClusterRepository(self.repository.session), cluster_id=values["cluster_id"]
        )
