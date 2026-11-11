"""Skills analytics: the leaderboard.

Every route declares its response in `api/schemas/skills.py`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from tracker.api.deps import InsightsScopeDep, OffBoardDep, SessionDep
from tracker.api.schemas.skills import TopSkillsResponse
from tracker.db.models import (
    Job,
)
from tracker.db.queries.skills import skill_role_counts
from tracker.skills.analytics import rank_skills

router = APIRouter()


@router.get("/api/skills/top", response_model=TopSkillsResponse)
async def skills_top(
    session: SessionDep,
    hidden: OffBoardDep,
    scope: InsightsScopeDep,
    company: Annotated[list[str] | None, Query()] = None,
    family: Annotated[list[str] | None, Query()] = None,
    location_group: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
) -> dict:
    """The Skills tab: a slice's skills by how characteristic they are
    of it, against the whole market; the whole market by share; competencies
    apart, industries excluded."""
    slice_conds: list = [*scope.conds()]
    if company:
        slice_conds.append(Job.company.in_(company))
    if family:
        slice_conds.append(Job.family.in_(family))
    market_counts, market_roles, meta = await skill_role_counts(session, hidden)
    narrowed = bool(slice_conds or location_group)
    if narrowed:
        slice_counts, slice_roles, _ = await skill_role_counts(
            session, hidden, slice_conds, location_group=location_group
        )
    else:
        slice_counts, slice_roles = market_counts, market_roles
    ranked = rank_skills(
        slice_counts, slice_roles, market_counts, market_roles, meta, narrowed=narrowed, limit=limit
    )
    # Each skill is its `term`; the client names it from its catalog.
    for key in ("items", "competencies"):
        ranked[key] = [{k: v for k, v in skill.items() if k != "display"} for skill in ranked[key]]
    return ranked
