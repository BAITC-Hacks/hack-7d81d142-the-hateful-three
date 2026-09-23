"""Deterministic, explainable graph heuristics for the current dataset.

Scores are heuristic strengths, not calibrated probabilities. The depth-four
boundary is never classified as a confirmed terminal recipient.
"""

from collections import Counter
from contextlib import contextmanager
from decimal import Decimal
from math import log1p
from threading import Lock

import networkx as nx
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from backend.models import Cluster, Edge, Node, NodeAssessment, RankedNode, Transaction
from backend.models.enums import NodeRole
from backend.services.exceptions import ConflictError, ValidationError

_write_lock = Lock()


@contextmanager
def analysis_write(session: Session):
    """Serialize imports/recalculations; PostgreSQL lock lasts through commit."""
    if not _write_lock.acquire(blocking=False):
        raise ConflictError("Анализ уже выполняется. Повторите запрос позже.")
    try:
        if session.bind.dialect.name == "postgresql":
            if not session.scalar(text("SELECT pg_try_advisory_xact_lock(1296523841)")):
                raise ConflictError("Анализ уже выполняется. Повторите запрос позже.")
        yield
    finally:
        _write_lock.release()


def summary(session: Session) -> dict:
    counts = {name: session.scalar(select(func.count()).select_from(model))
              for name, model in [("nodes", Node), ("edges", Edge),
                                  ("transactions", Transaction), ("clusters", Cluster),
                                  ("assessments", NodeAssessment)]}
    date_min, date_max, total = session.execute(select(
        func.min(Transaction.date), func.max(Transaction.date), func.sum(Transaction.sum_kzt),
    )).one()
    return counts | {
        "seeds": session.scalar(select(func.count()).select_from(Node).where(Node.is_seed.is_(True))),
        "role_counts": {r.value: n for r, n in session.execute(select(
            NodeAssessment.role, func.count(),
        ).group_by(NodeAssessment.role))},
        "truncated_nodes": session.scalar(select(func.count()).select_from(Node).where(
            Node.depth == 4, ~select(Edge.id).where(Edge.src == Node.gid).exists(),
        )),
        "date_min": date_min, "date_max": date_max, "total_kzt": str(total or 0),
        "analyzed_at": session.scalar(select(func.max(NodeAssessment.updated_at))),
        "analysis_ready": bool(counts["nodes"] and counts["assessments"] == counts["nodes"]),
        "method": "Объяснимые графовые эвристики v1; оценки не являются вероятностями.",
    }


def weighted_pagerank(graph: nx.DiGraph) -> dict[str, float]:
    """Weighted PageRank power iteration without a SciPy runtime dependency."""
    size = len(graph)
    if not size:
        return {}
    ranks = dict.fromkeys(graph, 1 / size)
    out = dict(graph.out_degree(weight="weight"))
    for _ in range(300):
        base = (0.15 + 0.85 * sum(ranks[n] for n in graph if out[n] == 0)) / size
        updated = dict.fromkeys(graph, base)
        for src, dst, attrs in graph.edges(data=True):
            if out[src]:
                updated[dst] += 0.85 * ranks[src] * attrs["weight"] / out[src]
        error = sum(abs(updated[n] - ranks[n]) for n in graph)
        ranks = updated
        if error < size * 1e-10:
            return ranks
    raise ValidationError("PageRank не сошёлся; сохранён предыдущий результат анализа.")


