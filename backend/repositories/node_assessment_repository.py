"""Persistence for the current assessment of each node."""

from backend.models import NodeAssessment
from backend.repositories.base import BaseRepository


class NodeAssessmentRepository(BaseRepository[NodeAssessment]):
    model = NodeAssessment
