"""The skills routes' response contract.

`tracker/api/schemas/skills.py` declares what `/api/skills/top` and
`/api/skills/overlap` send. These tests hold it over real HTTP against
`tests/skills_contract_seed.py`:

1. **Shapes**: built shapes forbid unknown keys.
2. **An empty radar**: each list route answers its empty shape.
3. **The leaderboard** counts evidence-grounded requirements on open, in-scope,
   visible roles, never industries, deprecated concepts, context mentions or
   low-confidence extractions, and narrows by company, family and location.
4. **The overlap** ranks companies by open roles above a per-company floor.
5. **Drift**: a builder that adds, drops or mistypes a key fails the response.

`no_escape` guards every test. Counts are asserted as sets wherever the route
leaves a tie unordered.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.exceptions import ResponseValidationError
from pydantic import BaseModel
from sqlalchemy import select

from tests.skills_contract_seed import SeededSkills, hide_company, seed_skills
from tracker.api.routers import skills as router
from tracker.api.schemas import skills as contract


@pytest_asyncio.fixture
async def seeded(api_client, db_session, no_escape) -> SeededSkills:
    return await seed_skills(db_session)


@pytest_asyncio.fixture
async def hidden(db_session, seeded) -> SeededSkills:
    await hide_company(db_session)
    return seeded


def _fields(model) -> list[str]:
    return list(model.model_fields)


async def _get(api_client, path: str, status: int = 200) -> dict:
    response = await api_client.get(path)
    assert response.status_code == status, response.text
    return response.json()


def _counts(body: dict) -> dict[str, int]:
    """Roles per concept, skills and competencies alike (the API lists them apart)."""
    return {item["term"]: item["job_count"] for item in body["items"] + body["competencies"]}


# --------------------------------------------------------------------------- #
# 1-2. Shapes and an empty radar
# --------------------------------------------------------------------------- #


def test_built_shapes_forbid_unknown_keys():
    built = [
        model for model in vars(contract).values()
        if isinstance(model, type) and issubclass(model, BaseModel) and model.__module__ == contract.__name__
    ]
    assert len(built) >= 4
    assert [m.__name__ for m in built if m.model_config.get("extra") != "forbid"] == []


@pytest.mark.asyncio
async def test_an_empty_radar_answers_each_list_with_nothing_in_it(api_client, no_escape):
    assert await _get(api_client, "/api/skills/top") == {
        "items": [], "competencies": [], "roles": 0, "market_roles": 0, "narrowed": False,
    }
    assert await _get(api_client, "/api/skills/overlap") == {"companies": [], "pairs": [], "min_jobs": 2}


# --------------------------------------------------------------------------- #
# 3. The leaderboard
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_the_leaderboard_counts_only_grounded_requirements_on_visible_open_roles(api_client, hidden):
    body = await _get(api_client, "/api/skills/top")
    assert list(body) == _fields(contract.TopSkillsResponse)
    assert all(list(item) == _fields(contract.TopSkill) for item in body["items"])
    # Not g4's context mention or low-confidence sql, not a closed or out-of-scope role,
    # not the hidden company, never an industry or a deprecated concept.
    assert [(i["term"], i["category"], i["job_count"]) for i in body["items"]] == [
        ("python", "language", 7),
        ("kubernetes", "platform", 4),
        ("sql", "language", 2),
    ]
    # A competency is listed apart, never ranked with the skills.
    assert [(i["term"], i["job_count"]) for i in body["competencies"]] == [("stakeholder-management", 3)]
    assert all(list(item) == _fields(contract.TopSkill) for item in body["competencies"])
    # The whole market: share of the roles naming any skill, lift 1, nothing distinctive.
    assert body["narrowed"] is False and body["roles"] == body["market_roles"] > 0
    python = body["items"][0]
    assert python["share"] == round(7 / body["roles"], 4) == python["market_share"]
    assert (python["lift"], python["distinctiveness"]) == (1.0, 0.0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("company=google", {"python": 3, "sql": 2, "kubernetes": 1}),
        # The limit applies to each list: two skills, and the slice's one competency.
        ("company=google&company=openai&limit=2", {"python": 5, "kubernetes": 4, "stakeholder-management": 2}),
        ("family=product_management", {"python": 4, "sql": 2, "kubernetes": 1}),
        ("location_group=silicon_valley", {"python": 7, "kubernetes": 4, "stakeholder-management": 3, "sql": 2}),
        ("location_group=london", {}),
    ],
    ids=["one_company", "two_companies_limited", "family", "location", "no_location_match"],
)
async def test_the_leaderboard_narrows_by_company_family_location_and_limit(api_client, hidden, query, expected):
    assert _counts(await _get(api_client, f"/api/skills/top?{query}")) == expected


@pytest.mark.asyncio
async def test_a_narrowed_slice_leads_with_what_sets_it_apart(api_client, hidden):
    """By count, every slice would lead with the same ubiquitous concepts. A
    slice leads with the skill most characteristic of it against the rest
    of the market: OpenAI's roles carry 3 of the market's 4 Kubernetes
    requirements, while naming Python less often than the market does."""
    body = await _get(api_client, "/api/skills/top?company=openai")
    assert body["narrowed"] is True and body["roles"] < body["market_roles"]
    first, *rest = body["items"]
    assert first["term"] == "kubernetes" and first["lift"] > 1 and first["distinctiveness"] > 0
    python = next(i for i in rest if i["term"] == "python")
    assert python["distinctiveness"] < first["distinctiveness"]
    # The whole market is not narrowed: lift 1, ranked by share.
    market = await _get(api_client, "/api/skills/top")
    assert [i["term"] for i in market["items"]][0] == "python"


@pytest.mark.asyncio
async def test_a_visible_company_counts_until_it_is_hidden(api_client, db_session, seeded):
    visible = _counts(await _get(api_client, "/api/skills/top"))
    assert (visible["python"], visible["sql"]) == (9, 4)
    await hide_company(db_session)
    assert _counts(await _get(api_client, "/api/skills/top")) == {
        "python": 7, "kubernetes": 4, "stakeholder-management": 3, "sql": 2,
    }


# --------------------------------------------------------------------------- #
# 4. The overlap
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_every_read_that_counts_skills_counts_the_same_requirements(api_client, db_session, seeded):
    """The leaderboard and the daily demand rollup read one rule
    (`ELIGIBLE_REQUIREMENT`). g4's context mention and low-confidence sql, the
    industry and the deprecated concept count in neither, and each reader
    finds python and sql on the same roles."""
    from datetime import UTC, datetime

    from tracker.db.models import SkillConcept, SkillDemandDaily
    from tracker.skills.analytics import compute_skill_demand

    leaderboard = _counts(await _get(api_client, "/api/skills/top?limit=50"))

    await compute_skill_demand(db_session)
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    demand: dict[str, int] = {}
    for slug, count in (
        await db_session.execute(
            select(SkillConcept.slug, SkillDemandDaily.job_count)
            .join(SkillConcept, SkillConcept.id == SkillDemandDaily.concept_id)
            .where(SkillDemandDaily.metric_date == today)
        )
    ).all():
        demand[slug] = demand.get(slug, 0) + count

    for reader in (leaderboard, demand):
        assert not {"fintech", "perl"} & set(reader), reader
    # g4's context python and low-confidence sql would make these 10 and 5.
    assert leaderboard["python"] == demand["python"] == 9
    assert leaderboard["sql"] == demand["sql"] == 4


@pytest.mark.asyncio
async def test_overlap_scores_what_companies_share_beyond_what_every_company_names(api_client, hidden):
    """Generic skills shared by every company must not inflate similarity.
    Each company is a rarity-weighted skill vector with competencies excluded;
    when Python is the only shared skill and all companies name it, pairs score 0."""
    body = await _get(api_client, "/api/skills/overlap")
    assert list(body) == _fields(contract.SkillOverlapResponse)
    # Stakeholder management is a competency: OpenAI's set is Python and Kubernetes.
    assert body["companies"] == [
        {"company": "google", "skill_count": 2, "open": 5},
        {"company": "openai", "skill_count": 2, "open": 3},
        {"company": "anthropic", "skill_count": 1, "open": 2},
    ]
    assert body["pairs"] == [
        {"a": "google", "b": "openai", "shared": 1, "union": 3, "similarity": 0.0, "top_shared": ["python"]},
        {"a": "google", "b": "anthropic", "shared": 1, "union": 2, "similarity": 0.0, "top_shared": ["python"]},
        {"a": "openai", "b": "anthropic", "shared": 1, "union": 2, "similarity": 0.0, "top_shared": ["python"]},
    ]
    assert body["min_jobs"] == 2


@pytest.mark.asyncio
async def test_a_lower_floor_widens_each_set_and_a_company_limit_drops_every_pair(api_client, hidden):
    floor_one = await _get(api_client, "/api/skills/overlap?min_jobs=1")
    pairs = {(p["a"], p["b"]): p for p in floor_one["pairs"]}
    # Google and OpenAI now also share Kubernetes, which two of the three name:
    # that is what scores, and it weighs more than Python, which all three name.
    assert pairs[("google", "openai")]["top_shared"] == ["kubernetes", "python"]
    assert pairs[("google", "openai")]["similarity"] > 0
    assert pairs[("openai", "anthropic")]["similarity"] == 0.0
    assert floor_one["min_jobs"] == 1
    assert await _get(api_client, "/api/skills/overlap?limit_companies=1") == {
        "companies": [{"company": "google", "skill_count": 2, "open": 5}], "pairs": [], "min_jobs": 2,
    }


@pytest.mark.asyncio
async def test_the_companies_compared_can_be_named(api_client, hidden):
    body = await _get(api_client, "/api/skills/overlap?company=openai&company=google&company=nope")
    assert [c["company"] for c in body["companies"]] == ["openai", "google"]
    assert [(p["a"], p["b"]) for p in body["pairs"]] == [("openai", "google")]


# --------------------------------------------------------------------------- #
# 5. Drift
# --------------------------------------------------------------------------- #


def _each_skill_adding(real):
    def drifted(*args, **kwargs):
        body = real(*args, **kwargs)
        return {**body, "items": [{**item, "unmodelled": True} for item in body["items"]]}

    return drifted


def _pair_without_shared(real):
    def drifted(*args, **kwargs):
        return [{k: v for k, v in p.items() if k != "shared"} for p in real(*args, **kwargs)]

    return drifted


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "drift", "path"),
    [
        ("rank_skills", _each_skill_adding, "/api/skills/top"),
        ("compute_overlap", _pair_without_shared, "/api/skills/overlap"),
    ],
    ids=["top_skill_key_added", "pair_shared_dropped"],
)
async def test_a_builder_that_drifts_fails_the_response(api_client, hidden, monkeypatch, name, drift, path):
    monkeypatch.setattr(router, name, drift(getattr(router, name)))
    with pytest.raises(ResponseValidationError):
        await api_client.get(path)
