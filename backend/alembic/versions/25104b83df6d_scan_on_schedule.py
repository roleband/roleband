"""A company on a user-directed source can be scanned on the regular schedule.

`tracked_company.scan_on_schedule` is the person's answer to "keep scanning this
company", given with their agreement to follow it. Every stored row takes
false, which is how such a company was treated: read only when the person asks.
Additive: no row is rewritten.
"""

import sqlalchemy as sa

from alembic import op

revision = "25104b83df6d"
down_revision = "c085e66ad879"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tracked_company",
        sa.Column("scan_on_schedule", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    # Refuses while a person chose regular scans for a company: the earlier
    # schema has nowhere to keep that choice.
    rows = op.get_bind().execute(
        sa.text("SELECT count(*) FROM tracked_company WHERE scan_on_schedule")
    ).scalar()
    if rows:
        raise RuntimeError(f"{rows} companies are set to keep scanning; that choice would be lost")
    op.drop_column("tracked_company", "scan_on_schedule")
