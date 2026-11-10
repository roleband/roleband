"""Skills analytics: the leaderboard and cross-company overlap.

Every route declares its response in `api/schemas/skills.py`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from tracker.api.deps import InsightsScopeDep, OffBoardDep, SessionDep
from tracker.api.schemas.skills import (
    SkillOverlapResponse,
    TopSkillsResponse,
)
from tracker.db.models import (
    Job,
    JobSkill,
    SkillConcept,
)
from tracker.db.queries.jobs import exclude_hidden
from tracker.db.queries.skills import ELIGIBLE_REQUIREMENT, skill_role_counts
from tracker.skills.analytics import (
    COMPETENCY_CATEGORIES,
    compute_overlap,
    rank_skills,
    seriate,
)

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
    if location_group:
        slice_conds.append(Job.location_groups.overlap(location_group))
    market_counts, market_roles, meta = await skill_role_counts(session, hidden)
    narrowed = bool(slice_conds)
    if narrowed:
        slice_counts, slice_roles, _ = await skill_role_counts(session, hidden, slice_conds)
    else:
        slice_counts, slice_roles = market_counts, market_roles
    ranked = rank_skills(
        slice_counts, slice_roles, market_counts, market_roles, meta, narrowed=narrowed, limit=limit
    )
    # Each skill is its `term`; the client names it from its catalog.
    for key in ("items", "competencies"):
        ranked[key] = [{k: v for k, v in skill.items() if k != "display"} for skill in ranked[key]]
    return ranked


@router.get("/api/skills/overlap", response_model=SkillOverlapResponse)
async def skills_overlap(
    session: SessionDep,
    hidden: OffBoardDep,
    scope: InsightsScopeDep,
    min_jobs: Annotated[int, Query(ge=1)] = 2,
    limit_companies: Annotated[int, Query(ge=1, le=50)] = 12,
    company: Annotated[list[str] | None, Query()] = None,
) -> dict:
    """Cross-company skill similarity over currently-open roles.

    A company's skill set = skill concepts required in at least `min_jobs` of its
    open roles (the floor trims one-off mentions that inflate spurious overlap;
    industries and competencies are excluded: a vertical is not a skill, and what
    every role is expected to do is overlap every company shares). Each pair
    is scored by the cosine of rarity-weighted skill vectors (`compute_overlap`).
    The companies are those named in `company`, else the top `limit_companies` by
    open roles in the scope, shown in an order that puts similar ones together.
    """
    rows = (
        await session.execute(
            exclude_hidden(
                select(
                    Job.company,
                    SkillConcept.slug,
                    SkillConcept.display,
                    func.count(func.distinct(JobSkill.job_id)).label("n"),
                )
                .select_from(JobSkill)
                .join(SkillConcept, SkillConcept.id == JobSkill.concept_id)
                .join(Job, Job.id == JobSkill.job_id)
                .where(
                    Job.status == "open",
                    Job.in_scope.is_(True),
                    *ELIGIBLE_REQUIREMENT,
                    SkillConcept.category.notin_(COMPETENCY_CATEGORIES),
                    *scope.conds(),
                ),
                hidden,
            ).group_by(Job.company, SkillConcept.slug, SkillConcept.display)
        )
    ).all()

    open_counts = dict(
        (
            await session.execute(
                exclude_hidden(
                    select(Job.company, func.count()).where(
                        Job.status == "open", Job.in_scope.is_(True), *scope.conds()
                    ), hidden
                ).group_by(Job.company)
            )
        ).all()
    )

    # company -> {concept slug: job_count} above the mention floor.
    skills: dict[str, dict[str, int]] = {}
    for company_slug, slug, _display, n in rows:
        if n >= min_jobs:
            skills.setdefault(company_slug, {})[slug] = int(n)

    if company:
        ranked = [c for c in dict.fromkeys(company) if c in skills][:limit_companies]
    else:
        ranked = sorted(
            skills.keys(), key=lambda c: (-open_counts.get(c, 0), c)
        )[:limit_companies]

    companies = [
        {"company": c, "skill_count": len(skills[c]), "open": int(open_counts.get(c, 0))}
        for c in ranked
    ]

    pairs = compute_overlap(skills, ranked, {c: open_counts.get(c, 0) for c in ranked})
    for p in pairs:
        # Slugs: the client names each skill from its catalog.
        p["top_shared"] = p.pop("top_shared_terms")
    order = {c: i for i, c in enumerate(seriate(ranked, pairs))}
    companies.sort(key=lambda row: order[row["company"]])

    return {"companies": companies, "pairs": pairs, "min_jobs": min_jobs}
