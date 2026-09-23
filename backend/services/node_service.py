"""Business rules for graph nodes."""

from typing import Any

from backend.models import Node
from backend.schemas import NodeCreate, NodeUpdate
from backend.services.base import BaseService


class NodeService(BaseService[Node, NodeCreate, NodeUpdate]):
    create_schema = NodeCreate

    def _validate(self, values: dict[str, Any], current: Node | None) -> None:
        self._ensure_unique(current, gid=values["gid"])
