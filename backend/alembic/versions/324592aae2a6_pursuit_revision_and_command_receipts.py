"""Pursuits count their writes, and agent writes keep a receipt.

`pursuits.revision` starts at 1 for every existing row: adding a column with a
constant default rewrites no row. `command_receipts` is new and empty. The
downgrade drops both, and with them every receipt; the pursuits themselves are
untouched either way.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "324592aae2a6"
down_revision = "b6d2e8f4a1c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pursuits",
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_check_constraint("ck_pursuit_revision", "pursuits", "revision >= 1")
    op.create_table(
        "command_receipts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("principal_id", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("contract_version", sa.String(length=16), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("input_hash ~ '^[0-9a-f]{64}$'", name="ck_command_receipt_input_hash"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "principal_id", "operation", "idempotency_key", name="uq_command_receipt_key"
        ),
    )


def downgrade() -> None:
    op.drop_table("command_receipts")
    op.drop_constraint("ck_pursuit_revision", "pursuits", type_="check")
    op.drop_column("pursuits", "revision")
