"""Skills analytics: the daily demand rollup and the skill ranking.

`compute_skill_demand` snapshots, per (company × family × concept), how many currently
open jobs carry a displayable requirement for that concept, into `skill_demand_daily`,
a daily history no screen reads yet. `rank_skills` is the pure ranking behind the
Skills tab. Industries are excluded everywhere here: a business vertical is never a
skill.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.db.models import Job, JobSkill, SkillConcept, SkillDemandDaily
from tracker.db.queries.jobs import insights_role_conds
from tracker.db.queries.skills import ELIGIBLE_REQUIREMENT


async def compute_skill_demand(session: AsyncSession) -> int:
    """Recompute today's skill-demand slices from `job_skills`. Returns slices written.

    Counts a role Insights describes (`insights_role_conds`: open, in scope, a place
    set once) once per (company, family, concept) when it has an eligible requirement for that concept (`ELIGIBLE_REQUIREMENT`), the same
    rule as `/api/skills/top`. Summing `job_count` across a concept's
    slices never double-counts (a job has one company+family). REPLACES today's
    slices: a slice whose last posting left is gone from today, not
    kept at its old count. Earlier days are untouched.
    """
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    rows = (
        await session.execute(
            select(
                Job.company,
                Job.family,
                JobSkill.concept_id,
                func.count(func.distinct(JobSkill.job_id)).label("job_count"),
            )
            .select_from(JobSkill)
            .join(SkillConcept, SkillConcept.id == JobSkill.concept_id)
            .join(Job, Job.id == JobSkill.job_id)
            .where(*insights_role_conds(), *ELIGIBLE_REQUIREMENT)
            .group_by(Job.company, Job.family, JobSkill.concept_id)
        )
    ).all()

    await session.execute(delete(SkillDemandDaily).where(SkillDemandDaily.metric_date == today))
    if rows:
        await session.execute(
            insert(SkillDemandDaily),
            [
                {"metric_date": today, "company": r.company, "family": r.family,
                 "concept_id": r.concept_id, "job_count": r.job_count}
                for r in rows
            ],
        )
    return len(rows)


#: Skill categories that name what a role is expected to do, not a skill that
#: tells one role from another (Roadmapping, Stakeholder Management,
#: Cross-functional Collaboration, Mentorship). They are the most-named
#: concepts, so a ranking by count would say "roles need roadmapping" for
#: every slice. They are listed apart, never ranked with Python or Kubernetes.
COMPETENCY_CATEGORIES: frozenset[str] = frozenset({"process", "leadership", "collaboration"})

#: Prior strength, in roles, of the informative Dirichlet prior (Monroe,
#: Colaresi & Quinn 2008, "Fightin' Words"): a slice's share is shrunk toward
#: the market's by this many pseudo-roles, so 2 of 3 roles cannot read as a
#: skill 20 times as characteristic as the market.
PRIOR_ROLES = 20.0
#: A skill named by fewer roles in the slice is never ranked as distinctive.
MIN_DISTINCTIVE_ROLES = 3


def rank_skills(
    slice_counts: Mapping[str, int],
    slice_roles: int,
    market_counts: Mapping[str, int],
    market_roles: int,
    meta: Mapping[str, tuple[str, str]],
    *,
    narrowed: bool,
    limit: int = 30,
) -> dict:
    """Skills of a slice by how characteristic they are of it. Pure.

    `slice_counts` / `market_counts`: concept slug -> roles naming it, in the
    slice and in the whole market; `slice_roles` / `market_roles`: roles with
    at least one named skill (the denominators, so extraction coverage is not
    read as demand); `meta`: slug -> (display, category).

    Each concept carries its `share` of the slice's roles, its `market_share`,
    `lift` (the ratio) and `distinctiveness`: the z-score of the smoothed
    log-odds difference between the slice and the rest of the market, with an
    informative Dirichlet prior of `PRIOR_ROLES` pseudo-roles at the market's
    rate. A narrowed slice ranks skills by distinctiveness (among those named by
    `MIN_DISTINCTIVE_ROLES` roles or more, then the rest by share); the whole
    market, whose lift is 1 everywhere, ranks by share. Competencies
    (`COMPETENCY_CATEGORIES`) are returned apart, by share.
    """
    rest_roles = max(0, market_roles - slice_roles)
    rows = []
    for slug, n in slice_counts.items():
        if n <= 0 or slice_roles <= 0:
            continue
        display, category = meta.get(slug, (slug, ""))
        m = market_counts.get(slug, n)
        share = n / slice_roles
        market_share = m / market_roles if market_roles else share
        z = 0.0
        if narrowed and rest_roles > 0 and market_share > 0:
            prior = PRIOR_ROLES * market_share
            rest_n = max(0, m - n)
            a = (n + prior) / (slice_roles + PRIOR_ROLES)
            b = (rest_n + prior) / (rest_roles + PRIOR_ROLES)
            a, b = min(a, 1 - 1e-9), min(b, 1 - 1e-9)
            delta = math.log(a / (1 - a)) - math.log(b / (1 - b))
            z = delta / math.sqrt(1 / (n + prior) + 1 / (rest_n + prior))
        rows.append({
            "term": slug,
            "display": display,
            "category": category,
            "job_count": n,
            "share": round(share, 4),
            "market_share": round(market_share, 4),
            "lift": round(share / market_share, 2) if market_share else None,
            "distinctiveness": round(z, 2),
        })

    def by_share(r: dict) -> tuple:
        return (-r["job_count"], r["term"])

    competencies = sorted((r for r in rows if r["category"] in COMPETENCY_CATEGORIES), key=by_share)
    skills = [r for r in rows if r["category"] not in COMPETENCY_CATEGORIES]
    if narrowed:
        ranked = sorted(
            skills,
            key=lambda r: (r["job_count"] < MIN_DISTINCTIVE_ROLES, -r["distinctiveness"], *by_share(r)),
        )
    else:
        ranked = sorted(skills, key=by_share)
    return {
        "items": ranked[:limit],
        "competencies": competencies[:limit],
        "roles": slice_roles,
        "market_roles": market_roles,
        "narrowed": narrowed,
    }
