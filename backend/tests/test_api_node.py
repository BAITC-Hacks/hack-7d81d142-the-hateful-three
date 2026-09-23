"""Node HTTP CRUD, uniqueness and pagination integration tests."""

from datetime import datetime

import pytest


PATH = "/nodes/"


@pytest.fixture
def node_payload():
    return {"gid": "api-node", "depth": 2, "is_seed": False}


def test_create_node(client, node_payload):
    response = client.post(PATH, json=node_payload)

    assert response.status_code == 201, response.text
    created = response.json()
    assert set(created) == set(node_payload) | {"id", "created_at", "updated_at"}
    assert {field: created[field] for field in node_payload} == node_payload
    assert isinstance(created["id"], int) and created["id"] > 0
    assert datetime.fromisoformat(created["created_at"]) <= datetime.fromisoformat(created["updated_at"])
    fetched = client.get(f"{PATH}{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == created


def test_duplicate_node_returns_409(client, api_create, node_payload):
    created = api_create(PATH, node_payload)

    response = client.post(PATH, json=node_payload | {"depth": 3})

    assert response.status_code == 409, response.text
    assert isinstance(response.json()["detail"], str)
    fetched = client.get(f"{PATH}{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == created
    listed = client.get(PATH)
    assert listed.status_code == 200, listed.text
    assert listed.json() == [created]


def test_get_missing_node_returns_404(client):
    response = client.get(f"{PATH}99999")

    assert response.status_code == 404, response.text
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("skip,limit", [(0, 2), (1, 2), (3, 2), (4, 2), (0, 0), (99, 2)])
def test_list_nodes_pagination(client, node_factory, skip, limit):
    # Business keys deliberately differ from insertion order.
    created = [node_factory(gid=gid) for gid in ("node-z", "node-a", "node-m", "node-b")]

    response = client.get(PATH, params={"skip": skip, "limit": limit})

    assert response.status_code == 200, response.text
    assert response.json() == created[skip:skip + limit]


def test_patch_node_preserves_omitted_fields(client, api_create, node_payload):
    created = api_create(PATH, node_payload)
    item_path = f"{PATH}{created['id']}"

    response = client.patch(item_path, json={"depth": 3})

    assert response.status_code == 200, response.text
    updated = response.json()
    expected = created | {"depth": 3}
    assert {key: value for key, value in updated.items() if key != "updated_at"} == {
        key: value for key, value in expected.items() if key != "updated_at"
    }
    assert datetime.fromisoformat(updated["updated_at"]) >= datetime.fromisoformat(created["updated_at"])
    fetched = client.get(item_path)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == updated


def test_delete_node(client, api_create, node_payload):
    created = api_create(PATH, node_payload)
    item_path = f"{PATH}{created['id']}"

    response = client.delete(item_path)

    assert response.status_code == 204, response.text
    assert response.content == b""
    assert client.get(item_path).status_code == 404
    listed = client.get(PATH)
    assert listed.status_code == 200, listed.text
    assert listed.json() == []
