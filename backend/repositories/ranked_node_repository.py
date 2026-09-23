"""Persistence for stored ranking snapshots."""

from backend.models import RankedNode
from backend.repositories.base import BaseRepository


class RankedNodeRepository(BaseRepository[RankedNode]):
    model = RankedNode
