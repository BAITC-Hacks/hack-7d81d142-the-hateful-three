"""Заглушка для RankedNode: GET /ranking."""

from fastapi import APIRouter

router = APIRouter(prefix="/ranking", tags=["ranking"])
