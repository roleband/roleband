"""Each plugin run's end is recorded once, in commit order, for the changes feed.

`plugin_run_ends` is a new table: one row per closed plugin run, inserted by
the transaction that closes it, with the changes feed's position columns
(`change_xact`, `change_cluster`) left to their defaults. Additive: nothing
existing changes and no row is written for a run that ended before it, so code
that does not know the table reads and writes as before. The downgrade drops
the table, and with it the ends recorded since; `plugin_run` keeps every run.
"""

import sqlalchemy as sa

from alembic import op

revision = "c3f8a1d6e9b4"
down_revision = "a7c3e9d1f5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plugin_run_ends",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("plugin_id", sa.String(length=32), nullable=False),
        sa.Column("job", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("change_cluster", sa.BigInteger(), nullable=True,
                  server_default=sa.text("(pg_control_system()).system_identifier")),
        sa.ForeignKeyConstraint(["run_id"], ["plugin_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_plugin_run_ends_run"),
    )
    # SQLAlchemy has no `xid8` type, and a migration names its types itself.
    op.execute("ALTER TABLE plugin_run_ends ADD COLUMN change_xact xid8 DEFAULT pg_current_xact_id()")
    op.create_index(
        "ix_plugin_run_ends_change_position",
        "plugin_run_ends",
        ["change_xact", "id"],
        postgresql_where=sa.text("change_xact IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("plugin_run_ends")
