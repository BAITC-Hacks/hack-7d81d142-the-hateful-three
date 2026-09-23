"""Persistence for directed aggregate edges."""

from backend.models import Edge
from backend.repositories.base import BaseRepository


class EdgeRepository(BaseRepository[Edge]):
    model = Edge
