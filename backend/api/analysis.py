"""Заглушка модуля запуска анализа: POST /analysis."""

from fastapi import APIRouter

router = APIRouter(prefix="/analysis", tags=["analysis"])
