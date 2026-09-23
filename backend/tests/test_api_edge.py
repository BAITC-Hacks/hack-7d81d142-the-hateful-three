"""Integration tests for directed edges through the authenticated HTTP API."""

from datetime import datetime

import pytest


@pytest.fixture
def edge_payload(node_factory):
    source = node_factory(gid="edge-source")
    destination = node_factory(gid="edge-destination")
    return {
        "src": source["gid"],
        "dst": destination["gid"],
        "sum_kzt": "12345.67",
        "n_tx": 3,
        "depth": 2,
    }


def test_create_edge(client, edge_payload):
    response = client.post("/edges/", json=edge_payload)

    assert response.status_code == 201, response.text
    created = response.json()
    assert set(created) == set(edge_payload) | {"id", "created_at", "updated_at"}
    assert {field: created[field] for field in edge_payload} == edge_payload
    assert isinstance(created["id"], int) and created["id"] > 0
    assert datetime.fromisoformat(created["created_at"])
    assert datetime.fromisoformat(created["updated_at"])
    fetched = client.get(f"/edges/{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == created


def test_duplicate_edge_returns_409(client, api_create, edge_payload):
    created = api_create("/edges/", edge_payload)

    response = client.post("/edges/", json=edge_payload | {"n_tx": 99})

    assert response.status_code == 409, response.text
    assert isinstance(response.json()["detail"], str)
    fetched = client.get(f"/edges/{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == created
    listed = client.get("/edges/")
    assert listed.status_code == 200, listed.text
    assert listed.json() == [created]


def test_get_missing_edge_returns_404(client):
    response = client.get("/edges/999999")

    assert response.status_code == 404, response.text
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("skip, limit", [(0, 2), (1, 2), (3, 10), (0, 0), (8, 2)])
def test_list_edges_pagination(client, edge_factory, skip, limit):
    created = [edge_factory(n_tx=index + 1) for index in range(4)]

    response = client.get("/edges/", params={"skip": skip, "limit": limit})

    assert response.status_code == 200, response.text
    assert response.json() == created[skip:skip + limit]


def test_patch_edge_preserves_omitted_fields(client, api_create, edge_payload):
    created = api_create("/edges/", edge_payload)
    item_path = f"/edges/{created['id']}"

    response = client.patch(item_path, json={"n_tx": 7})

    assert response.status_code == 200, response.text
    updated = response.json()
    assert set(updated) == set(created)
    assert {field: value for field, value in updated.items() if field != "updated_at"} == {
        field: value for field, value in (created | {"n_tx": 7}).items()
        if field != "updated_at"
    }
    assert datetime.fromisoformat(updated["updated_at"])
    fetched = client.get(item_path)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == updated


def test_delete_edge(client, api_create, edge_payload):
    created = api_create("/edges/", edge_payload)
    item_path = f"/edges/{created['id']}"

    response = client.delete(item_path)

    assert response.status_code == 204, response.text
    assert response.content == b""
    fetched = client.get(item_path)
    assert fetched.status_code == 404, fetched.text


@pytest.mark.parametrize("endpoint", ["src", "dst"])
def test_create_edge_with_missing_node_returns_404(client, edge_payload, endpoint):
    response = client.post("/edges/", json=edge_payload | {endpoint: "missing-node"})

    assert response.status_code == 404, response.text
    assert "Node not found" in response.json()["detail"]
    listed = client.get("/edges/")
    assert listed.status_code == 200, listed.text
    assert listed.json() == []


def test_reverse_edge_is_a_distinct_directed_pair(client, api_create, edge_payload):
    forward = api_create("/edges/", edge_payload)
    reverse_payload = edge_payload | {"src": edge_payload["dst"], "dst": edge_payload["src"]}

    response = client.post("/edges/", json=reverse_payload)

    assert response.status_code == 201, response.text
    reverse = response.json()
    assert reverse["id"] != forward["id"]
    assert {field: reverse[field] for field in reverse_payload} == reverse_payload
    listed = client.get("/edges/")
    assert listed.status_code == 200, listed.text
    assert listed.json() == [forward, reverse]
