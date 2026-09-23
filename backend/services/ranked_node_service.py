"""Business rules for ranking snapshots; recomputation belongs to analysis."""

from typing import Any

from backend.models import RankedNode
from backend.repositories import NodeRepository
from backend.schemas import RankedNodeCreate, RankedNodeUpdate
from backend.services.base import BaseService


class RankedNodeService(BaseService[RankedNode, RankedNodeCreate, RankedNodeUpdate]):
    create_schema = RankedNodeCreate

    def _validate(self, values: dict[str, Any], current: RankedNode | None) -> None:
        self._ensure_unique(current, gid=values["gid"])
        self._ensure_unique(current, rank=values["rank"])
        self._require_reference(NodeRepository(self.repository.session), gid=values["gid"])
