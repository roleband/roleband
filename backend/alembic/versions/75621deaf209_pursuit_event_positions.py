"""Position pursuit events for the agent's due feed."""

import sqlalchemy as sa

from alembic import op

revision = "75621deaf209"
down_revision = "761c19dadc87"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add defaults separately so the existing events keep their history without a table rewrite.
    op.execute("ALTER TABLE pursuit_events ADD COLUMN change_xact xid8")
    op.add_column("pursuit_events", sa.Column("change_cluster", sa.BigInteger(), nullable=True))
    op.alter_column("pursuit_events", "change_xact", server_default=sa.text("pg_current_xact_id()"))
    op.alter_column(
        "pursuit_events", "change_cluster", server_default=sa.text("(pg_control_system()).system_identifier")
    )


def downgrade() -> None:
    op.drop_column("pursuit_events", "change_cluster")
    op.drop_column("pursuit_events", "change_xact")
