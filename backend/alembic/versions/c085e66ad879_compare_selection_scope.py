"""A comparison belongs to the list screen it was picked on.

`compare_selection.scope` names that screen, `radar` or `pipeline`, and a role
is unique within a scope rather than across the table, so the same role can
be in both comparisons. Every stored row was picked before screens kept their
own, and takes `radar`, the screen the selection served. Additive: no row is
removed.
"""

import sqlalchemy as sa

from alembic import op

revision = "c085e66ad879"
down_revision = "a7d2f4c9e1b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "compare_selection",
        sa.Column("scope", sa.String(length=16), server_default="radar", nullable=False),
    )
    op.create_check_constraint(
        "ck_compare_selection_scope", "compare_selection", "scope IN ('radar','pipeline')"
    )
    op.drop_constraint("uq_compare_selection_job", "compare_selection", type_="unique")
    op.create_unique_constraint(
        "uq_compare_selection_scope_job", "compare_selection", ["scope", "job_id"]
    )


def downgrade() -> None:
    # Refuses while the Pipeline holds a comparison: the earlier schema keeps
    # one selection and has nowhere to put a second.
    rows = op.get_bind().execute(
        sa.text("SELECT count(*) FROM compare_selection WHERE scope <> 'radar'")
    ).scalar()
    if rows:
        raise RuntimeError(f"{rows} roles in the Pipeline's comparison would be lost")
    op.drop_constraint("uq_compare_selection_scope_job", "compare_selection", type_="unique")
    op.create_unique_constraint("uq_compare_selection_job", "compare_selection", ["job_id"])
    op.drop_constraint("ck_compare_selection_scope", "compare_selection", type_="check")
    op.drop_column("compare_selection", "scope")
