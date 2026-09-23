"""Integration tests for transactions backed by existing directed edges."""

from datetime import datetime

import pytest


@pytest.fixture
def transaction_payload(edge_factory):
    edge = edge_factory()
    return {
        "row_id": 101,
        "src": edge["src"],
        "dst": edge["dst"],
        "date": "2026-07-01",
        "sum_kzt": "5432.10",
    }


def test_create_transaction(client, transaction_payload):
    response = client.post("/transactions/", json=transaction_payload)

    assert response.status_code == 201, response.text
    created = response.json()
    assert set(created) == set(transaction_payload) | {"id", "created_at", "updated_at"}
    assert {field: created[field] for field in transaction_payload} == transaction_payload
    assert isinstance(created["id"], int) and created["id"] > 0
    assert datetime.fromisoformat(created["created_at"])
    assert datetime.fromisoformat(created["updated_at"])
    fetched = client.get(f"/transactions/{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == created


def test_duplicate_transaction_returns_409(client, api_create, transaction_payload):
    created = api_create("/transactions/", transaction_payload)

    response = client.post(
        "/transactions/", json=transaction_payload | {"sum_kzt": "999.99"},
    )

    assert response.status_code == 409, response.text
    assert isinstance(response.json()["detail"], str)
    fetched = client.get(f"/transactions/{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == created
    listed = client.get("/transactions/")
    assert listed.status_code == 200, listed.text
    assert listed.json() == [created]


def test_get_missing_transaction_returns_404(client):
    response = client.get("/transactions/999999")

    assert response.status_code == 404, response.text
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("skip, limit", [(0, 2), (1, 2), (3, 10), (0, 0), (8, 2)])
def test_list_transactions_pagination(client, api_create, transaction_payload, skip, limit):
    created = [
        api_create("/transactions/", transaction_payload | {"row_id": row_id})
        for row_id in [40, 10, 30, 20]
    ]

    response = client.get("/transactions/", params={"skip": skip, "limit": limit})

    assert response.status_code == 200, response.text
    assert response.json() == created[skip:skip + limit]


def test_patch_transaction_preserves_omitted_fields(client, api_create, transaction_payload):
    created = api_create("/transactions/", transaction_payload)
    item_path = f"/transactions/{created['id']}"

    response = client.patch(item_path, json={"sum_kzt": "6000.02"})

    assert response.status_code == 200, response.text
    updated = response.json()
    assert set(updated) == set(created)
    assert {field: value for field, value in updated.items() if field != "updated_at"} == {
        field: value for field, value in (created | {"sum_kzt": "6000.02"}).items()
        if field != "updated_at"
    }
    assert datetime.fromisoformat(updated["updated_at"])
    fetched = client.get(item_path)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == updated


def test_delete_transaction(client, api_create, transaction_payload):
    created = api_create("/transactions/", transaction_payload)
    item_path = f"/transactions/{created['id']}"

    response = client.delete(item_path)

    assert response.status_code == 204, response.text
    assert response.content == b""
    fetched = client.get(item_path)
    assert fetched.status_code == 404, fetched.text


def test_transaction_requires_an_existing_directed_edge(client, transaction_payload):
    # Both nodes exist, but the prerequisite edge exists only in the opposite direction.
    response = client.post("/transactions/", json=transaction_payload | {
        "src": transaction_payload["dst"],
        "dst": transaction_payload["src"],
    })

    assert response.status_code == 404, response.text
    assert "Edge not found" in response.json()["detail"]
    listed = client.get("/transactions/")
    assert listed.status_code == 200, listed.text
    assert listed.json() == []


def test_identical_transactions_with_distinct_row_ids_are_allowed(
    client, api_create, transaction_payload,
):
    first = api_create("/transactions/", transaction_payload)
    second_payload = transaction_payload | {"row_id": transaction_payload["row_id"] + 1}

    response = client.post("/transactions/", json=second_payload)

    assert response.status_code == 201, response.text
    second = response.json()
    assert second["id"] != first["id"]
    assert {field: second[field] for field in second_payload} == second_payload
    listed = client.get("/transactions/")
    assert listed.status_code == 200, listed.text
    assert listed.json() == [first, second]
