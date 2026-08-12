"""workspace archive move

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-12

"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ctf_discord_resources",
        sa.Column("archive_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ctf_discord_resources",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ctf_discord_resources", "archived_at")
    op.drop_column("ctf_discord_resources", "archive_after")
