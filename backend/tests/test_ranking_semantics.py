"""Regression coverage for the derived review queue and analytical validation."""

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import NodeAssessment, RankedNode
from backend.schemas import NodeAssessmentUpdate


def add_ranked(client, assessment, **overrides):
    response = client.post("/ranked-nodes/", json={
        "gid": assessment["gid"], "role": assessment["role"],
        "priority_score": assessment["priority_score"], "why": assessment["evidence"],
    } | overrides)
    assert response.status_code == 201, response.text
    return response.json()


def queue(client):
    response = client.get("/ranking")
    assert response.status_code == 200, response.text
    return response.json()


def test_requires_assessment_and_matching_role_score(client, node_factory, assessment_factory):
    node = node_factory()
    payload = {"gid": node["gid"], "role": "transit", "priority_score": 0.8, "why": "1 transfer"}
    assert client.post("/ranked-nodes/", json=payload).status_code == 404
    assessment = assessment_factory(gid=node["gid"])
    for mismatch in ({"role": "terminal"}, {"priority_score": 0.5}):
        assert client.post("/ranked-nodes/", json=payload | mismatch).status_code == 422
    ranked = add_ranked(client, assessment)
    for mismatch in ({"role": "terminal"}, {"priority_score": 0.5}, {"rank": None}):
        assert client.patch(f"/ranked-nodes/{ranked['id']}", json=mismatch).status_code == 422
    assert queue(client) == [ranked]


def test_sorts_before_pagination_and_reassigns_ranks(client, node_factory, assessment_factory):
    a = assessment_factory(gid=node_factory(gid="a")["gid"], priority_score=0.5)
    z = assessment_factory(gid=node_factory(gid="z")["gid"], priority_score=0.5)
    high = assessment_factory(priority_score=0.9)
    add_ranked(client, z, rank=99)
    add_ranked(client, a, rank=99)
    add_ranked(client, high, rank=99)
    rows = queue(client)
    assert [row["gid"] for row in rows] == [high["gid"], "a", "z"]
    assert [row["rank"] for row in rows] == [1, 2, 3]
    for path in ("/ranking", "/ranked-nodes/"):
        assert client.get(path, params={"skip": 1, "limit": 1}).json() == [rows[1]]


def test_assessment_changes_swap_ranks_and_refresh_derived_explanation(client, assessment_factory):
    low = assessment_factory(priority_score=0.2)
    high = assessment_factory(priority_score=0.9)
    original_low = add_ranked(client, low)
    original_high = add_ranked(client, high)
    response = client.patch(f"/node-assessments/{low['id']}", json={
        "priority_score": 1.0, "role": "terminal", "evidence": "priority=1.0; 0 outgoing edges",
    })
    assert response.status_code == 200, response.text
    rows = queue(client)
    assert [(r["id"], r["rank"]) for r in rows] == [(original_low["id"], 1), (original_high["id"], 2)]
    assert rows[0]["role"] == "terminal"
    assert rows[0]["priority_score"] == 1.0
    assert rows[0]["why"] == response.json()["evidence"]


def test_deleting_assessment_removes_ranked_member_and_closes_gap(client, assessment_factory):
    first = assessment_factory(priority_score=0.9)
    second = assessment_factory(priority_score=0.2)
    add_ranked(client, first)
    survivor = add_ranked(client, second)
    assert client.delete(f"/node-assessments/{first['id']}").status_code == 204
    rows = queue(client)
    assert len(rows) == 1
    assert (rows[0]["id"], rows[0]["rank"]) == (survivor["id"], 1)


def test_rekey_assessment_removes_old_ranking(client, node_factory, assessment_factory):
    assessment = assessment_factory()
    add_ranked(client, assessment)
    response = client.patch(f"/node-assessments/{assessment['id']}", json={"gid": node_factory()["gid"]})
    assert response.status_code == 200, response.text
    assert queue(client) == []


def test_deleting_ranked_member_does_not_delete_assessment(client, assessment_factory):
    high = assessment_factory(priority_score=0.9)
    low = assessment_factory(priority_score=0.2)
    ranked = add_ranked(client, high)
    add_ranked(client, low)
    assert client.delete(f"/ranked-nodes/{ranked['id']}").status_code == 204
    assert queue(client)[0]["rank"] == 1
    assert client.get(f"/node-assessments/{high['id']}").status_code == 200


def test_rebuild_includes_all_assessments_and_is_idempotent(client, assessment_factory):
    assert client.post("/ranking/rebuild").json() == {"ranked_nodes": 0}
    low = assessment_factory(priority_score=0.1)
    high = assessment_factory(priority_score=0.9)
    assert queue(client) == []  # Selection stays explicit until rebuild.
    assert client.post("/ranking/rebuild").json() == {"ranked_nodes": 2}
    before = queue(client)
    assert [row["gid"] for row in before] == [high["gid"], low["gid"]]
    assert client.post("/ranking/rebuild").json() == {"ranked_nodes": 2}
    assert queue(client) == before


