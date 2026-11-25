"""Top picks: the person's background, their brief, and an assistant's verdicts.

Five tables, all new: `candidate_document` and `candidate_background` (who the
person is), `pick_brief` (what they want, one row per version), `pick_run`
(one run of the judge) and `pick_verdict` (its verdict on one posting).
`job_feedback` gains `reason_text`, the person's own words for a dismissal.

Nothing existing is rewritten. The downgrade drops the five tables and the
column, and refuses while any of them holds a row: a background, a brief and
verdicts are the person's, and nothing rebuilds them.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a7c3e9d1b4f6"
down_revision = "4597fa526e25"
branch_labels = None
depends_on = None

_NOW = sa.text("now()")
_TABLES = ("pick_verdict", "pick_run", "pick_brief", "candidate_background", "candidate_document")


def upgrade() -> None:
    op.add_column("job_feedback", sa.Column("reason_text", sa.Text(), nullable=True))
    op.create_table(
        "candidate_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("stored_name", sa.String(length=96), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_candidate_document_sha256"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_candidate_document_size"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_name"),
    )
    op.create_table(
        "candidate_background",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reading", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("host", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("source IN ('document', 'spoken', 'minimal')", name="ck_candidate_background_source"),
        sa.ForeignKeyConstraint(["document_id"], ["candidate_document.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version"),
    )
    op.create_table(
        "pick_brief",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("made_by", sa.String(length=16), nullable=False),
        sa.Column("host", sa.String(length=32), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.CheckConstraint("status IN ('draft', 'active', 'superseded')", name="ck_pick_brief_status"),
        sa.CheckConstraint("made_by IN ('person', 'routine')", name="ck_pick_brief_made_by"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version"),
    )
    op.create_index(
        "uq_pick_brief_active", "pick_brief", ["status"], unique=True, postgresql_where=sa.text("status = 'active'")
    )
    op.create_index(
        "uq_pick_brief_draft", "pick_brief", ["status"], unique=True, postgresql_where=sa.text("status = 'draft'")
    )
    op.create_table(
        "pick_run",
        sa.Column("id", sa.String(length=24), nullable=False),
        sa.Column("host", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("trial", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("brief_version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column(
            "queue", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            "counts", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("tokens", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('finished', 'stopped', 'abandoned')", name="ck_pick_run_outcome"
        ),
        sa.CheckConstraint("(outcome IS NULL) = (finished_at IS NULL)", name="ck_pick_run_closed"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pick_run_started", "pick_run", ["started_at"])
    op.create_table(
        "pick_verdict",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=32), nullable=False),
        sa.Column("brief_version", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column(
            "reasons", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("against_baseline", sa.String(length=16), nullable=True),
        sa.Column("pass_code", sa.String(length=24), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("run_id", sa.String(length=24), nullable=False),
        sa.Column("trial", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("verdict IN ('pick', 'near_miss', 'pass')", name="ck_pick_verdict_verdict"),
        sa.CheckConstraint(
            "against_baseline IS NULL OR against_baseline IN ('better', 'comparable', 'weaker', 'unknown')",
            name="ck_pick_verdict_baseline",
        ),
        sa.CheckConstraint("(verdict = 'pass') = (pass_code IS NOT NULL)", name="ck_pick_verdict_pass_code"),
        sa.CheckConstraint("verdict <> 'pick' OR against_baseline <> 'weaker'", name="ck_pick_verdict_not_weaker"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["pick_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "content_hash", "brief_version", "trial", name="uq_pick_verdict_case"),
    )
    op.create_index("ix_pick_verdict_job_id", "pick_verdict", ["job_id"])
    op.create_index("ix_pick_verdict_run_id", "pick_verdict", ["run_id"])


def downgrade() -> None:
    bind = op.get_bind()
    held = {table: bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one() for table in _TABLES}
    words = bind.execute(sa.text("SELECT count(*) FROM job_feedback WHERE reason_text IS NOT NULL")).scalar_one()
    if kept := {table: count for table, count in held.items() if count}:
        raise RuntimeError(f"Downgrade refused: these tables hold rows that would be lost: {kept}.")
    if words:
        raise RuntimeError(f"Downgrade refused: {words} dismissals carry the person's own words.")
    op.drop_index("ix_pick_verdict_run_id", table_name="pick_verdict")
    op.drop_index("ix_pick_verdict_job_id", table_name="pick_verdict")
    op.drop_table("pick_verdict")
    op.drop_index("ix_pick_run_started", table_name="pick_run")
    op.drop_table("pick_run")
    op.drop_index("uq_pick_brief_draft", table_name="pick_brief")
    op.drop_index("uq_pick_brief_active", table_name="pick_brief")
    op.drop_table("pick_brief")
    op.drop_table("candidate_background")
    op.drop_table("candidate_document")
    op.drop_column("job_feedback", "reason_text")
