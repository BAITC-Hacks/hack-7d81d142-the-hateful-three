"""Exercise browser access and throttling through the real authentication API."""

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy import func, select

from backend.core.config import Settings, settings
from backend.core.rate_limit import limiter
from backend.main import app
from backend.models import User


@pytest.fixture(autouse=True)
def fresh_rate_limits(monkeypatch):
    limiter.reset()
    monkeypatch.setattr(settings, "login_rate_limit", "2/minute")
    monkeypatch.setattr(settings, "register_rate_limit", "2/minute")
    yield
    limiter.reset()


def test_registration_counts_conflicts_and_blocks_before_creating_user(client, db_session_factory):
    body = {"email": "limited@example.com", "password": "rate-test-password"}
    first = client.post("/auth/register", json=body)
    assert first.status_code == 201
    assert first.headers["X-RateLimit-Limit"] == "2"
    assert client.post("/auth/register", json=body).status_code == 409

    blocked = client.post("/auth/register", json=body | {"email": "blocked@example.com"})
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert blocked.headers["X-RateLimit-Remaining"] == "0"
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(User).where(
            User.email == "blocked@example.com",
        )) == 0


def test_login_counts_failed_attempts_and_returns_cors_on_429(client):
    body = {"email": "login-limit@example.com", "password": "rate-test-password"}
    assert client.post("/auth/register", json=body).status_code == 201
    assert client.post("/auth/login", json=body | {"password": "wrong-password"}).status_code == 401
    assert client.post("/auth/login", json=body).status_code == 200
    origin = settings.cors_origins[0]
    blocked = client.post("/auth/login", json=body, headers={"Origin": origin})
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert blocked.headers["access-control-allow-origin"] == origin
    assert "Retry-After" in blocked.headers["access-control-expose-headers"]

    # Exhausting login must not prevent a demo or the authenticated API.
    for path in ["/health", "/docs", "/redoc", "/openapi.json", "/nodes/"]:
        assert client.get(path).status_code == 200


def test_client_addresses_have_independent_buckets_and_forwarded_header_cannot_bypass(client):
    body = {"email": "unknown@example.com", "password": "rate-test-password"}
    with TestClient(app, client=("192.0.2.1", 1234)) as first:
        for _ in range(2):
            assert first.post("/auth/login", json=body).status_code == 401
        blocked = first.post("/auth/login", json=body, headers={"X-Forwarded-For": "192.0.2.99"})
        assert blocked.status_code == 429
    with TestClient(app, client=("192.0.2.2", 1234)) as second:
        assert second.post("/auth/login", json=body).status_code == 401


@pytest.mark.parametrize("origin", settings.cors_origins)
def test_allowed_origins_can_preflight_and_read_public_response(client, origin):
    preflight = client.options("/nodes/", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "Authorization, Content-Type",
    })
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    response = client.get("/health", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_unlisted_origin_is_not_allowed(client):
    headers = {"Origin": "https://unlisted.example", "Access-Control-Request-Method": "GET"}
    response = client.options("/nodes/", headers=headers)
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-origin" not in client.get("/health", headers=headers).headers


@pytest.mark.parametrize("value", ["invalid", "0/minute", "1/minute; 0/hour"])
@pytest.mark.parametrize("field", ["login_rate_limit", "register_rate_limit"])
def test_invalid_rate_limit_configuration_fails_at_startup(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})
