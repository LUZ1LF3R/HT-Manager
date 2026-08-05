"""polls, poll_options, poll_votes

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-05

"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

poll_status = sa.Enum(
    "drafting", "open", "closed", "tied", "cancelled", name="poll_status"
)


def upgrade() -> None:
    op.create_table(
        "polls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("discord_message_id", sa.BigInteger(), nullable=True),
        sa.Column("status", poll_status, nullable=False, server_default="drafting"),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("winning_ctf_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_polls"),
        sa.ForeignKeyConstraint(
            ["winning_ctf_id"], ["ctfs.id"], name="fk_polls_winning_ctf_id_ctfs"
        ),
    )

    op.create_table(
        "poll_options",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("poll_id", sa.Integer(), nullable=False),
        sa.Column("ctf_id", sa.Integer(), nullable=False),
        sa.Column("option_index", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_poll_options"),
        sa.ForeignKeyConstraint(["poll_id"], ["polls.id"], name="fk_poll_options_poll_id_polls"),
        sa.ForeignKeyConstraint(["ctf_id"], ["ctfs.id"], name="fk_poll_options_ctf_id_ctfs"),
        sa.UniqueConstraint("poll_id", "ctf_id", name="uq_poll_options_poll_id_ctf_id"),
    )

    op.create_table(
        "poll_votes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("poll_id", sa.Integer(), nullable=False),
        sa.Column("ctf_id", sa.Integer(), nullable=False),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_poll_votes"),
        sa.ForeignKeyConstraint(["poll_id"], ["polls.id"], name="fk_poll_votes_poll_id_polls"),
        sa.ForeignKeyConstraint(["ctf_id"], ["ctfs.id"], name="fk_poll_votes_ctf_id_ctfs"),
        sa.UniqueConstraint(
            "poll_id", "discord_user_id", name="uq_poll_votes_poll_id_discord_user_id"
        ),
    )


def downgrade() -> None:
    op.drop_table("poll_votes")
    op.drop_table("poll_options")
    op.drop_table("polls")
    poll_status.drop(op.get_bind(), checkfirst=True)
