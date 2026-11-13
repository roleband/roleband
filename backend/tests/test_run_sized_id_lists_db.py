"""A run's id list reaches Postgres as one parameter, however long it is.

The Postgres wire protocol refuses a statement with more than 32767 bind
parameters, and an expanded `IN (...)` spends one per id. A run that touches
more postings than that would fail the fatal fingerprint pass, skip every pass
after it, and fail the same way on every later full run. Each pass that reads a
run's (or the whole corpus's) ids is exercised here with more ids than the
limit, on a real database: the error is raised by the driver, never by a mock.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.content import content_fingerprint, fingerprint_content
from tracker.db.models import Job
from tracker.intelligence_runtime.disclosed_comp import owed_ids, settle_stored_bands
from tracker.lineage.detect import detect_lineage
from tracker.lineage.twins import detect_twins
from tracker.scope.projection import recompute_saved_scope
from tracker.skills.extract import extract_requirements
from tracker.workflows.post_passes import pending_roles, reclassify_domains, reclassify_places

pytestmark = pytest.mark.asyncio

#: More ids than one statement may carry as separate parameters (32767).
RUN_SIZE = 33_000


async def _seed(session: AsyncSession, count: int) -> list[int]:
    """`count` open postings. A multi-row insert: SQLAlchemy splits it into
    statements under the limit, with the model's own column defaults."""
    await session.execute(insert(Job), [
        {
            "company": "acme", "req_id": str(n), "dedupe_key": f"acme:{n}", "title": f"Engineer {n}",
            "url": f"https://x.test/{n}", "level_band": "senior",
            "description_text": f"Build systems, posting {n}",
        }
        for n in range(count)
    ])
    await session.commit()
    return list(await session.scalars(select(Job.id).order_by(Job.id)))


async def test_fingerprint_pass_takes_more_ids_than_the_parameter_limit(db_session):
    ids = await _seed(db_session, RUN_SIZE)
    assert len(ids) > 32_767

    bumped = await fingerprint_content(db_session, ids)
    await db_session.commit()

    assert bumped == RUN_SIZE, "every posting is new to the fingerprint"
    last = await db_session.get(Job, ids[-1])
    assert last is not None
    assert last.content_hash == content_fingerprint(last.title, last.description_text)
    unstamped = await db_session.scalar(
        select(func.count()).select_from(Job).where(Job.content_hash.is_(None))
    )
    assert unstamped == 0

    # Idempotent at this size too: nothing moved, so nothing is bumped.
    assert await fingerprint_content(db_session, ids) == 0


Read = Callable[[AsyncSession, list[int]], Awaitable[object]]

#: Every other pass that reads a run-sized id list. On an empty table: the
#: driver refuses the statement before any row is read, so no rows are needed.
READS: dict[str, Read] = {
    "skills": lambda s, ids: extract_requirements(s, ids),
    "settle_stored_bands": settle_stored_bands,
    "owed_ids": lambda s, ids: owed_ids(s, ids, "any-version"),
    "lineage": lambda s, ids: detect_lineage(s, ids, dry_run=True),
    "twins": lambda s, ids: detect_twins(s, ids, dry_run=True),
    "domains": reclassify_domains,
    "roles": pending_roles,
    "places": reclassify_places,
    "scope": lambda s, ids: recompute_saved_scope(s, job_ids=ids),
}


@pytest.mark.parametrize("name", sorted(READS))
async def test_pass_reads_take_more_ids_than_the_parameter_limit(db_session, name):
    ids = list(range(1, RUN_SIZE + 1))
    await READS[name](db_session, ids)
    await db_session.rollback()
