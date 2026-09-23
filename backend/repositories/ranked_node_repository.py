"""Persistence for stored ranking snapshots."""

from sqlalchemy import select, text

from backend.models import NodeAssessment, RankedNode
from backend.repositories.base import BaseRepository


class RankedNodeRepository(BaseRepository[RankedNode]):
    model = RankedNode

    def _list_order(self):
        return (RankedNode.rank, RankedNode.id)

    def lock_ranking(self) -> None:
        # Serialize assessment/ranking writers across PostgreSQL workers. The
        # transaction owns this lock, including the final request commit.
        if self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(text("SELECT pg_advisory_xact_lock(1296523841)"))

    def free_rank(self) -> int:
        used = set(self.session.scalars(select(RankedNode.rank)))
        rank = 1
        while rank in used:
            rank += 1
        return rank

    def synchronize(self, *, include_missing: bool = False) -> list[RankedNode]:
        """Refresh saved members; rebuilding also includes every assessed node."""
        assessments = {a.gid: a for a in self.session.scalars(select(NodeAssessment))}
        rows = list(self.session.scalars(select(RankedNode)))
        retained = []
        for row in rows:
            assessment = assessments.get(row.gid)
            if assessment is None:
                self.session.delete(row)
                continue
            row.role = assessment.role
            row.priority_score = assessment.priority_score
            if include_missing:
                row.why = assessment.evidence
            retained.append(row)
        self.session.flush()
        if include_missing:
            existing = {row.gid for row in retained}
            used = {row.rank for row in retained}
            candidate = 1
            for gid, assessment in assessments.items():
                if gid in existing:
                    continue
                while candidate in used:
                    candidate += 1
                row = RankedNode(gid=gid, rank=candidate, role=assessment.role,
                                 priority_score=assessment.priority_score, why=assessment.evidence)
                self.session.add(row)
                retained.append(row)
                used.add(candidate)
            self.session.flush()

        retained.sort(key=lambda row: (-row.priority_score, row.gid))
        if any(row.rank != rank for rank, row in enumerate(retained, 1)):
            # Positive, unused temporary ranks avoid UNIQUE collisions during
            # swaps on both SQLite and PostgreSQL, without deferrable constraints.
            used = {row.rank for row in retained}
            candidate = len(retained) + 1
            for row in retained:
                while candidate in used:
                    candidate += 1
                row.rank = candidate
                used.add(candidate)
            self.session.flush()
            for rank, row in enumerate(retained, 1):
                row.rank = rank
            self.session.flush()
        return retained
