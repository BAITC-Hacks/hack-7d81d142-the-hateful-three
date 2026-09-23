"""Заглушка модуля сводки датасета: GET /dataset."""

from fastapi import APIRouter

router = APIRouter(prefix="/dataset", tags=["dataset"])
