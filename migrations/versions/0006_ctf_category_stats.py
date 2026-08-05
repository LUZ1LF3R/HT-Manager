"""ctf_category_stats

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-05

"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ctf_category_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ctf_id", sa.Integer(), nullable=False),
        sa.Column("category_name", sa.String(length=100), nullable=False),
        sa.Column("solved", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ctf_category_stats"),
        sa.ForeignKeyConstraint(
            ["ctf_id"], ["ctfs.id"], name="fk_ctf_category_stats_ctf_id_ctfs"
        ),
        sa.UniqueConstraint(
            "ctf_id", "category_name", name="uq_ctf_category_stats_ctf_id_category_name"
        ),
    )


def downgrade() -> None:
    op.drop_table("ctf_category_stats")
