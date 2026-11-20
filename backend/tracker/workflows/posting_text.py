"""Read a posting's text where its row has none.

Two readers ask. The description backfill drains the open rows still blank
after a run (`post_passes.backfill_missing_descriptions`), and a person who
opens such a posting asks for it at once (`OpenTextReads`), so the role is not
shown without its text until the backfill reaches it. Both rebuild the posting
from its row (`stored_posting`) and read it through the company's own adapter
(`read_text`), so the two can never disagree about what a read stores.

Who may be read on open (`text_target`): an open row with no text, at a
company we collect (active, enabled, and the source policy's one decision,
`collection_access`, not denying it), whose adapter reads a posting's text
from the posting alone (`text_from_posting`), and, when the row names its
source, that same adapter. The backfill adds a schedule gate
(`scanned_automatically`) because it runs after scheduled runs too; an open is
the person asking, as a scan they start is.

Transactions: no read holds one across a request. The row is read and the
transaction ended, the posting is fetched, and the text is written in its own
transaction by `repo.fill_blank_description`, which reads the row again and
never replaces text another writer stored meanwhile.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from tracker.connectors import (
    BaseAdapter,
    BreakerPool,
    RateLimiterPool,
    build_adapter,
    structure_job_detail,
    text_from_posting,
)
from tracker.connectors.detail.base import sections_to_text
from tracker.content import fingerprint_content
from tracker.db.models import Job, TrackedCompany
from tracker.db.repo import fill_blank_description, refresh_search_vectors
from tracker.platform.util import html_to_text
from tracker.schema import PostingTextOutcome, RawJob
from tracker.source_policy import collection_access

logger = logging.getLogger(__name__)

#: Retries per request for a read a person waits on, as the posting page reads
#: (`posting_pages.ON_OPEN_RETRIES`): one absorbs a single transient 5xx, the
#: run's full budget would hold the person for many seconds.
ON_OPEN_RETRIES = 1

#: The longest one open waits on its read, whatever the adapter's requests add
#: up to. Past it the read is a failure the person can retry, never a request
#: the page waits on with no end.
ON_OPEN_DEADLINE_SECONDS = 20.0

#: After a read that found no text, another open of the same posting answers
#: from memory for this long, so a person never pays twice for a source's bad
#: minute. Asking again on purpose (`retry`) reads at once.
ON_OPEN_COOL_DOWN_SECONDS = 600.0

#: A breaker is run-scoped by design (`platform/breaker.py`); the API process
#: has no runs, so its breakers start over after this long, as the posting
#: page reads' do.
_OPEN_BREAKER_WINDOW_SECONDS = 900.0


def _cool_down_clock() -> float:
    """The cool-down's clock: monotonic, and its own name, so a test can move
    it without moving the event loop's."""
    return time.monotonic()


def stored_posting(job: Job) -> RawJob:
    """The posting rebuilt from its row, to be read again.

    The row has no text, so neither has the posting rebuilt from it.
    `RawJob` defaults to complete, and an adapter skips the read of a posting
    whose text is complete."""
    return RawJob(
        company=job.company,
        req_id=job.req_id,
        title=job.title,
        url=job.url,
        locations=list(job.locations or []),
        description_complete=False,
    )


async def read_text(adapter: BaseAdapter, raw: RawJob, source: str) -> str | None:
    """Read `raw`'s text through `adapter`, which the caller has entered.

    Fills `raw`'s description fields and returns its plain text, or None when
    the source served none. Raises whatever the read raises."""
    # What the listing row carried, where `hydrate` needs it and the posting
    # can rebuild it.
    raw.detail_payload = adapter.payload_from_posting(raw)
    await adapter.hydrate(raw)
    structure_job_detail(raw, adapter.drift, payload=raw.detail_payload, source=source)
    return sections_to_text(raw.description_sections) or html_to_text(raw.description_html) or None


@dataclass(frozen=True)
class TextTarget:
    """What building the adapter needs, copied off the company row so no read
    touches the ORM (or its transaction) across a request."""

    slug: str
    adapter: str
    board_token: str | None
    board_region: str | None
    consent: str | None


def _owed(job: Job) -> bool:
    """The row's half of "read its text on open": open, and no text."""
    return job.status == "open" and job.description_text is None


async def text_target(session: AsyncSession, job: Job) -> TextTarget | None:
    """The company to read `job`'s text through on open, or None when nothing
    may read it (see the module docstring)."""
    if not _owed(job):
        return None
    row = await session.get(TrackedCompany, job.company)
    if row is None or row.status != "active" or not row.enabled or not row.adapter:
        return None
    if not text_from_posting(row.adapter):
        return None
    provider = (job.source_facts or {}).get("provider")
    if provider and provider != row.adapter:
        # A posting another binding listed: its id means nothing to this one.
        return None
    if collection_access(row.adapter, company=row.slug, consent=row.consent_fingerprint).denied:
        return None
    return TextTarget(row.slug, row.adapter, row.board_token, row.board_region, row.consent_fingerprint)


async def readable_text_on_open(session: AsyncSession, job: Job) -> bool:
    """Should opening this posting read its text? The row's own gate goes
    first, so a posting that has text costs the detail read no query."""
    if not _owed(job):
        return False
    return await text_target(session, job) is not None


