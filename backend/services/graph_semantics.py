"""Rules that remain meaningful while a graph is being loaded incrementally."""

from sqlalchemy import select

from backend.models import Edge, NodeAssessment


def is_depth_boundary(session, gid: str, depth: int) -> bool:
    return depth == 4 and session.scalar(select(Edge.id).where(Edge.src == gid).limit(1)) is None


def refresh_depth_boundary(session, node) -> None:
    assessment = session.scalar(select(NodeAssessment).where(NodeAssessment.gid == node.gid))
    if assessment is not None:
        assessment.truncated_by_depth = is_depth_boundary(session, node.gid, node.depth)
        session.flush()
