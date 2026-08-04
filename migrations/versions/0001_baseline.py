"""baseline

Revision ID: 0001
Revises:
Create Date: 2026-08-04

"""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    # Baseline carries no schema; both directions are intentionally no-ops.
    pass
