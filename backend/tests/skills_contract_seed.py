"""Realistic rows for the skills contract.

The skill leaderboard and overlap read evidence-grounded `job_skills` over open,
in-scope roles; the daily demand rollup counts the same requirements.

Counts are chosen so no ordering the builders leave unspecified is ever exercised
by a tie: the leaderboard orders by count alone, overlap ranks companies by open
roles, and a pair's shared skills sort by the smaller count.

| rows | what they exercise |
|---|---|
| google `g1`..`g3`, `g5` | python on three roles, sql on two, kubernetes on one; a fourth open role with no skills, so google leads on open roles |
| google `g4` | python only as context and sql only at low confidence: neither counts |
| google `g-closed`, `g-out` | a closed and an out-of-scope role naming python: never counted |
| openai `o1`..`o3` | kubernetes on three, python and stakeholder management on two |
| anthropic `a1`, `a2` | python on two, stakeholder management on one: in the overlap at a floor of 2 by python alone |
| hidden-co `h1`, `h2` | python and sql on two roles of a company the seed leaves visible and `hide_company` hides |
| concepts `fintech`, `perl` | an industry and a deprecated concept: never skills |
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_company, make_job
from tracker.db.models import (
    Favorite,
    Job,
    JobSkill,
    SkillConcept,
    TrackedCompany,
)

NOW = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)


def _concept(slug: str, display: str, facet: str = "technology", category: str = "language",
             status: str = "active") -> SkillConcept:
    return SkillConcept(slug=slug, display=display, facet=facet, category=category, description=f"{display}.",
                        taxonomy_version="1", status=status)


def _role(company: str, key: str, family: str, **over) -> Job:
    return make_job(f"{company}-{key}", company=company, dedupe_key=f"{company}:{key}", family=family,
                first_seen=NOW - timedelta(days=5), last_seen=NOW, **over)


@dataclass(frozen=True)
class SeededSkills:
    jobs: dict[str, int]


async def seed_skills(session: AsyncSession) -> SeededSkills:
    session.add(make_company("hidden-co", "Hidden Co", source="url"))
    concepts = {
        "python": _concept("python", "Python"),
        "sql": _concept("sql", "SQL"),
        "kubernetes": _concept("kubernetes", "Kubernetes", category="platform"),
        "stakeholder": _concept("stakeholder-management", "Stakeholder management", facet="competency",
                                category="leadership"),
        "fintech": _concept("fintech", "Fintech", facet="industry", category="domain"),
        "perl": _concept("perl", "Perl", status="deprecated"),
    }
    session.add_all(concepts.values())
    await session.flush()

    pm, em = "product_management", "engineering_management"
    jobs = {
        "g1": _role("google", "g1", pm),
        "g2": _role("google", "g2", pm),
        "g3": _role("google", "g3", pm),
        "g4": _role("google", "g4", pm),
        "g5": _role("google", "g5", pm),
        "g-closed": _role("google", "closed", pm, status="closed", closed_at=NOW - timedelta(days=1)),
        "g-out": _role("google", "out-of-scope", pm, in_scope=False),
        "o1": _role("openai", "o1", em),
        "o2": _role("openai", "o2", em),
        "o3": _role("openai", "o3", em),
        "a1": _role("anthropic", "a1", em),
        "a2": _role("anthropic", "a2", pm),
        "h1": _role("hidden-co", "h1", pm),
        "h2": _role("hidden-co", "h2", pm),
    }
    session.add_all(jobs.values())
    await session.flush()

    def skill(job: str, concept: str, score: int, band: str = "core", confidence: str = "high") -> JobSkill:
        return JobSkill(job_id=jobs[job].id, concept_id=concepts[concept].id, importance_score=score,
                        importance_band=band, confidence=confidence, modality="required",
                        content_hash=f"{job}-{concept}", extractor_version="2.0.0", taxonomy_version="1")

    session.add_all([
        skill("g1", "python", 90), skill("g1", "sql", 70, "important"), skill("g1", "kubernetes", 50, "supporting"),
        skill("g2", "python", 80), skill("g2", "sql", 60, "important"),
        skill("g3", "python", 85), skill("g3", "fintech", 95),
        skill("g4", "python", 30, "context"), skill("g4", "sql", 75, confidence="low"),
        skill("g-closed", "python", 90), skill("g-out", "python", 90),
        skill("o1", "python", 95), skill("o1", "kubernetes", 60),
        skill("o2", "python", 88), skill("o2", "kubernetes", 65), skill("o2", "stakeholder", 40, "supporting"),
        skill("o3", "kubernetes", 70), skill("o3", "stakeholder", 45, "supporting"),
        skill("a1", "python", 70), skill("a1", "stakeholder", 50), skill("a1", "perl", 99),
        skill("a2", "python", 72),
        skill("h1", "python", 99), skill("h1", "sql", 90),
        skill("h2", "python", 98), skill("h2", "sql", 80),
        Favorite(job_id=jobs["g1"].id, created_at=NOW - timedelta(days=1)),
    ])
    await session.commit()
    return SeededSkills(jobs={key: row.id for key, row in jobs.items()})


async def hide_company(session: AsyncSession, slug: str = "hidden-co") -> None:
    """Hide a tracked company, as the Settings switch does."""
    await session.execute(update(TrackedCompany).where(TrackedCompany.slug == slug).values(visible=False))
    await session.commit()
