"""Заглушка выгрузок nodes_roles.csv, clusters.csv и top_nodes.csv."""

from fastapi import APIRouter

router = APIRouter(prefix="/exports", tags=["exports"])
