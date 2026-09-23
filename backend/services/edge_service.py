"""Business rules for directed aggregate edges."""

from typing import Any

from backend.models import Edge
from backend.repositories import NodeRepository
from backend.schemas import EdgeCreate, EdgeUpdate
from backend.services.base import BaseService


class EdgeService(BaseService[Edge, EdgeCreate, EdgeUpdate]):
    create_schema = EdgeCreate

    def _validate(self, values: dict[str, Any], current: Edge | None) -> None:
        self._ensure_unique(current, src=values["src"], dst=values["dst"])
        nodes = NodeRepository(self.repository.session)
        self._require_reference(nodes, gid=values["src"])
        self._require_reference(nodes, gid=values["dst"])
