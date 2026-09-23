"""Persistence for analysis cluster summaries."""

from backend.models import Cluster
from backend.repositories.base import BaseRepository


class ClusterRepository(BaseRepository[Cluster]):
    model = Cluster
