"""A pursuit holds several next steps.

`pursuit_steps` holds one row per step, open until `done_at`. Each pursuit's
current step (`pursuits.next_action`, `next_action_due`) becomes its first
row; the two columns stay, written from the steps as the soonest open one.
An overdue reminder stood for its pursuit and now stands for that step, so
the person's read or dismissed state carries over.

The downgrade drops the table, which holds more than the old columns can: it
refuses while any pursuit has more than one step or any step is ticked done,
so history is never dropped silently. It runs where it would lose nothing.
"""

import sqlalchemy as sa

from alembic import op

revision = "4597fa526e25"
down_revision = "75621deaf209"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pursuit_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pursuit_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("due", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("text <> ''", name="ck_pursuit_step_text"),
        sa.ForeignKeyConstraint(["pursuit_id"], ["pursuits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pursuit_steps_pursuit_id", "pursuit_steps", ["pursuit_id"])
    op.create_index("ix_pursuit_steps_due", "pursuit_steps", ["due"])
    op.execute(
        """
        INSERT INTO pursuit_steps (pursuit_id, text, due, created_at)
        SELECT id, next_action, next_action_due, updated_at
        FROM pursuits
        WHERE next_action IS NOT NULL AND next_action <> ''
        ORDER BY id
        """
    )
    op.execute(
        """
        UPDATE notifications AS n
        SET source_type = 'step', source_id = s.id
        FROM pursuit_steps AS s
        WHERE n.source_type = 'pursuit' AND s.pursuit_id = n.source_id
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    ticked = bind.execute(sa.text("SELECT count(*) FROM pursuit_steps WHERE done_at IS NOT NULL")).scalar_one()
    several = bind.execute(
        sa.text(
            "SELECT count(*) FROM (SELECT 1 FROM pursuit_steps GROUP BY pursuit_id HAVING count(*) > 1) AS many"
        )
    ).scalar_one()
    if ticked:
        raise RuntimeError(f"Downgrade refused: {ticked} ticked next steps would be lost with pursuit_steps.")
    if several:
        raise RuntimeError(
            f"Downgrade refused: {several} pursuits with several next steps would be lost with pursuit_steps."
        )
    op.execute(
        """
        UPDATE notifications AS n
        SET source_type = 'pursuit', source_id = s.pursuit_id
        FROM pursuit_steps AS s
        WHERE n.source_type = 'step' AND s.id = n.source_id
          AND s.id = (
            SELECT first.id FROM pursuit_steps AS first
            WHERE first.pursuit_id = s.pursuit_id AND first.done_at IS NULL
            ORDER BY first.due ASC NULLS LAST, first.id
            LIMIT 1
          )
        """
    )
    op.execute("DELETE FROM notifications WHERE source_type = 'step'")
    op.drop_index("ix_pursuit_steps_due", table_name="pursuit_steps")
    op.drop_index("ix_pursuit_steps_pursuit_id", table_name="pursuit_steps")
    op.drop_table("pursuit_steps")