async def _derive_from_text(session: AsyncSession, job_id: int) -> None:
    """What the post-passes derive from a row's text, for a row a person
    opened, as `scripts.refetch_descriptions` does for the rows it saves: the
    search vector, so a search finds it now, and the content fingerprint,
    which moves `content_changed_at` for every pass that gates on it.
    Requirements and the embedding follow when a run next touches the row:
    extracting requirements upserts the whole skills catalogue first, too
    much for a read a person waits on."""
    await session.flush()
    await refresh_search_vectors(session, [job_id])
    await fingerprint_content(session, [job_id])


class OpenTextReads:
    """Reading a posting's text because someone opened it, as one service per
    process: one pacer pool, one breaker pool, one reader per posting (two
    opens of one posting send one request), and the recent reads that found
    no text.

    The process that serves opens owns the instance (the API, through
    `api.deps.get_text_reads`), as it owns `posting_pages.OpenPageReads`.
    """

    def __init__(self) -> None:
        # Built at the first open, after the API's startup enabled shared
        # pacing, so this pool paces against every provider-facing process's
        # use of the host.
        self.limiter_pool = RateLimiterPool()
        self._breaker_pool = BreakerPool()
        self._breakers_since = time.monotonic()
        self._locks: dict[int, asyncio.Lock] = {}
        self._holders: Counter[int] = Counter()
        self._found_none: dict[int, float] = {}

    def breaker_pool(self) -> BreakerPool:
        if time.monotonic() - self._breakers_since > _OPEN_BREAKER_WINDOW_SECONDS:
            self._breaker_pool, self._breakers_since = BreakerPool(), time.monotonic()
        return self._breaker_pool

    def _cooling(self, job_id: int) -> bool:
        at = self._found_none.get(job_id)
        if at is None:
            return False
        if _cool_down_clock() - at > ON_OPEN_COOL_DOWN_SECONDS:
            del self._found_none[job_id]
            return False
        return True

    def _remember_none(self, job_id: int) -> None:
        """Note a read that found no text, and forget every note whose
        cool-down has ended, so a long-lived process keeps only live ones."""
        now = _cool_down_clock()
        self._found_none = {
            known: at for known, at in self._found_none.items() if now - at <= ON_OPEN_COOL_DOWN_SECONDS
        }
        self._found_none[job_id] = now

    @asynccontextmanager
    async def _one_reader(self, job_id: int) -> AsyncIterator[None]:
        lock = self._locks.setdefault(job_id, asyncio.Lock())
        self._holders[job_id] += 1
        try:
            async with lock:
                yield
        finally:
            self._holders[job_id] -= 1
            if not self._holders[job_id]:
                del self._holders[job_id]
                self._locks.pop(job_id, None)

    async def _read(self, target: TextTarget, raw: RawJob) -> str | None:
        """One paced, breaker-guarded read within the deadline. Never raises:
        a failure of the source's or of ours is no text."""
        try:
            adapter = build_adapter(
                target.slug,
                target.adapter,
                target.board_token,
                board_region=target.board_region,
                limiter_pool=self.limiter_pool,
                breaker_pool=self.breaker_pool(),
                # The adapter re-checks the policy on entry: it must see the
                # consent the gate saw.
                consent=target.consent,
            )
            adapter.max_retries = ON_OPEN_RETRIES
            async with asyncio.timeout(ON_OPEN_DEADLINE_SECONDS), adapter:
                return await read_text(adapter, raw, target.adapter)
        except Exception as exc:  # noqa: BLE001 - one posting's read is best effort
            logger.warning("text read on open failed for %s %s: %s", target.slug, raw.req_id, exc)
            return None

    async def read_one(
        self, session: AsyncSession, job_id: int, *, retry: bool = False
    ) -> tuple[PostingTextOutcome, Job] | None:
        """Read one posting's text because someone opened it.

        Returns None for an unknown posting, else what happened and the row
        afterwards. `already_read` answers from storage with no request;
        `not_available` is a posting nothing may read on open; `failed` stored
        nothing, and another open answers it from memory until the cool-down
        ends, unless it asks again on purpose (`retry`). A concurrent open of
        the same posting waits for this one and answers from storage.
        """
        async with self._one_reader(job_id):
            job = await session.get(Job, job_id, populate_existing=True)
            if job is None:
                return None
            if job.description_text is not None:
                await session.commit()
                return "already_read", job
            target = await text_target(session, job)
            raw = stored_posting(job)
            # Nothing is written above: end the transaction, so no connection
            # sits idle in one while the source answers.
            await session.commit()
            if target is None:
                return "not_available", job
            if not retry and self._cooling(job_id):
                return "failed", job
            text = await self._read(target, raw)
            if text is None:
                # Read again: a scan may have stored the text while the
                # source failed us, and then the posting has its text.
                job = await session.get(Job, job_id, populate_existing=True)
                await session.commit()
                if job is None:
                    return None
                if job.description_text is not None:
                    return "already_read", job
                self._remember_none(job_id)
                return "failed", job
            self._found_none.pop(job_id, None)
            wrote = await fill_blank_description(session, job_id, raw, text)
            if wrote:
                await _derive_from_text(session, job_id)
            await session.commit()
            job = await session.get(Job, job_id, populate_existing=True)
            if job is None:
                return None
            if wrote:
                return "read", job
            # Another writer gave it text meanwhile, or it closed.
            return ("already_read" if job.description_text is not None else "not_available"), job
