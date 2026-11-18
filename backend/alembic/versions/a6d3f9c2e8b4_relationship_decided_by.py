"""Who decided a duplicate or twin verdict, and the note that came with it.

Two nullable columns on `job_lineage_link` and `job_twin_link`:
`decided_by` (`person` or `agent`) and `decision_note` (an assistant's
one-line reason, or its note on a pair it left for the person). Additive:
every existing row keeps null, which reads as the person's decision, and code
that does not know the columns reads and writes as before. The downgrade drops
both columns, and with them the attribution recorded since.
"""

import sqlalchemy as sa

from alembic import op

revision = "a6d3f9c2e8b4"
down_revision = "d8e2a5c1f7b3"
branch_labels = None
depends_on = None

_TABLES = ("job_lineage_link", "job_twin_link")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("decided_by", sa.String(length=8), nullable=True))
        op.add_column(table, sa.Column("decision_note", sa.Text(), nullable=True))
        op.create_check_constraint(
            f"ck_{table}_decided_by", table, "decided_by IS NULL OR decided_by IN ('person', 'agent')"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f"ck_{table}_decided_by", table, type_="check")
        op.drop_column(table, "decision_note")
        op.drop_column(table, "decided_by")
