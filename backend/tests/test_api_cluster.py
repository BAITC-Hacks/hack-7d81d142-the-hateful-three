"""Cluster HTTP CRUD, uniqueness and pagination integration tests."""

from datetime import datetime

import pytest


PATH = "/clusters/"


@pytest.fixture
def cluster_payload(node_factory):
    nodes = [node_factory(is_seed=True), node_factory()]
    return {
        "cluster_id": 42,
        "n_nodes": 2,
        "n_seed": 1,
        "sum_kzt_internal": "10000.02",
        "top_gids": [node["gid"] for node in nodes],
        "hypothesis": "Two connected clients",
    }


def test_create_cluster(client, cluster_payload):
    response = client.post(PATH, json=cluster_payload)

    assert response.status_code == 201, response.text
    created = response.json()
    assert set(created) == set(cluster_payload) | {"id", "created_at", "updated_at"}
    assert {field: created[field] for field in cluster_payload} == cluster_payload
    assert isinstance(created["id"], int) and created["id"] > 0
    assert datetime.fromisoformat(created["created_at"]) <= datetime.fromisoformat(created["updated_at"])
    fetched = client.get(f"{PATH}{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == created


def test_duplicate_cluster_returns_409(client, api_create, cluster_payload):
    created = api_create(PATH, cluster_payload)

    response = client.post(PATH, json=cluster_payload | {"hypothesis": "Duplicate business key"})

    assert response.status_code == 409, response.text
    assert isinstance(response.json()["detail"], str)
    fetched = client.get(f"{PATH}{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == created
    listed = client.get(PATH)
    assert listed.status_code == 200, listed.text
    assert listed.json() == [created]


def test_get_missing_cluster_returns_404(client):
    response = client.get(f"{PATH}99999")

    assert response.status_code == 404, response.text
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("skip,limit", [(0, 2), (1, 2), (3, 2), (4, 2), (0, 0), (99, 2)])
def test_list_clusters_pagination(client, cluster_factory, skip, limit):
    # Pagination is ordered by technical ID, not cluster_id.
    created = [cluster_factory(cluster_id=value) for value in (42, 7, 99, 3)]

    response = client.get(PATH, params={"skip": skip, "limit": limit})

    assert response.status_code == 200, response.text
    assert response.json() == created[skip:skip + limit]


def test_patch_cluster_preserves_omitted_fields(client, api_create, cluster_payload):
    created = api_create(PATH, cluster_payload)
    item_path = f"{PATH}{created['id']}"

    response = client.patch(item_path, json={"hypothesis": "Updated explanation"})

    assert response.status_code == 200, response.text
    updated = response.json()
    expected = created | {"hypothesis": "Updated explanation"}
    assert {key: value for key, value in updated.items() if key != "updated_at"} == {
        key: value for key, value in expected.items() if key != "updated_at"
    }
    assert datetime.fromisoformat(updated["updated_at"]) >= datetime.fromisoformat(created["updated_at"])
    fetched = client.get(item_path)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == updated


def test_delete_cluster(client, api_create, cluster_payload):
    created = api_create(PATH, cluster_payload)
    item_path = f"{PATH}{created['id']}"

    response = client.delete(item_path)

    assert response.status_code == 204, response.text
    assert response.content == b""
    assert client.get(item_path).status_code == 404
    listed = client.get(PATH)
    assert listed.status_code == 200, listed.text
    assert listed.json() == []
