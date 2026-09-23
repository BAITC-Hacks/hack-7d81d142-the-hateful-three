"""Authenticated UTF-8 CSV exports using the starter's column order."""

import csv
import json
from io import StringIO
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import Response
from sqlalchemy import select

from backend.api.dependencies import DbSession
from backend.models import Cluster, Node, NodeAssessment, RankedNode

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/{filename}")
def export_csv(filename: Literal["nodes_roles.csv", "clusters.csv", "top_nodes.csv"], session: DbSession):
    if filename == "nodes_roles.csv":
        fields = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence",
                  "in_deg", "out_deg", "in_kzt", "out_kzt", "pagerank", "pass_through",
                  "depth", "is_seed", "truncated_by_depth"]
        rows = [dict({field: getattr(a, field) for field in fields if field not in ("depth", "is_seed")},
                     depth=node.depth, is_seed=node.is_seed)
                for a, node in session.execute(select(NodeAssessment, Node).join(
                    Node, Node.gid == NodeAssessment.gid,
                ).order_by(Node.gid))]
    else:
        model = Cluster if filename == "clusters.csv" else RankedNode
        fields = (["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"]
                  if model is Cluster else ["rank", "gid", "role", "priority_score", "why"])
        order = Cluster.cluster_id if model is Cluster else RankedNode.rank
        rows = [{field: getattr(row, field) for field in fields}
                for row in session.scalars(select(model).order_by(order))]
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        for key, value in row.items():
            if hasattr(value, "value"):
                row[key] = value.value
            elif isinstance(value, list):
                row[key] = json.dumps(value, ensure_ascii=False)
            if isinstance(row[key], str) and row[key].startswith(("=", "+", "-", "@", "\t", "\r")):
                row[key] = "'" + row[key]
        writer.writerow(row)
    return Response(output.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
