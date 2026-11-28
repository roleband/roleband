"""Track a Top picks run's first handoff of each posting."""

import sqlalchemy as sa

from alembic import op

revision = "f6d8a3c2b7e1"
down_revision = "a7c3e9d1b4f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pick_run", sa.Column("tracks_delivery", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table(
        "pick_delivery",
        sa.Column("run_id", sa.String(24), sa.ForeignKey("pick_run.id"), primary_key=True),
        sa.Column("job_id", sa.Integer(), primary_key=True),
        sa.Column("local_day", sa.Date(), nullable=False),
    )
    op.create_index("ix_pick_delivery_local_day", "pick_delivery", ["local_day"])


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE pick_run, pick_delivery IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM pick_delivery)")):
        raise RuntimeError("Top picks deliveries would be lost.")
    op.drop_table("pick_delivery")
    op.drop_column("pick_run", "tracks_delivery")
