"""participations, ctf_discord_resources

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-05

"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

participation_source = sa.Enum("vote", "manual", name="participation_source")


def upgrade() -> None:
    op.create_table(
        "participations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ctf_id", sa.Integer(), nullable=False),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column("source", participation_source, nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_participations"),
        sa.ForeignKeyConstraint(["ctf_id"], ["ctfs.id"], name="fk_participations_ctf_id_ctfs"),
        sa.UniqueConstraint(
            "ctf_id", "discord_user_id", name="uq_participations_ctf_id_discord_user_id"
        ),
    )

    op.create_table(
        "ctf_discord_resources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ctf_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=True),
        sa.Column("forum_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("thread_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("cleanup_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleaned_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_ctf_discord_resources"),
        sa.ForeignKeyConstraint(
            ["ctf_id"], ["ctfs.id"], name="fk_ctf_discord_resources_ctf_id_ctfs"
        ),
        sa.UniqueConstraint("ctf_id", name="uq_ctf_discord_resources_ctf_id"),
    )


def downgrade() -> None:
    op.drop_table("ctf_discord_resources")
    op.drop_table("participations")
    participation_source.drop(op.get_bind(), checkfirst=True)
