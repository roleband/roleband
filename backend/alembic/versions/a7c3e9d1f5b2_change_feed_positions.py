"""The changes feed's records carry the transaction that wrote each row.

`job_lifecycle_events` and `scrape_source_runs` gain `change_xact` (the
inserting transaction's `xid8`) and `change_cluster` (the cluster that
assigned it). Both are added without a default, so no existing row is
rewritten: an existing row reads NULL, which the feed treats as history from
before its cursors. The defaults are set afterwards and apply only to rows
inserted from then on. The partial indexes start empty for the same reason.
The downgrade drops the two columns and their indexes; every row stays.
"""

import sqlalchemy as sa

from alembic import op

revision = "a7c3e9d1f5b2"
down_revision = "324592aae2a6"
branch_labels = None
depends_on = None

_TABLES = ("job_lifecycle_events", "scrape_source_runs")


def upgrade() -> None:
    for table in _TABLES:
        # SQLAlchemy has no `xid8` type, and a migration names its types itself.
        op.execute(f"ALTER TABLE {table} ADD COLUMN change_xact xid8")
        op.add_column(table, sa.Column("change_cluster", sa.BigInteger(), nullable=True))
        op.alter_column(table, "change_xact", server_default=sa.text("pg_current_xact_id()"))
        op.alter_column(
            table, "change_cluster", server_default=sa.text("(pg_control_system()).system_identifier")
        )
        op.create_index(
            f"ix_{table}_change_position",
            table,
            ["change_xact", "id"],
            postgresql_where=sa.text("change_xact IS NOT NULL"),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_change_position", table_name=table)
        op.drop_column(table, "change_cluster")
        op.drop_column(table, "change_xact")
