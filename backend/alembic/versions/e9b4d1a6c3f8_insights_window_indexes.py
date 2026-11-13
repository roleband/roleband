"""Insights reads only the postings a window can reach.

`jobs.first_seen` and `jobs.closed_at` find the postings first seen or closed
since a window's start. The closing-note index finds the closings whose
`listed_with` names a posting, so a role whose other place went long ago is
still read whole. Additive: no row is rewritten.
"""

import sqlalchemy as sa

from alembic import op

revision = "e9b4d1a6c3f8"
down_revision = "25104b83df6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_jobs_first_seen", "jobs", ["first_seen"])
    op.create_index("ix_jobs_closed_at", "jobs", ["closed_at"], postgresql_where=sa.text("closed_at IS NOT NULL"))
    op.create_index(
        "ix_job_lifecycle_events_closing_note",
        "job_lifecycle_events",
        ["detail"],
        postgresql_using="gin",
        postgresql_ops={"detail": "jsonb_path_ops"},
        postgresql_where=sa.text("event_type = 'closed'"),
        postgresql_with={"fastupdate": "off"},
    )


def downgrade() -> None:
    op.drop_index("ix_job_lifecycle_events_closing_note", table_name="job_lifecycle_events")
    op.drop_index("ix_jobs_closed_at", table_name="jobs")
    op.drop_index("ix_jobs_first_seen", table_name="jobs")
