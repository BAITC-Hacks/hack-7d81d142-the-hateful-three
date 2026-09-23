"""Business rules for cluster summaries."""

from typing import Any

from backend.models import Cluster
from backend.schemas import ClusterCreate, ClusterUpdate
from backend.services.base import BaseService
from backend.services.exceptions import ValidationError


class ClusterService(BaseService[Cluster, ClusterCreate, ClusterUpdate]):
    create_schema = ClusterCreate

    def _validate(self, values: dict[str, Any], current: Cluster | None) -> None:
        if values["n_seed"] > values["n_nodes"]:
            raise ValidationError("n_seed must not exceed n_nodes")
        self._ensure_unique(current, cluster_id=values["cluster_id"])
