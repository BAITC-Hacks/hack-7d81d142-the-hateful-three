"""HTTP CRUD and request transaction checks against disposable SQLite."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.config import settings
from backend.core.database import create_db_engine
from backend.core.security import create_access_token
from backend.main import app
from backend.models import Base, Cluster, Edge, Node, NodeAssessment, User


class TrackingSession(Session):
    """Record transaction boundaries without replacing real SQL operations."""

    def commit(self):
        self.info["events"].append("commit")
        if self.info.get("fail_commit"):
            raise RuntimeError("Simulated commit failure")
        return super().commit()

    def rollback(self):
        self.info["events"].append("rollback")
        return super().rollback()

    def close(self):
        self.info["events"].append("close")
        return super().close()


class ApiTests(unittest.TestCase):
    def setUp(self):
        secret_patch = patch.object(settings, "jwt_secret_key", SecretStr("api-tests-secret-" * 4))
        secret_patch.start()
        self.addCleanup(secret_patch.stop)
        self.engine = create_db_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            user = User(email="crud@example.com", hashed_password="unused")
            session.add_all([
                user,
                Node(gid="a", depth=0, is_seed=True),
                Node(gid="b", depth=1),
                Node(gid="c", depth=2),
                Cluster(cluster_id=42, n_nodes=3, n_seed=1,
                        sum_kzt_internal=10000, top_gids=["a", "b"],
                        hypothesis="baseline"),
            ])
            session.flush()
            token = create_access_token(str(user.id))
            session.add(Edge(src="a", dst="b", sum_kzt=10000, n_tx=2, depth=1))
            session.add(NodeAssessment(**(self.cases()[4][1] | {"gid": "c"})))
            session.commit()

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
        self.client.headers["Authorization"] = f"Bearer {token}"
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    @staticmethod
    def cases():
        """JSON create/patch bodies with distinct business and technical IDs."""
        return [
            ("/nodes/", {"gid": "new", "depth": 3}, {"depth": 4}),
            ("/edges/", {"src": "b", "dst": "c", "sum_kzt": "5000.01",
                         "n_tx": 1, "depth": 2}, {"n_tx": 2}),
            ("/transactions/", {"row_id": 10, "src": "a", "dst": "b",
                                "date": "2026-07-01", "sum_kzt": "5000.01"},
             {"sum_kzt": "6000.02"}),
            ("/clusters/", {"cluster_id": 99, "n_nodes": 2, "n_seed": 1,
                            "sum_kzt_internal": "0.00", "hypothesis": "new"},
             {"hypothesis": "changed"}),
            ("/node-assessments/", {
                "gid": "a", "role": "transit", "role_score": 0.7,
                "cluster_id": 42, "priority_score": 0.8, "evidence": "2 transfers",
                "in_deg": 0, "out_deg": 1, "in_tx": 0, "out_tx": 2,
                "in_kzt": "0.00", "out_kzt": "10000.02", "pagerank": 0.1,
                "pass_through": 1.5, "truncated_by_depth": False,
            }, {"priority_score": 0.9}),
            ("/ranked-nodes/", {"gid": "c", "rank": 1, "role": "transit",
                                "priority_score": 0.8, "why": "2 transfers"},
             {"why": "updated explanation"}),
        ]

    def create(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_http_crud_and_pagination_for_every_entity(self):
        for path, body, changes in self.cases():
            with self.subTest(path=path):
                initial = self.client.get(path)
                self.assertEqual(initial.status_code, 200, initial.text)
                before = len(initial.json())
                created = self.create(path, body)
                self.assertIsInstance(created["id"], int)
                self.assertTrue(created["created_at"])
                self.assertTrue(created["updated_at"])
                item_path = f"{path}{created['id']}"

                fetched = self.client.get(item_path)
                self.assertEqual(fetched.status_code, 200, fetched.text)
                self.assertEqual(fetched.json(), created)
                page = self.client.get(path, params={"skip": before, "limit": 1})
                self.assertEqual(page.status_code, 200, page.text)
                self.assertEqual(page.json(), [created])
                self.assertEqual(self.client.get(path, params={"limit": 0}).json(), [])
                self.assertEqual(self.client.get(path, params={"skip": 999}).json(), [])

                updated = self.client.patch(item_path, json=changes)
                self.assertEqual(updated.status_code, 200, updated.text)
                expected = created | changes
                for field, value in expected.items():
                    if field != "updated_at":
                        self.assertEqual(updated.json()[field], value, field)
                self.assertEqual(self.client.get(item_path).json(), updated.json())

                deleted = self.client.delete(item_path)
                self.assertEqual(deleted.status_code, 204, deleted.text)
                self.assertEqual(deleted.content, b"")
                self.assertEqual(self.client.get(item_path).status_code, 404)
                self.assertEqual(len(self.client.get(path).json()), before)

    def test_missing_entities_are_404_for_read_patch_and_delete(self):
        for path, _, _ in self.cases():
            for method, kwargs in (("GET", {}), ("PATCH", {"json": {}}), ("DELETE", {})):
                with self.subTest(path=path, method=method):
                    response = self.client.request(method, f"{path}99999", **kwargs)
                    self.assertEqual(response.status_code, 404, response.text)
                    self.assertIsInstance(response.json()["detail"], str)

    def test_duplicate_business_keys_are_409_for_every_entity(self):
        for path, body, _ in self.cases():
            with self.subTest(path=path):
                created = self.create(path, body)
                duplicate = self.client.post(path, json=body)
                self.assertEqual(duplicate.status_code, 409, duplicate.text)
                self.assertIsInstance(duplicate.json()["detail"], str)
                self.assertEqual(self.client.get(f"{path}{created['id']}").json(), created)

    def test_patch_distinguishes_omitted_fields_from_explicit_null(self):
        for path, body, changes in self.cases():
            with self.subTest(path=path):
                created = self.create(path, body)
                item_path = f"{path}{created['id']}"
                unchanged = self.client.patch(item_path, json={})
                self.assertEqual(unchanged.status_code, 200, unchanged.text)
                self.assertEqual(unchanged.json(), created)
                field = next(iter(changes))
                invalid = self.client.patch(item_path, json={field: None})
                self.assertEqual(invalid.status_code, 422, invalid.text)
                self.assertIsInstance(invalid.json()["detail"], str)
                self.assertEqual(self.client.get(item_path).json(), created)
                if path == "/node-assessments/":
                    changed = self.client.patch(item_path, json={"evidence": "changed: 2 transfers"})
                    self.assertEqual(changed.status_code, 200, changed.text)
                    self.assertEqual(changed.json()["pass_through"], 1.5)
                    cleared = self.client.patch(item_path, json={"pass_through": None})
                    self.assertEqual(cleared.status_code, 200, cleared.text)
                    self.assertIsNone(cleared.json()["pass_through"])
                    self.assertIsNone(self.client.get(item_path).json()["pass_through"])

    def test_service_and_request_validation_both_return_422(self):
        path, body, _ = self.cases()[3]
        invalid = self.client.post(path, json=body | {"n_seed": 3})
        self.assertEqual(invalid.status_code, 422, invalid.text)
        self.assertIsInstance(invalid.json()["detail"], str)
        created = self.create(path, body)
        item_path = f"{path}{created['id']}"
        invalid_patch = self.client.patch(item_path, json={"n_nodes": 0})
        self.assertEqual(invalid_patch.status_code, 422, invalid_patch.text)
        self.assertEqual(self.client.get(item_path).json(), created)

        for method, url, kwargs in [
            ("POST", "/nodes/", {"json": {"gid": "invalid", "depth": 5}}),
            ("POST", "/nodes/", {"json": {"depth": 1}}),
            ("GET", "/nodes/not-an-integer", {}),
            ("GET", "/nodes/", {"params": {"skip": -1}}),
            ("GET", "/nodes/", {"params": {"limit": -1}}),
            ("GET", "/nodes/", {"params": {"limit": "abc"}}),
        ]:
            with self.subTest(method=method, url=url, kwargs=kwargs):
                response = self.client.request(method, url, **kwargs)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIsInstance(response.json()["detail"], list)

    def test_missing_service_reference_returns_404(self):
        _, body, _ = self.cases()[1]
        response = self.client.post("/edges/", json=body | {"src": "missing"})
        self.assertEqual(response.status_code, 404, response.text)
        self.assertIsInstance(response.json()["detail"], str)

    def test_failed_foreign_key_flush_rolls_back_and_next_request_commits(self):
        with Session(self.engine) as reader:
            node_id = reader.scalar(select(Node.id).where(Node.gid == "a"))
        self.events.clear()
        response = self.client.delete(f"/nodes/{node_id}")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.events, ["rollback", "close", ("response", 409)])
        with Session(self.engine) as reader:
            self.assertEqual(reader.get(Node, node_id).gid, "a")
            self.assertIsNotNone(reader.scalar(select(Edge).where(Edge.src == "a")))

        self.events.clear()
        created = self.create("/nodes/", {"gid": "after-rollback", "depth": 1})
        self.assertEqual(self.events, ["commit", "close", ("response", 201)])
        with Session(self.engine) as reader:
            self.assertEqual(reader.get(Node, created["id"]).gid, "after-rollback")

    def test_commit_failure_rolls_back_before_sending_any_success_response(self):
        self.session_factory.configure(info={"events": self.events, "fail_commit": True})
        self.events.clear()
        response = self.client.post("/nodes/", json={"gid": "uncommitted", "depth": 1})
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(self.events, ["commit", "rollback", "close", ("response", 500)])
        with Session(self.engine) as reader:
            self.assertIsNone(reader.scalar(select(Node).where(Node.gid == "uncommitted")))


if __name__ == "__main__":
    unittest.main()
