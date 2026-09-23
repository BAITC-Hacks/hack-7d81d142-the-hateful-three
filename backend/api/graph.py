"""Заглушка окружения графа из Node и Edge: GET /graph."""

from fastapi import APIRouter

router = APIRouter(prefix="/graph", tags=["graph"])
