"""The workspace gets a durable identity.

`workspace_identity` holds one row: the id agent receipts, cursors and grants
are keyed by. The upgrade writes it, so every database at this revision has
one before any engine answers. Additive: no existing row is rewritten. The
downgrade drops the table, and with it the id; an upgrade after that makes a
new one, which a caller sees as a different workspace.
"""

import sqlalchemy as sa

from alembic import op

revision = "b6d2e8f4a1c7"
down_revision = "e9b4d1a6c3f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_identity",
        sa.Column("singleton", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("singleton", name="ck_workspace_identity_singleton"),
        sa.CheckConstraint("workspace_id ~ '^ws_[0-9a-f]{32}$'", name="ck_workspace_identity_format"),
        sa.PrimaryKeyConstraint("singleton"),
        sa.UniqueConstraint("workspace_id"),
    )
    # gen_random_uuid() is built into Postgres 13 and later.
    op.execute(
        "INSERT INTO workspace_identity (workspace_id)"
        " VALUES ('ws_' || replace(gen_random_uuid()::text, '-', ''))"
    )


def downgrade() -> None:
    op.drop_table("workspace_identity")
