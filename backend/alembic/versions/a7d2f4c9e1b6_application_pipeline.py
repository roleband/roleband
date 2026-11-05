"""A pursuit has three more endings, comments of its own and interview rounds.

`pursuits.stage` gains `accepted`, `declined` and `role_closed`, so an ending
says whether the user chose it or it happened to them. `pursuit_comments`
holds what the user writes on one role; its rows are edited and deleted by
their author, which `pursuit_events` (append-only) cannot hold.
`pursuit_interviews` holds one row per round. `pursuit_events` gains `source`,
where a synced calendar or mailbox will write its own value; every stored row
came from the app. Additive: no stored row changes meaning.
"""

import sqlalchemy as sa

from alembic import op

revision = "a7d2f4c9e1b6"
down_revision = "b2c3e11e3185"
branch_labels = None
depends_on = None

_STAGES_BEFORE = (
    "stage IN ('saved','researching','networking','applied','interviewing',"
    "'offer','rejected','withdrawn')"
)
_STAGES_AFTER = (
    "stage IN ('saved','researching','networking','applied','interviewing',"
    "'offer','accepted','declined','withdrawn','rejected','role_closed')"
)


def upgrade() -> None:
    op.drop_constraint("ck_pursuit_stage", "pursuits", type_="check")
    op.create_check_constraint("ck_pursuit_stage", "pursuits", _STAGES_AFTER)

    op.add_column(
        "pursuit_events",
        sa.Column("source", sa.String(length=16), server_default="app", nullable=False),
    )

    op.create_table(
        "pursuit_comments",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("pursuit_id", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), server_default="app", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("actor IN ('user','agent')", name="ck_pursuit_comment_actor"),
        sa.ForeignKeyConstraint(["pursuit_id"], ["pursuits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pursuit_comments_pursuit_id", "pursuit_comments", ["pursuit_id"])
    op.create_index("ix_pursuit_comments_created_at", "pursuit_comments", ["created_at"])

    op.create_table(
        "pursuit_interviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pursuit_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("all_day", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=True),
        sa.Column("link", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "format IS NULL OR format IN ('video','phone','onsite')",
            name="ck_pursuit_interview_format",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('passed','not_passed','cancelled')",
            name="ck_pursuit_interview_outcome",
        ),
        sa.ForeignKeyConstraint(["pursuit_id"], ["pursuits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pursuit_interviews_pursuit_id", "pursuit_interviews", ["pursuit_id"])
    op.create_index("ix_pursuit_interviews_scheduled_at", "pursuit_interviews", ["scheduled_at"])


def downgrade() -> None:
    # Refuses while any row would be lost: a pursuit in one of the new endings
    # (no stage is rewritten to fit the narrower set), or a comment or an
    # interview the user wrote (the earlier schema has nowhere to keep them).
    bind = op.get_bind()
    held = {
        "pursuits in a new ending": "SELECT count(*) FROM pursuits"
        " WHERE stage IN ('accepted','declined','role_closed')",
        "comments": "SELECT count(*) FROM pursuit_comments",
        "interviews": "SELECT count(*) FROM pursuit_interviews",
    }
    for what, sql in held.items():
        rows = bind.execute(sa.text(sql)).scalar()
        if rows:
            raise RuntimeError(f"{rows} {what} would be lost; the earlier schema cannot hold them")
    op.drop_index("ix_pursuit_interviews_scheduled_at", table_name="pursuit_interviews")
    op.drop_index("ix_pursuit_interviews_pursuit_id", table_name="pursuit_interviews")
    op.drop_table("pursuit_interviews")
    op.drop_index("ix_pursuit_comments_created_at", table_name="pursuit_comments")
    op.drop_index("ix_pursuit_comments_pursuit_id", table_name="pursuit_comments")
    op.drop_table("pursuit_comments")
    op.drop_column("pursuit_events", "source")
    op.drop_constraint("ck_pursuit_stage", "pursuits", type_="check")
    op.create_check_constraint("ck_pursuit_stage", "pursuits", _STAGES_BEFORE)
