"""Integration coverage for the node assessment CRUD routes."""

from datetime import datetime

import pytest


PATH = "/node-assessments/"


@pytest.fixture
def assessment_payload(node_factory, cluster_factory):
    node = node_factory()
    cluster = cluster_factory()
    return {
        "gid": node["gid"],
        "role": "transit",
        "role_score": 0.7,
        "cluster_id": cluster["cluster_id"],
        "priority_score": 0.8,
        "evidence": "5 incoming and 7 outgoing transfers",
        "in_deg": 2,
        "out_deg": 3,
        "in_tx": 5,
        "out_tx": 7,
        "in_kzt": "15000.25",
        "out_kzt": "12000.50",
        "pagerank": 0.15,
        "pass_through": 0.8,
        "truncated_by_depth": False,
    }


def test_create_node_assessment(client, assessment_payload):
    response = client.post(PATH, json=assessment_payload)

    assert response.status_code == 201, response.text
    created = response.json()
    assert set(created) == set(assessment_payload) | {"id", "created_at", "updated_at"}
    assert {field: created[field] for field in assessment_payload} == assessment_payload
    assert isinstance(created["id"], int) and created["id"] > 0
    assert datetime.fromisoformat(created["created_at"])
    assert datetime.fromisoformat(created["updated_at"])

    fetched = client.get(f"{PATH}{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == created


def test_create_duplicate_node_assessment_returns_409(client, api_create, assessment_payload):
    created = api_create(PATH, assessment_payload)

    response = client.post(PATH, json=assessment_payload | {"evidence": "Duplicate: 5 transfers"})

    assert response.status_code == 409, response.text
    assert isinstance(response.json()["detail"], str)
    fetched = client.get(f"{PATH}{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == created
    listed = client.get(PATH)
    assert listed.status_code == 200, listed.text
    assert listed.json() == [created]


def test_get_missing_node_assessment_returns_404(client):
    response = client.get(f"{PATH}999999")

    assert response.status_code == 404, response.text
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("skip, limit", [(0, 2), (1, 2), (3, 2), (4, 2), (0, 0)])
def test_list_node_assessments_pagination(
    client, api_create, assessment_payload, node_factory, skip, limit
):
    created = [api_create(PATH, assessment_payload)]
    for index in range(1, 4):
        node = node_factory()
        created.append(api_create(PATH, assessment_payload | {
            "gid": node["gid"],
            "evidence": f"Assessment {index}",
        }))

    response = client.get(PATH, params={"skip": skip, "limit": limit})

    assert response.status_code == 200, response.text
    assert response.json() == created[skip:skip + limit]


def test_patch_node_assessment_preserves_omitted_fields(client, api_create, assessment_payload):
    created = api_create(PATH, assessment_payload)
    item_path = f"{PATH}{created['id']}"

    response = client.patch(item_path, json={"priority_score": 0.95})

    assert response.status_code == 200, response.text
    updated = response.json()
    expected = created | {"priority_score": 0.95}
    assert {field: value for field, value in updated.items() if field != "updated_at"} == {
        field: value for field, value in expected.items() if field != "updated_at"
    }
    assert datetime.fromisoformat(updated["updated_at"])
    fetched = client.get(item_path)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == updated


def test_patch_node_assessment_allows_explicit_null_pass_through(
    client, api_create, assessment_payload
):
    created = api_create(PATH, assessment_payload)
    item_path = f"{PATH}{created['id']}"

    response = client.patch(item_path, json={"pass_through": None})

    assert response.status_code == 200, response.text
    updated = response.json()
    expected = created | {"pass_through": None}
    assert {field: value for field, value in updated.items() if field != "updated_at"} == {
        field: value for field, value in expected.items() if field != "updated_at"
    }
    fetched = client.get(item_path)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == updated


def test_delete_node_assessment(client, api_create, assessment_payload):
    created = api_create(PATH, assessment_payload)
    item_path = f"{PATH}{created['id']}"

    response = client.delete(item_path)

    assert response.status_code == 204, response.text
    assert response.content == b""
    fetched = client.get(item_path)
    assert fetched.status_code == 404, fetched.text
