"""Exercise the production error handlers and middleware without a database."""

import asyncio
import logging
import math
from time import perf_counter
import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.core.security import SecurityConfigurationError
from backend.main import app
from backend.services.exceptions import ConflictError, NotFoundError, ServiceError, ValidationError


class SpecializedNotFoundError(NotFoundError):
    """Handlers must also apply to a service exception's subclasses."""


class ErrorLoggingTests(unittest.TestCase):
    def setUp(self):
        test_app = FastAPI(
            exception_handlers=dict(app.exception_handlers),
            middleware=list(app.user_middleware),
        )

        @test_app.post("/success")
        async def success():
            await asyncio.sleep(0.01)
            return {"status": "ok"}

        @test_app.get("/validated/{item_id}")
        async def validated(item_id: int):
            return {"item_id": item_id}

        @test_app.get("/unauthorized")
        async def unauthorized():
            raise HTTPException(
                status_code=401,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        @test_app.get("/unavailable")
        async def unavailable():
            raise SecurityConfigurationError("sensitive authentication configuration")

        @test_app.get("/chained-error")
        async def chained_error():
            try:
                raise ValueError("sensitive original cause")
            except ValueError as exc:
                raise RuntimeError("sensitive outer failure") from exc

        self.service_errors = {
            "not-found": (NotFoundError("Node", "missing"), 404),
            "specialized-not-found": (SpecializedNotFoundError("Edge", 42), 404),
            "conflict": (ConflictError("Duplicate node"), 409),
            "validation": (ValidationError("Invalid business fields"), 422),
            "unknown-service": (ServiceError("sensitive service failure"), 500),
        }

        def error_endpoint(error):
            async def endpoint():
                raise error
            return endpoint

        for name, (error, _) in self.service_errors.items():
            test_app.add_api_route(f"/errors/{name}", error_endpoint(error))

        self.client = TestClient(test_app, raise_server_exceptions=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def assert_access_record(self, records, method, path, status_code):
        access_records = [record for record in records if record.name == "backend.access"]
        self.assertEqual(len(access_records), 1)
        record = access_records[0]
        self.assertEqual(record.method, method)
        self.assertEqual(record.path, path)
        self.assertEqual(record.status_code, status_code)
        level = logging.ERROR if status_code >= 500 else (
            logging.WARNING if status_code >= 400 else logging.INFO
        )
        self.assertEqual(record.levelno, level)
        self.assertIsInstance(record.duration_ms, (int, float))
        self.assertTrue(math.isfinite(record.duration_ms))
        self.assertGreaterEqual(record.duration_ms, 0)
        return record

    def test_service_error_bodies_and_warning_logs(self):
        for name, (error, expected_status) in self.service_errors.items():
            if expected_status == 500:
                continue
            with self.subTest(error=name), self.assertLogs("backend", level="INFO") as logs:
                response = self.client.get(f"/errors/{name}")
            self.assertEqual(response.status_code, expected_status)
            self.assertEqual(response.json(), {"detail": str(error)})
            self.assert_access_record(logs.records, "GET", f"/errors/{name}", expected_status)
            self.assertFalse(any(record.exc_info for record in logs.records))

    def test_uncaught_errors_hide_details_and_log_tracebacks(self):
        cases = [
            ("/chained-error", RuntimeError, "sensitive outer failure"),
            ("/errors/unknown-service", ServiceError, "sensitive service failure"),
        ]
        for path, exception_type, message in cases:
            with self.subTest(path=path), self.assertLogs("backend", level="INFO") as logs:
                response = self.client.get(path)
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json(), {"detail": "Internal server error"})
            self.assert_access_record(logs.records, "GET", path, 500)
            error_records = [record for record in logs.records if record.name == "backend.main"]
            self.assertEqual(len(error_records), 1)
            record = error_records[0]
            self.assertEqual(record.levelno, logging.ERROR)
            self.assertIsNotNone(record.exc_info)
            self.assertIsInstance(record.exc_info[1], exception_type)
            self.assertIsNotNone(record.exc_info[2])
            traceback = logging.Formatter().format(record)
            self.assertIn("Traceback (most recent call last):", traceback)
            self.assertIn(message, traceback)
            if path == "/chained-error":
                self.assertIsInstance(record.exc_info[1].__cause__, ValueError)
                self.assertIn("sensitive original cause", traceback)
                self.assertIn("chained_error", traceback)

    def test_success_timing_and_access_logs_exclude_secrets(self):
        secrets = ("private-query-value", "private-body-value", "private-auth-value")
        start = perf_counter()
        with self.assertLogs("backend.access", level="INFO") as logs:
            response = self.client.post(
                "/success",
                params={"token": secrets[0]},
                json={"password": secrets[1]},
                headers={"Authorization": f"Bearer {secrets[2]}"},
            )
        elapsed_ms = (perf_counter() - start) * 1000
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        record = self.assert_access_record(logs.records, "POST", "/success", 200)
        self.assertGreaterEqual(record.duration_ms, 8)
        self.assertLessEqual(record.duration_ms, elapsed_ms + 1)
        for secret in secrets:
            self.assertNotIn(secret, repr(record.__dict__))
        self.assertNotIn("?", record.path)

    def test_framework_errors_and_handled_503_log_actual_status(self):
        cases = [
            ("GET", "/missing-route", 404),
            ("GET", "/success", 405),
            ("GET", "/validated/not-an-integer", 422),
            ("GET", "/unauthorized", 401),
            ("GET", "/unavailable", 503),
        ]
        for method, path, expected_status in cases:
            with self.subTest(path=path), self.assertLogs("backend", level="INFO") as logs:
                response = self.client.request(method, path)
            self.assertEqual(response.status_code, expected_status)
            self.assert_access_record(logs.records, method, path, expected_status)
            self.assertFalse(any(record.exc_info for record in logs.records))
            if expected_status == 401:
                self.assertEqual(response.headers["WWW-Authenticate"], "Bearer")
            elif expected_status == 503:
                self.assertEqual(response.json(), {"detail": "Authentication is not configured"})

    def test_cors_preflight_is_logged_once(self):
        origin = settings.cors_origins[0] if settings.cors_origins else "https://example.test"
        with self.assertLogs("backend.access", level="INFO") as logs:
            response = self.client.options(
                "/success",
                headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
            )
        expected_status = 200 if settings.cors_origins else 400
        self.assertEqual(response.status_code, expected_status)
        self.assert_access_record(logs.records, "OPTIONS", "/success", expected_status)
        if expected_status == 200:
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], origin)


if __name__ == "__main__":
    unittest.main()
