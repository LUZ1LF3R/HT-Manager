"""ctf and audit_log tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-05

"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ctf_status = sa.Enum(
    "draft",
    "polling",
    "tied",
    "selected",
    "active",
    "finished",
    "archived",
    "cancelled",
    name="ctf_status",
)


def upgrade() -> None:
    op.create_table(
        "ctfs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("ctftime_event_id", sa.Integer(), nullable=True),
        sa.Column("ctftime_url", sa.String(length=500), nullable=True),
        sa.Column("official_url", sa.String(length=500), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column(
            "status", ctf_status, nullable=False, server_default="draft"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ctfs"),
        sa.UniqueConstraint("ctftime_event_id", name="uq_ctfs_ctftime_event_id"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_table", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("ctfs")
    ctf_status.drop(op.get_bind(), checkfirst=True)
