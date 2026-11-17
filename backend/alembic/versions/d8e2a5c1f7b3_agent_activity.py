"""Every agent operation is listed for the person: the `agent_activity` table.

A new, empty table and its index. Additive: nothing existing changes, and code
that does not know the table reads and writes as before. The downgrade drops
the table, and with it the activity listed since.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "d8e2a5c1f7b3"
down_revision = "c3f8a1d6e9b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_activity",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=True),
        sa.Column("principal_id", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "categories",
            postgresql.ARRAY(sa.String(length=32)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("action_group", sa.String(length=64), nullable=True),
        sa.Column("refusal", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "subject",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.CheckConstraint("kind IN ('read', 'change', 'refused')", name="ck_agent_activity_kind"),
        sa.CheckConstraint("(kind = 'refused') = (refusal IS NOT NULL)", name="ck_agent_activity_refusal"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_activity_occurred", "agent_activity", ["occurred_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_agent_activity_occurred", table_name="agent_activity")
    op.drop_table("agent_activity")