def test_ranking_commit_failure_rolls_back_assessment_and_queue(
    client, assessment_factory, db_session_factory, db_engine
):
    low = assessment_factory(priority_score=0.1)
    high = assessment_factory(priority_score=0.9)
    add_ranked(client, low)
    add_ranked(client, high)

    class FailingSession(Session):
        def commit(self):
            raise RuntimeError("ranking commit failure")

    original_class = db_session_factory.class_
    db_session_factory.class_ = FailingSession
    try:
        with pytest.raises(RuntimeError, match="ranking commit failure"):
            client.patch(f"/node-assessments/{low['id']}", json={"priority_score": 1.0})
    finally:
        db_session_factory.class_ = original_class
    with Session(db_engine) as session:
        assert session.get(NodeAssessment, low["id"]).priority_score == 0.1
        rows = list(session.scalars(select(RankedNode).order_by(RankedNode.rank)))
        assert [(row.gid, row.rank) for row in rows] == [(high["gid"], 1), (low["gid"], 2)]


@pytest.mark.parametrize("path,method", [("/ranking", "get"), ("/ranking/rebuild", "post")])
def test_ranking_routes_require_authentication(client, path, method):
    client.headers.pop("Authorization")
    assert getattr(client, method)(path).status_code == 401


@pytest.mark.parametrize("evidence", ["", "   ", "Lots of transfers"])
def test_evidence_requires_numeric_explanation_on_create_and_patch(client, assessment_factory, evidence):
    assessment = assessment_factory()
    payload = {k: v for k, v in assessment.items() if k not in {"id", "created_at", "updated_at"}}
    assert client.post("/node-assessments/", json=payload | {"evidence": evidence}).status_code == 422
    assert client.patch(f"/node-assessments/{assessment['id']}", json={"evidence": evidence}).status_code == 422
    assert client.get(f"/node-assessments/{assessment['id']}").json() == assessment


@pytest.mark.parametrize("depth,is_seed", [(0, False), (1, True), (4, True)])
def test_seed_depth_rule_checks_merged_patch(client, node_factory, depth, is_seed):
    assert client.post("/nodes/", json={"gid": "invalid", "depth": depth, "is_seed": is_seed}).status_code == 422
    node = node_factory(depth=depth if depth else 0, is_seed=depth == 0)
    assert client.patch(f"/nodes/{node['id']}", json={"is_seed": is_seed}).status_code == 422
    assert client.get(f"/nodes/{node['id']}").json() == node


def test_boundary_flag_checks_graph_and_tracks_node_and_edge_changes(
    client, node_factory, assessment_factory, edge_factory
):
    node = node_factory(depth=4)
    assessment = assessment_factory(gid=node["gid"], truncated_by_depth=True)
    path = f"/node-assessments/{assessment['id']}"
    assert client.patch(path, json={"truncated_by_depth": False}).status_code == 422
    assert client.patch(f"/nodes/{node['id']}", json={"depth": 3}).status_code == 200
    assert client.get(path).json()["truncated_by_depth"] is False
    assert client.patch(f"/nodes/{node['id']}", json={"depth": 4}).status_code == 200
    assert client.get(path).json()["truncated_by_depth"] is True
    edge = edge_factory(src=node["gid"])
    assert client.get(path).json()["truncated_by_depth"] is False
    assert client.patch(path, json={"truncated_by_depth": True}).status_code == 422
    assert client.delete(f"/edges/{edge['id']}").status_code == 204
    assert client.get(path).json()["truncated_by_depth"] is True


def test_boundary_flag_cannot_be_set_below_depth_four(client, assessment_factory):
    assessment = assessment_factory()
    assert client.patch(f"/node-assessments/{assessment['id']}", json={"truncated_by_depth": True}).status_code == 422


@pytest.mark.parametrize("values", [
    {"pagerank": 1.1}, {"pagerank": float("inf")},
    {"pass_through": float("inf")}, {"pass_through": float("nan")},
])
def test_nonfinite_or_out_of_range_metrics_are_rejected(values):
    with pytest.raises(ValidationError):
        NodeAssessmentUpdate(**values)


def test_moving_edge_refreshes_both_boundary_flags(client, node_factory, assessment_factory, edge_factory):
    left = node_factory(depth=4)
    right = node_factory(depth=4)
    a = assessment_factory(gid=left["gid"], truncated_by_depth=True)
    b = assessment_factory(gid=right["gid"], truncated_by_depth=True)
    edge = edge_factory(src=left["gid"])
    assert client.patch(f"/edges/{edge['id']}", json={"src": right["gid"]}).status_code == 200
    assert client.get(f"/node-assessments/{a['id']}").json()["truncated_by_depth"] is True
    assert client.get(f"/node-assessments/{b['id']}").json()["truncated_by_depth"] is False
