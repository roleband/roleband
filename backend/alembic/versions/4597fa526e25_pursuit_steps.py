"""A pursuit holds several next steps.

`pursuit_steps` holds one row per step, open until `done_at`. Each pursuit's
current step (`pursuits.next_action`, `next_action_due`) becomes its first
row; the two columns stay, written from the steps as the soonest open one.
An overdue reminder stood for its pursuit and now stands for that step, so
the person's read or dismissed state carries over.

The downgrade refuses completed steps, multiple steps per pursuit, and step
reminders that cannot be mapped to distinct legacy notification keys.
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


def _lock_downgrade(bind: sa.Connection) -> None:
    locks = (
        "LOCK TABLE pursuits IN ACCESS EXCLUSIVE MODE",
        "LOCK TABLE pursuit_steps IN ACCESS EXCLUSIVE MODE",
        "LOCK TABLE notifications IN SHARE ROW EXCLUSIVE MODE",
    )
    # The drop also removes the foreign key trigger on pursuits, so take both
    # exclusive locks up front. Pursuit edits write the parent before the step
    # and its reminders, but scan finalization can write notifications before
    # reading steps and pursuits. Release partial acquisitions before waiting.
    while True:
        try:
            with bind.begin_nested():
                for lock in locks:
                    bind.exec_driver_sql(f"{lock} NOWAIT")
            return
        except sa.exc.OperationalError as exc:
            if getattr(exc.orig, "pgcode", None) != "55P03":  # lock_not_available
                raise
        with bind.begin_nested() as wait:
            bind.exec_driver_sql(lock)
            wait.rollback()


def downgrade() -> None:
    bind = op.get_bind()
    # Alembic reads the revision before this lock boundary. The guards need
    # fresh snapshots so they see commits that landed while acquiring locks.
    if bind.get_isolation_level() not in {"READ COMMITTED", "READ UNCOMMITTED"}:
        raise RuntimeError("Downgrade refused: pursuit_steps requires READ COMMITTED isolation.")
    _lock_downgrade(bind)

    ticked = bind.execute(sa.text("SELECT count(*) FROM pursuit_steps WHERE done_at IS NOT NULL")).scalar_one()
    if ticked:
        raise RuntimeError(f"Downgrade refused: {ticked} ticked next steps would be lost with pursuit_steps.")
    several = bind.execute(sa.text(
        "SELECT count(*) FROM (SELECT 1 FROM pursuit_steps GROUP BY pursuit_id HAVING count(*) > 1) AS many"
    )).scalar_one()
    if several:
        raise RuntimeError(
            f"Downgrade refused: {several} pursuits with several next steps would be lost with pursuit_steps."
        )
    collisions = bind.execute(sa.text(
        """
        SELECT count(*)
        FROM notifications AS n
        JOIN pursuit_steps AS s ON s.id = n.source_id
        JOIN notifications AS legacy
          ON legacy.source_type = 'pursuit'
         AND legacy.source_id = s.pursuit_id
         AND legacy.category = n.category
        WHERE n.source_type = 'step'
        """
    )).scalar_one()
    if collisions:
        raise RuntimeError(
            f"Downgrade refused: {collisions} step reminders collide with existing legacy notification keys."
        )

    op.execute(
        """
        UPDATE notifications AS n
        SET source_type = 'pursuit', source_id = s.pursuit_id
        FROM pursuit_steps AS s
        WHERE n.source_type = 'step' AND s.id = n.source_id
        """
    )
    unmapped = bind.execute(sa.text("SELECT count(*) FROM notifications WHERE source_type = 'step'")).scalar_one()
    if unmapped:
        raise RuntimeError(f"Downgrade refused: {unmapped} orphaned step reminders have no pursuit to remap to.")

    op.execute(
        """
        UPDATE pursuits AS p
        SET next_action = s.text, next_action_due = s.due
        FROM pursuit_steps AS s
        WHERE s.pursuit_id = p.id
          AND (p.next_action IS DISTINCT FROM s.text OR p.next_action_due IS DISTINCT FROM s.due)
        """
    )
    op.drop_index("ix_pursuit_steps_due", table_name="pursuit_steps")
    op.drop_index("ix_pursuit_steps_pursuit_id", table_name="pursuit_steps")
    op.drop_table("pursuit_steps")
