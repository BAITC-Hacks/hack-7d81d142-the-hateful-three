"""JWT, password handling, and real HTTP authentication against disposable SQLite."""

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import jwt
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.config import Settings, settings
from backend.core.database import create_db_engine
from backend.core.rate_limit import limiter
from backend.core.security import (
    SecurityConfigurationError,
    create_access_token,
    hash_password,
    verify_password,
    verify_token,
)
from backend.main import app
from backend.models import Base, User
from backend.tests.test_api import TrackingSession


TEST_SECRET = "auth-test-secret-for-signing-and-verification-" * 2
PASSWORD = "correct-password-123"
BUSINESS_ROUTES = ("nodes", "edges", "transactions", "clusters", "node-assessments", "ranked-nodes")


class SecurityTests(unittest.TestCase):
    def setUp(self):
        secret_patch = patch.object(settings, "jwt_secret_key", SecretStr(TEST_SECRET))
        secret_patch.start()
        self.addCleanup(secret_patch.stop)

    def test_password_hashes_are_salted_and_verify_only_the_original(self):
        first = hash_password(PASSWORD)
        second = hash_password(PASSWORD)
        self.assertTrue(first.startswith("$2"))
        self.assertNotEqual(first, PASSWORD)
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password(PASSWORD, first))
        self.assertTrue(verify_password(PASSWORD, second))
        self.assertFalse(verify_password("wrong-password", first))
        self.assertFalse(verify_password(PASSWORD, "malformed-stored-hash"))

    def test_access_token_round_trip_uses_configured_lifetime(self):
        with patch.object(settings, "access_token_expire_minutes", 7):
            token = create_access_token("42")
        payload = verify_token(token)
        self.assertEqual(jwt.get_unverified_header(token)["alg"], "HS256")
        self.assertEqual(payload["sub"], "42")
        self.assertEqual(payload["type"], "access")
        self.assertEqual(payload["exp"] - payload["iat"], 7 * 60)
        self.assertNotIn("password", payload)
        custom = verify_token(create_access_token("42", expires_delta=timedelta(seconds=45)))
        self.assertEqual(custom["exp"] - custom["iat"], 45)

    def test_missing_secret_fails_closed(self):
        token = create_access_token("42")
        with patch.object(settings, "jwt_secret_key", None):
            with self.assertRaises(SecurityConfigurationError):
                create_access_token("42")
            with self.assertRaises(SecurityConfigurationError):
                verify_token(token)

    def test_settings_reject_short_signing_keys_and_nonpositive_lifetimes(self):
        for secret, lifetime in [("short-secret", 30), (TEST_SECRET, 0), (TEST_SECRET, -1)]:
            with self.subTest(secret=secret, lifetime=lifetime):
                with self.assertRaises(ValidationError):
                    Settings(_env_file=None, jwt_secret_key=secret, access_token_expire_minutes=lifetime)
        config = Settings(_env_file=None, jwt_secret_key=TEST_SECRET, access_token_expire_minutes=1)
        self.assertEqual(config.jwt_secret_key.get_secret_value(), TEST_SECRET)
        self.assertNotIn(TEST_SECRET, repr(config))

    def test_verify_token_rejects_expired_and_invalid_claims(self):
        with self.assertRaises(jwt.InvalidTokenError):
            verify_token(create_access_token("42", expires_delta=timedelta(seconds=-1)))
        now = int(datetime.now(timezone.utc).timestamp())
        claims = {"sub": "42", "iat": now, "exp": now + 300, "type": "access"}
        invalid_payloads = [claims | {"type": "refresh"}]
        invalid_payloads.extend({key: value for key, value in claims.items() if key != missing}
                                for missing in claims)
        invalid_payloads.extend(claims | {"sub": subject}
                                for subject in [42, "", "0", "-1", "1.5", "2147483648"])
        invalid_payloads.extend(claims | {field: value}
                                for field in ["exp", "iat"]
                                for value in [[], {}, str(now + 300), True, now + 0.5])
        invalid_payloads.append(claims | {"iat": now + 300, "exp": now + 600})
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                token = jwt.encode(payload, TEST_SECRET, algorithm="HS256")
                with self.assertRaises(jwt.InvalidTokenError):
                    verify_token(token)
        for token in [
            "not-a-token",
            jwt.encode(claims, "different-signing-key-" * 4, algorithm="HS256"),
            jwt.encode(claims, TEST_SECRET, algorithm="HS512"),
            jwt.encode(claims, "", algorithm="none"),
        ]:
            with self.subTest(token=token):
                with self.assertRaises(jwt.InvalidTokenError):
                    verify_token(token)


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        limiter.reset()
        self.addCleanup(limiter.reset)
        secret_patch = patch.object(settings, "jwt_secret_key", SecretStr(TEST_SECRET))
        secret_patch.start()
        self.addCleanup(secret_patch.stop)
        self.engine = create_db_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.events = []
        self.session_factory = sessionmaker(
            self.engine, class_=TrackingSession, info={"events": self.events},
        )
        factory_patch = patch(
            "backend.core.database.get_session_factory", return_value=self.session_factory,
        )
        factory_patch.start()
        self.addCleanup(factory_patch.stop)

        async def observe_response(scope, receive, send):
            async def record_send(message):
                if message["type"] == "http.response.start":
                    self.events.append(("response", message["status"]))
                await send(message)
            await app(scope, receive, record_send)

        self.client = TestClient(observe_response, raise_server_exceptions=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def register(self, email="reader@example.com", password=PASSWORD):
        response = self.client.post("/auth/register", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def login(self, email="reader@example.com", password=PASSWORD):
        response = self.client.post("/auth/login", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def assert_unauthorized(self, response):
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(response.headers.get("WWW-Authenticate"), "Bearer")

    def test_registration_login_and_authenticated_identity(self):
        registration = self.register("  Reader@Example.COM  ")
        user_fields = {"id", "email", "created_at", "updated_at"}
        self.assertEqual(set(registration), user_fields | {"access_token", "token_type"})
        user = {field: registration[field] for field in user_fields}
        self.assertEqual(user["email"], "reader@example.com")
        self.assertTrue(user["created_at"])
        self.assertTrue(user["updated_at"])
        self.assertEqual(self.events, ["commit", "close", ("response", 201)])
        with Session(self.engine) as session:
            saved = session.get(User, user["id"])
            self.assertTrue(saved.hashed_password.startswith("$2"))
            self.assertNotEqual(saved.hashed_password, PASSWORD)
            self.assertTrue(verify_password(PASSWORD, saved.hashed_password))
        for source in ["registration", "login"]:
            with self.subTest(source=source):
                credentials = registration if source == "registration" else self.login("  READER@EXAMPLE.com ")
                if source == "login":
                    self.assertEqual(set(credentials), {"access_token", "token_type"})
                self.assertEqual(credentials["token_type"], "bearer")
                self.assertEqual(verify_token(credentials["access_token"])["sub"], str(user["id"]))
                headers = {"Authorization": f"Bearer {credentials['access_token']}"}
                self.events.clear()
                current = self.client.get("/auth/me", headers=headers)
                self.assertEqual(current.status_code, 200, current.text)
                self.assertEqual(current.json(), user)
                self.assertEqual(self.events, ["commit", "close", ("response", 200)])
                for prefix in BUSINESS_ROUTES:
                    with self.subTest(path=f"/{prefix}/"):
                        response = self.client.get(f"/{prefix}/", headers=headers)
                        self.assertEqual(response.status_code, 200, response.text)

    def test_duplicate_email_normalization_and_failed_registration_rollback(self):
        user = self.register()
        self.events.clear()
        duplicate = self.client.post("/auth/register", json={
            "email": "  READER@EXAMPLE.COM ", "password": "different-password",
        })
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(self.events, ["rollback", "close", ("response", 409)])
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(User)), 1)
            self.assertTrue(verify_password(PASSWORD, session.get(User, user["id"]).hashed_password))
        self.register("another@example.com")

    def test_registration_commit_failure_is_500_and_does_not_save_user(self):
        self.session_factory.configure(info={"events": self.events, "fail_commit": True})
        response = self.client.post("/auth/register", json={
            "email": "uncommitted@example.com", "password": PASSWORD,
        })
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(self.events, ["commit", "rollback", "close", ("response", 500)])
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(User)), 0)
        self.session_factory.configure(info={"events": self.events})
        self.register("uncommitted@example.com")

    def test_bad_login_does_not_disclose_whether_email_exists(self):
        self.register()
        responses = [self.client.post("/auth/login", json={"email": email, "password": password})
                     for email, password in [("reader@example.com", "wrong-password"),
                                             ("unknown@example.com", PASSWORD)]]
        for response in responses:
            self.assert_unauthorized(response)
        self.assertEqual(responses[0].json(), responses[1].json())

    def test_invalid_email_and_password_input_is_rejected(self):
        for endpoint in ["/auth/register", "/auth/login"]:
            invalid_bodies = [
                {"email": "not-an-email", "password": PASSWORD},
                {"email": "", "password": PASSWORD},
                {"email": "reader@example.com", "password": ""},
                {"email": "reader@example.com", "password": "a" * 73},
                {"email": "reader@example.com", "password": "я" * 37},
                {"email": "reader@example.com", "password": "valid\x00password"},
                {"email": "reader@example.com"},
                {"password": PASSWORD},
                {"email": "reader@example.com", "password": PASSWORD, "unexpected": PASSWORD},
            ]
            if endpoint == "/auth/register":
                invalid_bodies.append({"email": "reader@example.com", "password": "x8P!r2q"})
            for body in invalid_bodies:
                with self.subTest(endpoint=endpoint, body=body):
                    response = self.client.post(endpoint, json=body)
                    self.assertEqual(response.status_code, 422, response.text)
                    # Pydantic's default error payload can otherwise echo plaintext passwords.
                    for error in response.json()["detail"]:
                        self.assertNotIn("input", error)
                        self.assertNotIn("ctx", error)
                    if body.get("password"):
                        self.assertNotIn(body["password"], response.text)
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(User)), 0)

    def test_72_byte_unicode_password_is_accepted_without_truncation(self):
        password = "я" * 36
        self.assertEqual(len(password.encode("utf-8")), 72)
        self.register(password=password)
        self.login(password=password)
        wrong = self.client.post("/auth/login", json={
            "email": "reader@example.com", "password": "я" * 35 + "ю",
        })
        self.assert_unauthorized(wrong)
        extended = self.client.post("/auth/login", json={
            "email": "reader@example.com", "password": password + "a",
        })
        self.assertEqual(extended.status_code, 422, extended.text)

    def test_every_business_crud_route_requires_authentication(self):
        for prefix in BUSINESS_ROUTES:
            for method, path in [("GET", f"/{prefix}/"), ("POST", f"/{prefix}/"),
                                 ("GET", f"/{prefix}/1"), ("PATCH", f"/{prefix}/1"),
                                 ("DELETE", f"/{prefix}/1")]:
                for headers in [{}, {"Authorization": "Bearer malformed"}]:
                    with self.subTest(method=method, path=path, headers=headers):
                        response = self.client.request(
                            method, path, headers=headers,
                            json={} if method in {"POST", "PATCH"} else None,
                        )
                        self.assert_unauthorized(response)
        self.assert_unauthorized(self.client.get("/auth/me"))

    def test_invalid_tokens_and_deleted_users_cannot_access_protected_routes(self):
        with Session(self.engine) as session:
            user = User(email="token@example.com", hashed_password="unused")
            session.add(user)
            session.flush()
            user_id = user.id
            session.commit()
        now = int(datetime.now(timezone.utc).timestamp())
        claims = {"sub": str(user_id), "iat": now, "exp": now + 300, "type": "access"}
        tokens = [
            "malformed",
            TEST_SECRET,
            create_access_token(str(user_id), expires_delta=timedelta(seconds=-1)),
            jwt.encode(claims, "wrong-key-for-integration-tests-" * 3, algorithm="HS256"),
            jwt.encode(claims | {"type": "refresh"}, TEST_SECRET, algorithm="HS256"),
            jwt.encode({key: value for key, value in claims.items() if key != "exp"}, TEST_SECRET, algorithm="HS256"),
            create_access_token("2147483647"),
        ]
        for token in tokens:
            with self.subTest(token=token):
                self.assert_unauthorized(self.client.get("/nodes/", headers={"Authorization": f"Bearer {token}"}))
        for authorization in ["Basic credentials", "Bearer", "Bearer "]:
            with self.subTest(authorization=authorization):
                self.assert_unauthorized(self.client.get("/auth/me", headers={"Authorization": authorization}))
        for request_options in [
            {"headers": {"X-API-Key": TEST_SECRET}},
            {"params": {"api_key": TEST_SECRET}},
            {"params": {"token": TEST_SECRET}},
        ]:
            with self.subTest(request_options=request_options):
                self.assert_unauthorized(self.client.get("/nodes/", **request_options))
        original_token = create_access_token(str(user_id))
        with Session(self.engine) as session:
            session.delete(session.get(User, user_id))
            session.commit()
            session.add(User(email="replacement@example.com", hashed_password="unused"))
            session.commit()
        self.assert_unauthorized(self.client.get("/auth/me", headers={"Authorization": f"Bearer {original_token}"}))

    def test_missing_secret_returns_503_but_health_and_docs_stay_public(self):
        user = self.register()
        token = create_access_token(str(user["id"]))
        with patch.object(settings, "jwt_secret_key", None):
            self.events.clear()
            registration = self.client.post("/auth/register", json={
                "email": "unsigned@example.com", "password": PASSWORD,
            })
            self.assertEqual(registration.status_code, 503, registration.text)
            self.assertEqual(self.events, ["rollback", "close", ("response", 503)])
            with Session(self.engine) as session:
                self.assertEqual(session.scalar(select(func.count()).select_from(User)), 1)
            login = self.client.post("/auth/login", json={"email": user["email"], "password": PASSWORD})
            self.assertEqual(login.status_code, 503, login.text)
            current = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(current.status_code, 503, current.text)
            with patch("backend.core.database.get_session_factory", side_effect=RuntimeError("Database unavailable")):
                for path in ["/health", "/docs", "/openapi.json"]:
                    with self.subTest(path=path):
                        response = self.client.get(path)
                        self.assertEqual(response.status_code, 200, response.text)

    def test_cors_preflight_allows_bearer_authorization_header(self):
        response = self.client.options("/nodes/", headers={
            "Origin": settings.cors_origins[0],
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("authorization", response.headers["Access-Control-Allow-Headers"].lower())


if __name__ == "__main__":
    unittest.main()
