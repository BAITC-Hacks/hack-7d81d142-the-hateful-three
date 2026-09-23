"""Persistence for graph nodes."""

from backend.models import Node
from backend.repositories.base import BaseRepository


class NodeRepository(BaseRepository[Node]):
    model = Node
