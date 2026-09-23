"""Opt-in pytest fixtures for HTTP tests with a fresh SQLite database per test."""

from collections.abc import Iterator
from itertools import count

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core import database
from backend.core.config import settings
from backend.core.security import create_access_token
from backend.main import app
from backend.models import Base, User


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    # TestClient runs the app in another thread. StaticPool shares the same
    # in-memory database, and create_db_engine enables SQLite foreign keys.
    engine = database.create_db_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session_factory(db_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=db_engine, expire_on_commit=False)


@pytest.fixture
def client(db_session_factory: sessionmaker[Session], monkeypatch) -> Iterator[TestClient]:
    # Keep the application's real get_db commit/rollback/close lifecycle and
    # authentication dependencies; replace only the database and signing key.
    monkeypatch.setattr(database, "get_session_factory", lambda: db_session_factory)
    monkeypatch.setattr(settings, "jwt_secret_key", SecretStr("pytest-api-secret-" * 4))
    with db_session_factory() as session:
        user = User(email="pytest-api@example.com", hashed_password="unused-by-bearer-auth")
        session.add(user)
        session.commit()
        token = create_access_token(str(user.id))

    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as test_client:
        yield test_client


@pytest.fixture
def api_create(client):
    """Create setup records through the same HTTP API exercised by the tests."""
    def create(path, payload):
        response = client.post(path, json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return create


@pytest.fixture
def node_factory(api_create):
    sequence = count(1)

    def create(**overrides):
        payload = {
            "gid": f"fixture-node-{next(sequence)}",
            "depth": 0 if overrides.get("is_seed") else 1,
            "is_seed": False,
        }
        return api_create("/nodes/", payload | overrides)

    return create


@pytest.fixture
def assessment_factory(api_create, node_factory, cluster_factory):
    def create(**overrides):
        node = None if "gid" in overrides else node_factory()
        payload = {
            "gid": overrides.get("gid", node["gid"] if node else None),
            "cluster_id": overrides.get("cluster_id"),
            "role": "transit", "role_score": 0.7, "priority_score": 0.8,
            "evidence": "0 observed transfers", "in_deg": 0, "out_deg": 0,
            "in_tx": 0, "out_tx": 0, "in_kzt": "0.00", "out_kzt": "0.00",
            "pagerank": 0.0, "pass_through": None, "truncated_by_depth": False,
        }
        if payload["cluster_id"] is None:
            payload["cluster_id"] = cluster_factory()["cluster_id"]
        return api_create("/node-assessments/", payload | overrides)
    return create


@pytest.fixture
def edge_factory(api_create, node_factory):
    def create(**overrides):
        payload = {"sum_kzt": "10000.02", "n_tx": 2, "depth": 1} | overrides
        for endpoint in ("src", "dst"):
            if endpoint not in payload:
                payload[endpoint] = node_factory()["gid"]
        return api_create("/edges/", payload)

    return create


@pytest.fixture
def cluster_factory(api_create):
    sequence = count(1001)

    def create(**overrides):
        payload = {
            "cluster_id": next(sequence),
            "n_nodes": 4,
            "n_seed": 1,
            "sum_kzt_internal": "10000.02",
            "top_gids": [],
            "hypothesis": "Fixture cluster",
        }
        return api_create("/clusters/", payload | overrides)

    return create
