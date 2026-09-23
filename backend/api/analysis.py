"""Recalculate the current graph analysis atomically."""

from fastapi import APIRouter

from backend.api.dependencies import DbSession
from backend.services.analytics import analysis_write, run_analysis

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("")
def analyze(session: DbSession) -> dict:
    with analysis_write(session):
        result = run_analysis(session)
        session.commit()
        return result