def run_analysis(session: Session) -> dict:
    nodes = list(session.scalars(select(Node).order_by(Node.gid)))
    edges = list(session.scalars(select(Edge).order_by(Edge.src, Edge.dst)))
    if not nodes:
        raise ValidationError("Сначала загрузите датасет.")
    graph = nx.DiGraph()
    graph.add_nodes_from(n.gid for n in nodes)
    for edge in edges:
        graph.add_edge(edge.src, edge.dst, weight=float(edge.sum_kzt), amount=edge.sum_kzt, n_tx=edge.n_tx)
    pagerank = weighted_pagerank(graph)
    undirected = nx.Graph()
    undirected.add_nodes_from(graph)
    for edge in edges:
        # Reciprocal transfers contribute both directions to community weight.
        previous = undirected.get_edge_data(edge.src, edge.dst, {}).get("weight", 0)
        undirected.add_edge(edge.src, edge.dst, weight=previous + max(float(edge.sum_kzt), 1))
    groups = (nx.community.louvain_communities(undirected, weight="weight", seed=42)
              if edges else [{n.gid} for n in nodes])
    groups = sorted(groups, key=lambda group: (-len(group), min(group)))
    membership = {gid: i for i, group in enumerate(groups, 1) for gid in group}
    seed_reach = Counter()
    for node in nodes:
        if node.is_seed:
            seed_reach.update(nx.descendants(graph, node.gid))
    features = []
    for node in nodes:
        incoming = list(graph.in_edges(node.gid, data=True))
        outgoing = list(graph.out_edges(node.gid, data=True))
        in_kzt = sum((e[2]["amount"] for e in incoming), Decimal(0))
        out_kzt = sum((e[2]["amount"] for e in outgoing), Decimal(0))
        ideg, odeg = len(incoming), len(outgoing)
        ratio = float(out_kzt / in_kzt) if in_kzt else None
        truncated = node.depth == 4 and odeg == 0
        if truncated:
            role, strength = NodeRole.PERIPHERAL, 0.3
        elif ideg >= 3 and odeg >= 3 and seed_reach[node.gid] >= 2:
            role, strength = NodeRole.COORDINATOR, 0.75
        elif ideg >= 3 and (ratio is None or ratio < 0.7):
            role, strength = NodeRole.CONSOLIDATOR, 0.8
        elif odeg >= 3 and odeg >= 2 * ideg:
            role, strength = NodeRole.DISTRIBUTOR, 0.8
        elif ideg and odeg and ratio is not None and 0.7 <= ratio <= 1.3:
            role, strength = NodeRole.TRANSIT, 0.75
        elif ideg and not odeg:
            role, strength = NodeRole.TERMINAL, 0.55
        else:
            role, strength = NodeRole.PERIPHERAL, 0.4
        evidence = (f"Вход: {ideg} / {in_kzt:,.0f} KZT; выход: {odeg} / {out_kzt:,.0f} KZT; "
                    f"seed-достижимость: {seed_reach[node.gid]}; "
                    + (f"выход/вход: {ratio:.2f}." if ratio is not None else "нет входящего объёма."))
        if truncated:
            evidence += " Граница 4-го колена; конечный получатель не подтверждён."
        features.append(dict(
            gid=node.gid, role=role, role_score=strength, cluster_id=membership[node.gid],
            in_deg=ideg, out_deg=odeg, in_kzt=in_kzt, out_kzt=out_kzt,
            in_tx=sum(e[2]["n_tx"] for e in incoming), out_tx=sum(e[2]["n_tx"] for e in outgoing),
            pagerank=pagerank[node.gid], pass_through=ratio,
            truncated_by_depth=truncated, evidence=evidence[:200],
        ))
    max_volume = max(log1p(float(f["in_kzt"] + f["out_kzt"])) for f in features) or 1
    max_degree = max(f["in_deg"] + f["out_deg"] for f in features) or 1
    max_seeds = max(seed_reach.values(), default=1) or 1
    max_pr = max(pagerank.values()) or 1
    role_weight = {NodeRole.CONSOLIDATOR: 1, NodeRole.COORDINATOR: 1,
                   NodeRole.DISTRIBUTOR: .8, NodeRole.TRANSIT: .6,
                   NodeRole.TERMINAL: .35, NodeRole.PERIPHERAL: .1}
    for f in features:
        score = (.3 * log1p(float(f["in_kzt"] + f["out_kzt"])) / max_volume
                 + .2 * (f["in_deg"] + f["out_deg"]) / max_degree
                 + .2 * seed_reach[f["gid"]] / max_seeds
                 + .15 * f["pagerank"] / max_pr + .15 * role_weight[f["role"]])
        if not (f["in_deg"] or f["out_deg"]):
            score = 0
        if f["truncated_by_depth"]:
            score *= .6
        f["priority_score"] = round(min(1, score), 6)
    ordered = sorted(features, key=lambda f: (-f["priority_score"], f["gid"]))
    # Delete/rebuild only derived results inside the caller's transaction.
    for model in (RankedNode, NodeAssessment, Cluster):
        session.execute(delete(model))
    seed_ids = {n.gid for n in nodes if n.is_seed}
    internal = Counter()
    for edge in edges:
        if membership[edge.src] == membership[edge.dst]:
            internal[membership[edge.src]] += edge.sum_kzt
    for i, group in enumerate(groups, 1):
        leaders = [f for f in ordered if f["gid"] in group][:5]
        seed_count = len(group & seed_ids)
        session.add(Cluster(
            cluster_id=i, n_nodes=len(group), n_seed=seed_count,
            sum_kzt_internal=internal[i], top_gids=[f["gid"] for f in leaders],
            hypothesis=f"Группа Louvain: {len(group)} узлов, {seed_count} seed. "
                       f"Ведущая роль: {leaders[0]['role'].value}. Гипотеза для проверки аналитиком.",
        ))
    session.flush()
    session.add_all(NodeAssessment(**f) for f in features)
    session.add_all(RankedNode(rank=i, gid=f["gid"], role=f["role"],
                               priority_score=f["priority_score"], why=f["evidence"])
                    for i, f in enumerate(ordered, 1))
    session.flush()
    return summary(session)
