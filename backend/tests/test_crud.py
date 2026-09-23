"""Repository/service integration checks against disposable SQLite with FKs."""

from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.database import create_db_engine
from backend.models import Base, Cluster, Edge, Node, NodeRole
from backend.repositories import (
    ClusterRepository, EdgeRepository, NodeAssessmentRepository,
    NodeRepository, RankedNodeRepository, TransactionRepository,
)
from backend.schemas import (
    ClusterCreate, ClusterUpdate, EdgeCreate, EdgeUpdate,
    NodeAssessmentCreate, NodeAssessmentUpdate, NodeCreate, NodeUpdate,
    RankedNodeCreate, RankedNodeUpdate, TransactionCreate, TransactionUpdate,
)
from backend.services import (
    ClusterService, ConflictError, EdgeService, NodeAssessmentService,
    NodeService, NotFoundError, RankedNodeService, TransactionService, ValidationError,
)


class CrudTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_db_engine("sqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        self.session.add_all([
            Node(gid="a", depth=0, is_seed=True),
            Node(gid="b", depth=1),
            Node(gid="c", depth=2),
            Cluster(cluster_id=42, n_nodes=3, n_seed=1, sum_kzt_internal=10000,
                    top_gids=["a", "b"], hypothesis="baseline"),
        ])
        self.session.flush()
        self.session.add(Edge(src="a", dst="b", sum_kzt=10000, n_tx=2, depth=1))
        self.session.commit()

    def cases(self):
        """A valid independent create/update pair for each of the six entities."""
        return [
            (NodeRepository, NodeService,
             NodeCreate(gid="new", depth=3), NodeUpdate(depth=4)),
            (EdgeRepository, EdgeService,
             EdgeCreate(src="b", dst="c", sum_kzt="5000.01", n_tx=1, depth=2),
             EdgeUpdate(n_tx=2)),
            (TransactionRepository, TransactionService,
             TransactionCreate(row_id=10, src="a", dst="b", date=date(2026, 7, 1), sum_kzt="5000.01"),
             TransactionUpdate(sum_kzt="6000.02")),
            (ClusterRepository, ClusterService,
             ClusterCreate(cluster_id=99, n_nodes=2, n_seed=1, sum_kzt_internal=0, hypothesis="new"),
             ClusterUpdate(hypothesis="changed")),
            (NodeAssessmentRepository, NodeAssessmentService,
             NodeAssessmentCreate(
                 gid="a", role=NodeRole.TRANSIT, role_score=0.7, cluster_id=42,
                 priority_score=0.8, evidence="2 transfers", in_deg=0, out_deg=1,
                 in_tx=0, out_tx=2, in_kzt=0, out_kzt="10000.02", pagerank=0.1,
                 pass_through=1.5, truncated_by_depth=False,
             ), NodeAssessmentUpdate(priority_score=0.9)),
            (RankedNodeRepository, RankedNodeService,
             RankedNodeCreate(gid="a", rank=1, role=NodeRole.TRANSIT, priority_score=0.8, why="2 transfers"),
             RankedNodeUpdate(why="updated explanation")),
        ]

    def test_repository_crud_for_every_entity(self):
        for repository_type, _, create, update in self.cases():
            with self.subTest(entity=repository_type.__name__):
                repository = repository_type(self.session)
                before = len(repository.get_all())
                self.assertIsNone(repository.get_by_id(99999))
                self.assertIsNone(repository.update(99999, {}))
                self.assertFalse(repository.delete(99999))
                entity = repository.create(create.model_dump())
                entity_id = entity.id
                self.assertIsNotNone(entity.created_at)
                self.assertIsNotNone(entity.updated_at)
                self.assertIs(repository.get_by_id(entity_id), entity)
                self.assertEqual(repository.get_all(skip=before, limit=1), [entity])
                changes = update.model_dump(exclude_unset=True)
                self.assertIs(repository.update(entity_id, changes), entity)
                for field, value in changes.items():
                    self.assertEqual(getattr(entity, field), value)
                self.assertTrue(repository.delete(entity_id))
                self.assertIsNone(repository.get_by_id(entity_id))
                self.assertEqual(len(repository.get_all()), before)

    def test_service_crud_for_every_entity(self):
        for repository_type, service_type, create, update in self.cases():
            with self.subTest(entity=service_type.__name__):
                service = service_type(repository_type(self.session))
                before = len(service.get_all())
                entity = service.create(create)
                entity_id = entity.id
                self.assertIs(service.get_by_id(entity_id), entity)
                self.assertEqual(service.get_all(skip=before, limit=1), [entity])
                old_values = create.model_dump()
                service.update(entity_id, update)
                old_values.update(update.model_dump(exclude_unset=True))
                for field, value in old_values.items():
                    self.assertEqual(getattr(entity, field), value)
                service.delete(entity_id)
                with self.assertRaises(NotFoundError):
                    service.get_by_id(entity_id)

    def test_missing_service_records(self):
        for repository_type, service_type, _, update in self.cases():
            service = service_type(repository_type(self.session))
            for operation in (lambda: service.get_by_id(99999),
                              lambda: service.update(99999, update),
                              lambda: service.delete(99999)):
                with self.subTest(entity=service_type.__name__), self.assertRaises(NotFoundError):
                    operation()

    def test_pagination_is_stable_and_validated(self):
        repository = NodeRepository(self.session)
        service = NodeService(repository)
        self.assertEqual([node.gid for node in service.get_all(skip=1, limit=1)], ["b"])
        self.assertEqual([node.gid for node in service.get_all()], ["a", "b", "c"])
        self.assertEqual(service.get_all(limit=0), [])
        self.assertEqual(service.get_all(skip=999), [])
        for kwargs in ({"skip": -1}, {"limit": -1}, {"skip": 0.5}, {"limit": True}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    repository.get_all(**kwargs)
                with self.assertRaises(ValidationError):
                    service.get_all(**kwargs)

    def test_uniqueness_on_create_and_unchanged_key_on_update(self):
        for repository_type, service_type, create, update in self.cases():
            with self.subTest(entity=service_type.__name__):
                service = service_type(repository_type(self.session))
                entity = service.create(create)
                with self.assertRaises(ConflictError):
                    service.create(create)
                self.assertTrue(self.session.is_active)
                service.update(entity.id, type(update)())
                service.update(entity.id, update)

    def test_uniqueness_on_update_including_composite_edge_key(self):
        overrides = [
            {"gid": "other"}, {"src": "c", "dst": "a"}, {"row_id": 11},
            {"cluster_id": 100}, {"gid": "b"}, {"gid": "b", "rank": 2},
        ]
        for (repository_type, service_type, create, update), changed_key in zip(self.cases(), overrides):
            with self.subTest(entity=service_type.__name__):
                service = service_type(repository_type(self.session))
                service.create(create)
                other_values = create.model_dump() | changed_key
                other = service.create(type(create)(**other_values))
                conflicting = {key: getattr(create, key) for key in changed_key}
                with self.assertRaises(ConflictError):
                    service.update(other.id, type(update)(**conflicting))
                for key, value in changed_key.items():
                    self.assertEqual(getattr(other, key), value)
                if isinstance(service, RankedNodeService):
                    with self.assertRaises(ConflictError):
                        service.update(other.id, RankedNodeUpdate(rank=1))
                    with self.assertRaises(ConflictError):
                        service.update(other.id, RankedNodeUpdate(gid="a"))

    def test_missing_references_on_create_and_partial_update(self):
        reference_changes = {
            EdgeService: [{"src": "missing"}, {"dst": "missing"}],
            TransactionService: [{"src": "b", "dst": "a"}],
            NodeAssessmentService: [{"gid": "missing"}, {"cluster_id": 404}],
            RankedNodeService: [{"gid": "missing"}],
        }
        for repository_type, service_type, create, update in self.cases():
            if service_type not in reference_changes:
                continue
            service = service_type(repository_type(self.session))
            for change in reference_changes[service_type]:
                with self.subTest(entity=service_type.__name__, change=change):
                    with self.assertRaises(NotFoundError):
                        service.create(type(create)(**(create.model_dump() | change)))
            entity = service.create(create)
            for change in reference_changes[service_type]:
                with self.subTest(entity=service_type.__name__, change=change):
                    with self.assertRaises(NotFoundError):
                        service.update(entity.id, type(update)(**change))
                    for key in change:
                        self.assertEqual(getattr(entity, key), getattr(create, key))

    def test_partial_updates_reject_null_except_nullable_pass_through(self):
        for repository_type, service_type, create, update in self.cases():
            service = service_type(repository_type(self.session))
            entity = service.create(create)
            field = next(iter(update.model_dump(exclude_unset=True)))
            original = getattr(entity, field)
            with self.subTest(entity=service_type.__name__):
                with self.assertRaises(ValidationError):
                    service.update(entity.id, type(update)(**{field: None}))
                self.assertEqual(getattr(entity, field), original)
        assessment_service = NodeAssessmentService(NodeAssessmentRepository(self.session))
        assessment = assessment_service.get_all()[0]
        assessment_service.update(assessment.id, NodeAssessmentUpdate(evidence="changed"))
        self.assertEqual(assessment.pass_through, 1.5)
        assessment_service.update(assessment.id, NodeAssessmentUpdate(pass_through=None))
        self.assertIsNone(assessment.pass_through)

    def test_cluster_rules_validate_merged_values_before_mutating(self):
        repository = ClusterRepository(self.session)
        service = ClusterService(repository)
        with self.assertRaises(ValidationError):
            service.create(ClusterCreate(cluster_id=99, n_nodes=1, n_seed=2,
                                         sum_kzt_internal=0, hypothesis="invalid"))
        cluster = repository.get_by_fields(cluster_id=42)
        with self.assertRaises(ValidationError):
            service.update(cluster.id, ClusterUpdate(n_nodes=0))
        with self.assertRaises(ValidationError):
            service.update(cluster.id, ClusterUpdate(n_seed=4))
        self.assertEqual((cluster.n_nodes, cluster.n_seed), (3, 1))
        service.update(cluster.id, ClusterUpdate(n_nodes=0, n_seed=0, top_gids=[]))
        self.assertEqual((cluster.n_nodes, cluster.n_seed, cluster.top_gids), (0, 0, []))

    def test_identical_transfers_with_different_row_ids_are_preserved(self):
        service = TransactionService(TransactionRepository(self.session))
        values = dict(src="a", dst="b", date=date(2026, 7, 1), sum_kzt="5000.01")
        first = service.create(TransactionCreate(row_id=0, **values))
        second = service.create(TransactionCreate(row_id=1, **values))
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(first.sum_kzt, Decimal("5000.01"))
        self.assertEqual(len(service.get_all()), 2)

    def test_referenced_records_cannot_be_deleted_or_rekeyed(self):
        for repository_type, service_type, create, _ in self.cases():
            if service_type in (TransactionService, NodeAssessmentService, RankedNodeService):
                service_type(repository_type(self.session)).create(create)
        self.session.commit()
        cases = [
            (NodeService(NodeRepository(self.session)), {"gid": "a"}, NodeUpdate(gid="renamed")),
            (EdgeService(EdgeRepository(self.session)), {"src": "a", "dst": "b"}, EdgeUpdate(dst="c")),
            (ClusterService(ClusterRepository(self.session)), {"cluster_id": 42}, ClusterUpdate(cluster_id=77)),
        ]
        for service, lookup, update in cases:
            entity_id = service.repository.get_by_fields(**lookup).id
            for operation in (lambda: service.delete(entity_id), lambda: service.update(entity_id, update)):
                with self.subTest(entity=type(service).__name__):
                    with self.assertRaises(ConflictError) as caught:
                        operation()
                    self.assertIsInstance(caught.exception.__cause__, IntegrityError)
                    self.session.rollback()
                    self.assertIsNotNone(service.repository.get_by_id(entity_id))

    def test_database_uniqueness_conflict_is_translated_after_precheck_race(self):
        service = NodeService(NodeRepository(self.session))
        # Simulate a competing transaction winning between precheck and INSERT.
        with patch.object(service.repository, "get_by_fields", return_value=None):
            with self.assertRaises(ConflictError) as caught:
                service.create(NodeCreate(gid="a", depth=0))
        self.assertIsInstance(caught.exception.__cause__, IntegrityError)
        self.session.rollback()
        self.assertEqual(len(service.get_all()), 3)

    def test_caller_can_commit_or_roll_back_a_multi_entity_transaction(self):
        nodes = NodeService(NodeRepository(self.session))
        edges = EdgeService(EdgeRepository(self.session))
        with self.assertRaises(ConflictError):
            with self.session.begin():
                nodes.create(NodeCreate(gid="rolled-back", depth=1))
                edges.create(EdgeCreate(src="a", dst="rolled-back", sum_kzt=1, n_tx=1, depth=1))
                nodes.create(NodeCreate(gid="a", depth=0))
        self.assertIsNone(nodes.repository.get_by_fields(gid="rolled-back"))
        self.assertIsNone(edges.repository.get_by_fields(dst="rolled-back"))
        self.session.rollback()
        with self.session.begin():
            entity_id = nodes.create(NodeCreate(gid="committed", depth=1)).id
        with Session(self.engine) as reader:
            self.assertEqual(NodeRepository(reader).get_by_id(entity_id).gid, "committed")
        nodes.update(entity_id, NodeUpdate(depth=2))
        self.session.rollback()
        self.assertEqual(nodes.get_by_id(entity_id).depth, 1)
        nodes.delete(entity_id)
        self.session.rollback()
        self.assertIsNotNone(nodes.get_by_id(entity_id))

    def test_repository_protects_server_managed_and_unmapped_fields(self):
        repository = NodeRepository(self.session)
        for field in ("id", "created_at", "updated_at", "assessment", "unknown"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    repository.create({"gid": "new", "depth": 1, field: None})
                with self.assertRaises(ValueError):
                    repository.update(1, {field: None})


if __name__ == "__main__":
    unittest.main()
