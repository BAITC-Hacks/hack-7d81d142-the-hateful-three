"""Integration coverage for the ranked node CRUD routes."""

from datetime import datetime

import pytest


PATH = "/ranked-nodes/"


@pytest.fixture
def ranked_node_payload(assessment_factory):
    assessment = assessment_factory(role="consolidator", priority_score=0.85)
    return {
        "rank": 1,
        "gid": assessment["gid"],
        "role": "consolidator",
        "priority_score": 0.85,
        "why": "High incoming transfer volume",
    }


def test_create_ranked_node(client, ranked_node_payload):
    response = client.post(PATH, json=ranked_node_payload)

    assert response.status_code == 201, response.text
    created = response.json()
    assert set(created) == set(ranked_node_payload) | {"id", "created_at", "updated_at"}
    assert {field: created[field] for field in ranked_node_payload} == ranked_node_payload
    assert isinstance(created["id"], int) and created["id"] > 0
    assert datetime.fromisoformat(created["created_at"])
    assert datetime.fromisoformat(created["updated_at"])

    fetched = client.get(f"{PATH}{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == created


def test_create_duplicate_ranked_node_returns_409(
    client, api_create, ranked_node_payload
):
    created = api_create(PATH, ranked_node_payload)
    duplicate = ranked_node_payload | {"why": "Duplicate"}
    duplicate["rank"] = ranked_node_payload["rank"] + 1

    response = client.post(PATH, json=duplicate)

    assert response.status_code == 409, response.text
    assert isinstance(response.json()["detail"], str)
    fetched = client.get(f"{PATH}{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == created
    listed = client.get(PATH)
    assert listed.status_code == 200, listed.text
    assert listed.json() == [created]


def test_get_missing_ranked_node_returns_404(client):
    response = client.get(f"{PATH}999999")

    assert response.status_code == 404, response.text
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("skip, limit", [(0, 2), (1, 2), (3, 2), (4, 2), (0, 0)])
def test_list_ranked_nodes_pagination(
    client, api_create, ranked_node_payload, assessment_factory, skip, limit
):
    created = [api_create(PATH, ranked_node_payload)]
    for rank in (3, 9, 1):
        assessment = assessment_factory(role="consolidator", priority_score=0.85)
        created.append(api_create(PATH, ranked_node_payload | {
            "rank": rank,
            "gid": assessment["gid"],
        }))

    response = client.get(PATH, params={"skip": skip, "limit": limit})

    assert response.status_code == 200, response.text
    assert response.json() == created[skip:skip + limit]


def test_patch_ranked_node_preserves_omitted_fields(client, api_create, ranked_node_payload):
    created = api_create(PATH, ranked_node_payload)
    item_path = f"{PATH}{created['id']}"

    response = client.patch(item_path, json={"why": "Updated transfer analysis"})

    assert response.status_code == 200, response.text
    updated = response.json()
    expected = created | {"why": "Updated transfer analysis"}
    assert {field: value for field, value in updated.items() if field != "updated_at"} == {
        field: value for field, value in expected.items() if field != "updated_at"
    }
    assert datetime.fromisoformat(updated["updated_at"])
    fetched = client.get(item_path)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == updated


def test_delete_ranked_node(client, api_create, ranked_node_payload):
    created = api_create(PATH, ranked_node_payload)
    item_path = f"{PATH}{created['id']}"

    response = client.delete(item_path)

    assert response.status_code == 204, response.text
    assert response.content == b""
    fetched = client.get(item_path)
    assert fetched.status_code == 404, fetched.text
