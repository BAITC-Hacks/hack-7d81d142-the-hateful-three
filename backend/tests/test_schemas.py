"""Check Pydantic contracts without a server or database connection.

Run from the project root:
    python -m unittest backend.tests.test_schemas -v
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import json
import unittest

from pydantic import ValidationError

from backend import models, schemas


PAYLOADS = {
    "Node": {"gid": "source", "depth": 0, "is_seed": True},
    "Edge": {
        "src": "source", "dst": "destination", "sum_kzt": "100.25",
        "n_tx": 1, "depth": 1,
    },
    "Transaction": {
        "row_id": 0, "src": "source", "dst": "destination",
        "date": "2026-09-23", "sum_kzt": "100.25",
    },
    "Cluster": {
        "cluster_id": 0, "n_nodes": 2, "n_seed": 1,
        "sum_kzt_internal": "100.25", "top_gids": ["source"],
        "hypothesis": "Two connected nodes",
    },
    "NodeAssessment": {
        "gid": "source", "role": "transit", "role_score": 0.7,
        "cluster_id": 0, "priority_score": 0.8, "evidence": "1 transfer",
        "in_deg": 0, "out_deg": 1, "in_tx": 0, "out_tx": 1,
        "in_kzt": "0.00", "out_kzt": "100.25", "pagerank": 0.1,
        "pass_through": None, "truncated_by_depth": False,
    },
    "RankedNode": {
        "rank": 1, "gid": "source", "role": "transit",
        "priority_score": 0.8, "why": "One transfer",
    },
}

TIMESTAMP = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
SERVER_FIELDS = {"id": 1, "created_at": TIMESTAMP, "updated_at": TIMESTAMP}


class SchemaTests(unittest.TestCase):
    def test_create_accepts_valid_json_for_each_entity(self):
        for name, payload in PAYLOADS.items():
            with self.subTest(entity=name):
                create_type = getattr(schemas, name + "Create")
                request = create_type.model_validate_json(json.dumps(payload))
                self.assertEqual(request.model_dump(mode="json"), payload)

    def test_create_requires_entity_fields(self):
        for name in PAYLOADS:
            with self.subTest(entity=name):
                with self.assertRaises(ValidationError):
                    getattr(schemas, name + "Create")()

    def test_requests_do_not_expose_server_managed_fields(self):
        for name, payload in PAYLOADS.items():
            for suffix in ("Create", "Update"):
                with self.subTest(entity=name, schema=suffix):
                    request_type = getattr(schemas, name + suffix)
                    request = request_type.model_validate(payload | SERVER_FIELDS)
                    self.assertTrue(SERVER_FIELDS.keys().isdisjoint(request.model_dump()))

    def test_update_accepts_empty_and_single_field_patches(self):
        for name, payload in PAYLOADS.items():
            update_type = getattr(schemas, name + "Update")
            with self.subTest(entity=name, patch="empty"):
                self.assertEqual(update_type().model_dump(exclude_unset=True), {})
            for field, value in payload.items():
                with self.subTest(entity=name, field=field):
                    patch = update_type.model_validate({field: value})
                    self.assertEqual(
                        patch.model_dump(mode="json", exclude_unset=True), {field: value}
                    )

    def test_update_distinguishes_explicit_null_from_omitted_fields(self):
        # Every Update field is Optional; exclude_unset preserves explicit null.
        for name, payload in PAYLOADS.items():
            update_type = getattr(schemas, name + "Update")
            for field in payload:
                with self.subTest(entity=name, field=field):
                    patch = update_type.model_validate({field: None})
                    self.assertEqual(patch.model_dump(exclude_unset=True), {field: None})

    def test_response_reads_sqlalchemy_objects_and_serializes_json(self):
        for name, payload in PAYLOADS.items():
            with self.subTest(entity=name):
                request = getattr(schemas, name + "Create").model_validate(payload)
                # Supply generated columns explicitly: no database is needed.
                entity = getattr(models, name)(**request.model_dump(), **SERVER_FIELDS)
                response = getattr(schemas, name + "Response").model_validate(entity)
                self.assertEqual(response.model_dump(), request.model_dump() | SERVER_FIELDS)
                self.assertEqual(
                    json.loads(response.model_dump_json()),
                    payload | {
                        "id": 1,
                        "created_at": "2026-09-23T12:00:00Z",
                        "updated_at": "2026-09-23T12:00:00Z",
                    },
                )

    def test_invalid_values_are_rejected_in_create_and_update(self):
        invalid_fields = {
            "Node": {"gid": "x" * 33, "depth": 5},
            "Edge": {"sum_kzt": "-0.01", "n_tx": 0, "depth": 0},
            "Transaction": {"row_id": -1, "date": "invalid", "sum_kzt": "0.001"},
            "Cluster": {
                "n_nodes": -1, "n_seed": -1, "top_gids": ["x" * 33],
                "sum_kzt_internal": "1000000000000000000.00",
            },
            "NodeAssessment": {
                "role": "invalid", "role_score": 1.1, "priority_score": -0.1,
                "evidence": "x" * 201, "in_deg": -1, "out_deg": -1,
                "in_tx": -1, "out_tx": -1, "in_kzt": "-1", "out_kzt": "-1",
                "pagerank": -1, "pass_through": -1,
            },
            "RankedNode": {"rank": 0, "role": "invalid", "priority_score": 1.1},
        }
        for name, invalid in invalid_fields.items():
            for field, value in invalid.items():
                for suffix in ("Create", "Update"):
                    with self.subTest(entity=name, schema=suffix, field=field):
                        payload = PAYLOADS[name] if suffix == "Create" else {}
                        request_type = getattr(schemas, name + suffix)
                        with self.assertRaises(ValidationError) as raised:
                            request_type.model_validate(payload | {field: value})
                        self.assertIn(field, {error["loc"][0] for error in raised.exception.errors()})

    def test_dates_amounts_and_roles_keep_their_python_types(self):
        transaction = schemas.TransactionCreate(**PAYLOADS["Transaction"])
        self.assertEqual(transaction.date, date(2026, 9, 23))
        self.assertIsInstance(transaction.date, date)
        self.assertEqual(transaction.sum_kzt, Decimal("100.25"))
        self.assertIsInstance(transaction.sum_kzt, Decimal)
        assessment = schemas.NodeAssessmentCreate(**PAYLOADS["NodeAssessment"])
        self.assertIs(assessment.role, models.NodeRole.TRANSIT)

    def test_defaults_are_independent_and_valid_boundaries_are_accepted(self):
        self.assertFalse(schemas.NodeCreate(gid="node", depth=0).is_seed)
        cluster_payload = {key: value for key, value in PAYLOADS["Cluster"].items() if key != "top_gids"}
        first = schemas.ClusterCreate(**cluster_payload)
        second = schemas.ClusterCreate(**cluster_payload)
        first.top_gids.append("source")
        self.assertEqual(second.top_gids, [])

        assessment_payload = {
            key: value for key, value in PAYLOADS["NodeAssessment"].items()
            if key != "pass_through"
        }
        self.assertIsNone(schemas.NodeAssessmentCreate(**assessment_payload).pass_through)
        self.assertEqual(schemas.NodeAssessmentUpdate(pass_through=2.5).pass_through, 2.5)
        self.assertEqual(schemas.NodeUpdate(depth=4).depth, 4)
        for amount in ("0.00", "999999999999999999.99"):
            with self.subTest(amount=amount):
                self.assertEqual(schemas.EdgeUpdate(sum_kzt=amount).sum_kzt, Decimal(amount))
        for score in (0, 1):
            with self.subTest(score=score):
                self.assertEqual(schemas.RankedNodeUpdate(priority_score=score).priority_score, score)

    def test_user_response_excludes_password_hash(self):
        user = models.User(
            email="schema-test@example.com",
            hashed_password="test-only-password-hash",
            **SERVER_FIELDS,
        )
        response = schemas.UserResponse.model_validate(user)
        self.assertEqual(set(response.model_dump()), {"id", "created_at", "updated_at", "email"})
        self.assertEqual(response.email, user.email)
        self.assertNotIn(user.hashed_password, response.model_dump_json())


if __name__ == "__main__":
    unittest.main()
