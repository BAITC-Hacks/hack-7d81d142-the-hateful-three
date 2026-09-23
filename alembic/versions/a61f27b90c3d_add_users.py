"""Add registered users.

Revision ID: a61f27b90c3d
Revises: 28fe255db73e
"""

from alembic import op
import sqlalchemy as sa


revision = "a61f27b90c3d"
down_revision = "28fe255db73e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sqlite_autoincrement=True,
    )


def downgrade() -> None:
    op.drop_table("users")
