"""Each activity row names the host the call ran under: `agent_activity.host`.

A nullable column and an index for each host's latest call. Additive: rows
already listed keep no host, since nothing recorded which host made them, and
code that does not know the column reads and writes as before.
"""

import sqlalchemy as sa

from alembic import op

revision = "761c19dadc87"
down_revision = "d8e2a5c1f7b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_activity", sa.Column("host", sa.String(length=32), nullable=True))
    op.create_index("ix_agent_activity_host", "agent_activity", ["host", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_activity_host", table_name="agent_activity")
    op.drop_column("agent_activity", "host")
