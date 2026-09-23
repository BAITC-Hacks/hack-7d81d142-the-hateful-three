"""Public pagination limits and stable traversal across the 100-row boundary."""

import pytest

from backend.models import Node


COLLECTION_PATHS = (
    "/nodes/",
    "/edges/",
    "/transactions/",
    "/clusters/",
    "/node-assessments/",
    "/ranked-nodes/",
)


@pytest.mark.parametrize("path", COLLECTION_PATHS)
@pytest.mark.parametrize("limit", [101, 1_000_000, -1])
def test_all_collection_routes_reject_invalid_limits(client, path, limit):
    response = client.get(path, params={"limit": limit})

    assert response.status_code == 422, response.text
    assert any(error["loc"] == ["query", "limit"] for error in response.json()["detail"])


@pytest.mark.parametrize("path", COLLECTION_PATHS)
def test_all_collection_routes_accept_maximum_limit(client, path):
    response = client.get(path, params={"skip": 0, "limit": 100})

    assert response.status_code == 200, response.text
    assert response.json() == []


def test_default_page_is_capped_and_next_page_has_no_gaps(client, db_session_factory):
    with db_session_factory() as session:
        nodes = [Node(gid=f"page-node-{index:03d}", depth=1) for index in range(105)]
        session.add_all(nodes)
        session.commit()
        expected_ids = [node.id for node in nodes]

    first = client.get("/nodes/")
    assert first.status_code == 200, first.text
    assert len(first.json()) == 100

    second = client.get("/nodes/", params={"skip": 100, "limit": 100})
    assert second.status_code == 200, second.text
    assert len(second.json()) == 5
    assert [node["id"] for node in first.json() + second.json()] == expected_ids

    empty = client.get("/nodes/", params={"limit": 0})
    assert empty.status_code == 200, empty.text
    assert empty.json() == []
