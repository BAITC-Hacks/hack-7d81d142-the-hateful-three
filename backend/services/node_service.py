"""Business rules for graph nodes."""

from typing import Any

from backend.models import Node
from backend.repositories import RankedNodeRepository
from backend.schemas import NodeCreate, NodeUpdate
from backend.services.base import BaseService
from backend.services.exceptions import ValidationError
from backend.services.graph_semantics import refresh_depth_boundary


class NodeService(BaseService[Node, NodeCreate, NodeUpdate]):
    create_schema = NodeCreate

    def _validate(self, values: dict[str, Any], current: Node | None) -> None:
        self._ensure_unique(current, gid=values["gid"])
        if values["is_seed"] != (values["depth"] == 0):
            raise ValidationError("is_seed must be true exactly when depth is 0")

    def update(self, entity_id: int, data: NodeUpdate) -> Node:
        RankedNodeRepository(self.repository.session).lock_ranking()
        entity = super().update(entity_id, data)
        refresh_depth_boundary(self.repository.session, entity)
        return entity
