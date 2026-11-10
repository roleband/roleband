"""Response contracts for the skills routes.

`GET /api/skills/top` and `/api/skills/overlap`.

- Shapes the handlers and `skills.analytics` build forbid unknown keys, declared
  in the order they are written.
- A leaderboard count is an integer; a skill's specificity and a pair's
  similarity are rounded floats.
- Companies, concept slugs, families and categories stay `str`: database strings.
  One key set per route, so no unions.
"""

from __future__ import annotations

from tracker.api.schemas.base import Built


class TopSkill(Built):
    """A concept in a slice of open roles: how many roles name it, its
    share of the slice's roles and of the market's, the ratio, and how
    characteristic of the slice it is (`skills.analytics.rank_skills`)."""

    term: str
    category: str
    job_count: int
    share: float
    market_share: float
    lift: float | None
    #: z-score of the smoothed log-odds, slice against the rest of the market; 0
    #: for the whole market.
    distinctiveness: float


class TopSkillsResponse(Built):
    """`GET /api/skills/top`: a narrowed slice by distinctiveness, the whole market
    by share; competencies apart; industries and deprecated concepts never appear."""

    items: list[TopSkill]
    #: Process, leadership and collaboration concepts: what roles expect, listed apart.
    competencies: list[TopSkill]
    #: Roles naming any skill, in the slice and in the whole market.
    roles: int
    market_roles: int
    narrowed: bool


class OverlapCompany(Built):
    company: str
    skill_count: int
    open: int


class OverlapPair(Built):
    """Two companies sharing at least one skill; `a` precedes `b` in the order shown."""

    a: str
    b: str
    shared: int
    union: int
    #: Cosine of the two companies' skill vectors, each skill a role share weighted
    #: by rarity across the companies compared, 0 to 1.
    similarity: float
    #: Slugs of the skills both name most, which the client names.
    top_shared: list[str]


class SkillOverlapResponse(Built):
    """`GET /api/skills/overlap`: the floor a skill must clear per company, echoed."""

    companies: list[OverlapCompany]
    pairs: list[OverlapPair]
    min_jobs: int
