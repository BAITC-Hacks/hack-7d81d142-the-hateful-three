"""Migration/ORM integration checks, with no application routes or CRUD layer.

Default: disposable in-memory SQLite database. Set TEST_DATABASE_URL to test
PostgreSQL in a unique temporary schema, created and removed by this suite.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.schema import CreateSchema, DropSchema

from backend.core.config import settings
from backend.core.database import create_db_engine, get_database_url
from backend.models import Base, Cluster, Edge, Node, NodeAssessment, NodeRole, RankedNode, Transaction, User
from backend.repositories import RankedNodeRepository


ROOT = Path(__file__).resolve().parents[2]
SOURCE = "100000003684369100"
DESTINATION = "100000008603629100"


class MigrationTests(unittest.TestCase):
    def setUp(self):
        configure_mappers()
        self.engine = create_db_engine(os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:"))
        self.connection = self.engine.connect()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.connection.close)
        if self.engine.dialect.name == "postgresql":
            schema = "test_moneygraph_" + uuid4().hex
            self.connection.execute(CreateSchema(schema))
            self.connection.execute(text(f'SET search_path TO "{schema}"'))
            self.connection.commit()
            self.engine.dialect.default_schema_name = schema

            def remove_test_schema():
                self.connection.rollback()
                self.connection.execute(text("SET search_path TO public"))
                self.connection.execute(DropSchema(schema, cascade=True))
                self.connection.commit()

            self.addCleanup(remove_test_schema)
        self.config = Config(str(ROOT / "alembic.ini"))
        self.config.attributes["connection"] = self.connection
        command.upgrade(self.config, "head")
        self.connection.commit()

    def seed_graph(self, session):
        source = Node(gid=SOURCE, depth=0, is_seed=True)
        destination = Node(gid=DESTINATION, depth=1)
        edge = Edge(source=source, destination=destination, sum_kzt=Decimal("10000.02"), n_tx=2, depth=1)
        cluster = Cluster(
            cluster_id=0, n_nodes=2, n_seed=1,
            sum_kzt_internal=Decimal("10000.02"), top_gids=[SOURCE, DESTINATION], hypothesis="2 nodes",
        )
        session.add_all([source, destination, edge, cluster])
        session.flush()
        return source, destination, edge, cluster

    def assessment_values(self):
        return dict(
            gid=SOURCE, role=NodeRole.TRANSIT, role_score=0.7, cluster_id=0,
            priority_score=0.8, evidence="2 outgoing transfers", in_deg=0, out_deg=1,
            in_tx=0, out_tx=2, in_kzt=Decimal("0"), out_kzt=Decimal("10000.02"),
            pagerank=0.1, pass_through=None, truncated_by_depth=False,
        )

    def test_upgrade_matches_metadata_and_downgrade_is_reversible(self):
        command.upgrade(self.config, "head")  # Re-running head must be harmless.
        command.check(self.config)
        inspector = inspect(self.connection)
        self.assertEqual(set(inspector.get_table_names()), set(Base.metadata.tables) | {"alembic_version"})
        for table in Base.metadata.tables:
            columns = {column["name"]: column for column in inspector.get_columns(table)}
            for name in ("id", "created_at", "updated_at"):
                self.assertIn(name, columns)
                self.assertFalse(columns[name]["nullable"])
        with Session(self.connection) as session:
            self.seed_graph(session)
            session.commit()
        self.connection.commit()
        command.downgrade(self.config, "base")
        self.assertEqual(inspect(self.connection).get_table_names(), ["alembic_version"])
        command.upgrade(self.config, "head")
        command.check(self.config)

    def test_relationships_duplicate_transfers_and_nullable_ratio(self):
        with Session(self.connection) as session:
            source, destination, edge, cluster = self.seed_graph(session)
            transfers = [
                Transaction(row_id=row, sender=source, recipient=destination,
                            date=date(2026, 7, 1), sum_kzt=Decimal("5000.01"))
                for row in (0, 1)
            ]
            assessment = NodeAssessment(**self.assessment_values())
            ranked = RankedNode(node=source, rank=1, role=NodeRole.TRANSIT, priority_score=0.8, why="2 transfers")
            session.add_all([*transfers, assessment, ranked])
            session.commit()
            self.assertEqual(source.assessment, assessment)
            self.assertEqual(source.ranked_node, ranked)
            self.assertEqual(assessment.cluster, cluster)
            self.assertEqual(cluster.assessments, [assessment])
            self.assertEqual(source.outgoing_edges, [edge])
            self.assertEqual(destination.incoming_edges, [edge])
            self.assertEqual(len(source.sent_transactions), 2)
            self.assertEqual(len(destination.received_transactions), 2)
            self.assertEqual(len(edge.transactions), 2)
            self.assertEqual(transfers[0].edge, edge)
            self.assertNotEqual(transfers[0].id, transfers[1].id)
            self.assertEqual(transfers[0].sum_kzt, Decimal("5000.01"))
            self.assertIsNone(assessment.pass_through)
            self.assertEqual(cluster.top_gids, [SOURCE, DESTINATION])
            for entity in (source, destination, edge, cluster, assessment, ranked, *transfers):
                self.assertIsNotNone(entity.id)
                self.assertIsNotNone(entity.created_at)
                self.assertIsNotNone(entity.updated_at)
            original_created_at = source.created_at
            session.execute(Node.__table__.update().where(Node.id == source.id).values(
                updated_at=datetime(2000, 1, 1, tzinfo=timezone.utc)
            ))
            session.commit()
            source.depth = 1
            session.commit()
            self.assertEqual(source.created_at, original_created_at)
            self.assertGreater(source.updated_at.year, 2000)
            cluster.top_gids.append("100000000000000001")
            session.commit()
            self.assertEqual(len(cluster.top_gids), 3)

    def test_rank_swaps_use_migrated_constraints_and_preserve_ids(self):
        with Session(self.connection) as session:
            self.seed_graph(session)
            source = NodeAssessment(**self.assessment_values())
            destination = NodeAssessment(**(self.assessment_values() | {
                "gid": DESTINATION, "priority_score": 0.2,
            }))
            session.add_all([source, destination])
            session.flush()
            repository = RankedNodeRepository(session)
            repository.lock_ranking()
            first = repository.synchronize(include_missing=True)
            ids = {row.gid: row.id for row in first}
            self.assertEqual([row.gid for row in first], [SOURCE, DESTINATION])
            destination.priority_score = 0.9
            session.flush()
            swapped = repository.synchronize()
            self.assertEqual([(row.gid, row.rank) for row in swapped], [(DESTINATION, 1), (SOURCE, 2)])
            self.assertEqual({row.gid: row.id for row in swapped}, ids)
            session.commit()

    def test_user_email_is_unique_and_deleted_ids_are_not_reused(self):
        with Session(self.connection) as session:
            user = User(email="account@example.com", hashed_password="stored-hash")
            session.add(user)
            session.commit()
            original_id = user.id
            self.assertIsNotNone(user.created_at)
            self.assertIsNotNone(user.updated_at)
            with session.begin_nested():
                with self.assertRaises(IntegrityError):
                    session.add(User(email=user.email, hashed_password="another-hash"))
                    session.flush()
            session.delete(user)
            session.commit()
            replacement = User(email="replacement@example.com", hashed_password="stored-hash")
            session.add(replacement)
            session.commit()
            # Reusing a deleted identity would let its old JWT authenticate a new account.
            self.assertGreater(replacement.id, original_id)

    def test_users_migration_downgrade_preserves_existing_graph_data(self):
        with Session(self.connection) as session:
            self.seed_graph(session)
            session.add(User(email="account@example.com", hashed_password="stored-hash"))
            session.commit()
        self.connection.commit()
        command.downgrade(self.config, "28fe255db73e")
        self.assertNotIn("users", inspect(self.connection).get_table_names())
        self.assertEqual(self.connection.execute(text("SELECT count(*) FROM nodes")).scalar_one(), 2)
        self.connection.commit()
        command.upgrade(self.config, "head")
        command.check(self.config)
        self.assertEqual(self.connection.execute(text("SELECT count(*) FROM users")).scalar_one(), 0)

    def test_integrity_constraints(self):
        with Session(self.connection) as session:
            self.seed_graph(session)
            session.add(NodeAssessment(**self.assessment_values()))
            session.add(RankedNode(gid=SOURCE, rank=1, role=NodeRole.TRANSIT, priority_score=0.8, why="2 transfers"))
            session.commit()

        invalid_statements = {
            "duplicate gid": Node.__table__.insert().values(gid=SOURCE, depth=0),
            "invalid depth": Node.__table__.insert().values(gid="bad-depth", depth=5),
            "duplicate edge": Edge.__table__.insert().values(src=SOURCE, dst=DESTINATION, sum_kzt=1, n_tx=1, depth=1),
            "unknown node": Edge.__table__.insert().values(src=SOURCE, dst="missing", sum_kzt=1, n_tx=1, depth=1),
            "wrong edge direction": Transaction.__table__.insert().values(
                row_id=2, src=DESTINATION, dst=SOURCE, date=date(2026, 7, 1), sum_kzt=5000),
            "duplicate assessment": NodeAssessment.__table__.insert().values(**self.assessment_values()),
            "unknown cluster": NodeAssessment.__table__.update().values(cluster_id=999),
            "invalid score": NodeAssessment.__table__.update().values(priority_score=1.1),
            "long evidence": NodeAssessment.__table__.update().values(evidence="x" * 201),
            "invalid role": text("UPDATE node_assessments SET role = 'invalid'"),
            "duplicate rank": RankedNode.__table__.insert().values(
                gid=DESTINATION, rank=1, role=NodeRole.TRANSIT, priority_score=0.5, why="1 edge"),
            "referenced node deletion": Node.__table__.delete().where(Node.gid == SOURCE),
        }
        for label, statement in invalid_statements.items():
            with self.subTest(label=label):
                # PostgreSQL rejects oversized VARCHAR values before CHECK runs.
                expected_error = (
                    DataError
                    if label == "long evidence" and self.engine.dialect.name == "postgresql"
                    else IntegrityError
                )
                with self.connection.begin_nested() as savepoint:
                    with self.assertRaises(expected_error):
                        self.connection.execute(statement)
                    savepoint.rollback()


class ConfigurationTests(unittest.TestCase):
    def test_postgresql_offline_sql_and_encoded_password(self):
        output = StringIO()
        url = "postgresql://test:p%25ss%40word@localhost:5432/test"
        with patch.object(settings, "database_url", url):
            self.assertEqual(get_database_url().drivername, "postgresql+psycopg")
            self.assertEqual(get_database_url().password, "p%ss@word")
            command.upgrade(Config(str(ROOT / "alembic.ini"), output_buffer=output), "head", sql=True)
        sql = output.getvalue()
        self.assertEqual(sql.count("CREATE TABLE "), len(Base.metadata.tables) + 1)
        self.assertIn("BOOLEAN DEFAULT false", sql)
        self.assertIn("VARCHAR(32)[]", sql)
        self.assertIn("TIMESTAMP WITH TIME ZONE", sql)
        self.assertNotIn("p%ss@word", sql)


if __name__ == "__main__":
    unittest.main()
