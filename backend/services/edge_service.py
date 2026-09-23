"""Business rules for directed aggregate edges."""

from typing import Any

from backend.models import Edge
from backend.repositories import NodeRepository, RankedNodeRepository
from backend.schemas import EdgeCreate, EdgeUpdate
from backend.services.base import BaseService
from backend.services.graph_semantics import refresh_depth_boundary


class EdgeService(BaseService[Edge, EdgeCreate, EdgeUpdate]):
    create_schema = EdgeCreate

    def _refresh_source(self, gid: str) -> None:
        node = NodeRepository(self.repository.session).get_by_fields(gid=gid)
        refresh_depth_boundary(self.repository.session, node)

    def create(self, data: EdgeCreate) -> Edge:
        RankedNodeRepository(self.repository.session).lock_ranking()
        entity = super().create(data)
        self._refresh_source(entity.src)
        return entity

    def update(self, entity_id: int, data: EdgeUpdate) -> Edge:
        RankedNodeRepository(self.repository.session).lock_ranking()
        old_src = self.get_by_id(entity_id).src
        entity = super().update(entity_id, data)
        for gid in {old_src, entity.src}:
            self._refresh_source(gid)
        return entity

    def delete(self, entity_id: int) -> None:
        RankedNodeRepository(self.repository.session).lock_ranking()
        src = self.get_by_id(entity_id).src
        super().delete(entity_id)
        self._refresh_source(src)

    def _validate(self, values: dict[str, Any], current: Edge | None) -> None:
        self._ensure_unique(current, src=values["src"], dst=values["dst"])
        nodes = NodeRepository(self.repository.session)
        self._require_reference(nodes, gid=values["src"])
        self._require_reference(nodes, gid=values["dst"])
