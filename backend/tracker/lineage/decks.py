"""The decks a posting belongs to, read for one posting: its repost stack and its twins.

A deck stacks postings that are one role; it never merges them. Each member
stays its own posting with its own dates, places and pay, and the link that
placed it says why it is in the deck. Job detail (`api/routers/lineage.py`)
and the agent operations (`agents/operations/relations.py`) both read decks
from here. A posting's place set is read by `lineage.place_sets.place_set_of`.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.db.models import Job, JobLineageLink, JobTwinLink
from tracker.lineage.detect import effective_link_clause, link_fact
from tracker.lineage.project import choose_predecessors
from tracker.lineage.twins import connected_twin_ids, twin_component_links


@dataclass(frozen=True)
class StackMember:
    job: Job
    #: The inbound link the projection chose for this member; None for the first posting.
    link: JobLineageLink | None
    #: The link ties this member to its predecessor: auto and not rejected, or confirmed.
    effective: bool


async def lineage_stack(session: AsyncSession, lineage_id: int) -> list[StackMember]:
    """Every posting of the lineage, oldest first, each with the link that placed it.

    The inbound link per member is the one the projection chose
    (`project.choose_predecessors`), never the last row read, so a pending
    proposal to a posting outside the lineage cannot stand in for the
    confirmed link that placed the member."""
    members = list(
        (
            await session.scalars(
                select(Job).where(Job.lineage_id == lineage_id).order_by(Job.lineage_seq.asc())
            )
        ).all()
    )
    links = (
        await session.scalars(
            select(JobLineageLink).where(
                JobLineageLink.job_id.in_([m.id for m in members]),
                effective_link_clause(),
            )
        )
    ).all()
    by_pair = {(lk.job_id, lk.prior_job_id): lk for lk in links}
    link_by_job = {
        job_id: by_pair[(fact.job_id, fact.prior_job_id)]
        for job_id, fact in choose_predecessors([link_fact(lk) for lk in links]).items()
    }
    stack = []
    for member in members:
        link = link_by_job.get(member.id)
        effective = link is not None and (
            (link.confidence == "auto" and link.status != "rejected") or link.status == "confirmed"
        )
        stack.append(StackMember(member, link, effective))
    return stack


@dataclass(frozen=True)
class TwinDeck:
    #: The posting first, then every twin reached from it, by id.
    member_ids: list[int]
    #: The twins linked to the posting itself rather than through another twin.
    direct: set[int]
    #: Each direct twin's link, by the twin's id.
    links: dict[int, JobTwinLink]


async def twin_deck(session: AsyncSession, job_id: int) -> TwinDeck:
    """The posting's twins: every posting reached through effective twin links,
    and the links of the direct ones, the only ones shown with their evidence."""
    links = await twin_component_links(session, job_id)
    component, direct = connected_twin_ids(job_id, list(links.values()))
    own = [link_id for link_id, (a, b) in links.items() if job_id in (a, b)]
    direct_links = {
        (link.job_b_id if link.job_a_id == job_id else link.job_a_id): link
        for link in (await session.scalars(select(JobTwinLink).where(JobTwinLink.id.in_(own)))).all()
    }
    return TwinDeck([job_id, *sorted(component)], direct, direct_links)
