"""results, sync_state

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-05

"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

result_source = sa.Enum("ctftime", "manual", name="result_source")


def upgrade() -> None:
    op.create_table(
        "results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ctf_id", sa.Integer(), nullable=False),
        sa.Column("source", result_source, nullable=False),
        sa.Column("placement", sa.Integer(), nullable=True),
        sa.Column("total_teams", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("rating_points", sa.Float(), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("announced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_results"),
        sa.ForeignKeyConstraint(["ctf_id"], ["ctfs.id"], name="fk_results_ctf_id_ctfs"),
        sa.UniqueConstraint("ctf_id", name="uq_results_ctf_id"),
    )

    op.create_table(
        "sync_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("integration_key", sa.String(length=100), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sync_state"),
        sa.UniqueConstraint("integration_key", name="uq_sync_state_integration_key"),
    )


def downgrade() -> None:
    op.drop_table("sync_state")
    op.drop_table("results")
    result_source.drop(op.get_bind(), checkfirst=True)
