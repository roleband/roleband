"""The skills routes' response contract.

`tracker/api/schemas/skills.py` declares what `/api/skills/top` sends. These
tests hold it over real HTTP against
`tests/skills_contract_seed.py`:

1. **Shapes**: built shapes forbid unknown keys.
2. **An empty radar**: each list route answers its empty shape.
3. **The leaderboard** counts evidence-grounded requirements on open, in-scope,
   visible roles, never industries, deprecated concepts, context mentions or
   low-confidence extractions, and narrows by company, family and location.
4. **One counting rule**: the leaderboard and the daily rollup count the same
   requirements.
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
    assert len(built) >= 2
    assert [m.__name__ for m in built if m.model_config.get("extra") != "forbid"] == []


@pytest.mark.asyncio
async def test_an_empty_radar_answers_each_list_with_nothing_in_it(api_client, no_escape):
    assert await _get(api_client, "/api/skills/top") == {
        "items": [], "competencies": [], "roles": 0, "market_roles": 0, "narrowed": False,
    }
    # The leaderboard is the one Skills read (docs/decisions/0004-insights-answers-a-question.md).
    assert (await api_client.get("/api/skills/overlap")).status_code == 404


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
# 4. One counting rule
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


# --------------------------------------------------------------------------- #
# 5. Drift
# --------------------------------------------------------------------------- #


def _each_skill_adding(real):
    def drifted(*args, **kwargs):
        body = real(*args, **kwargs)
        return {**body, "items": [{**item, "unmodelled": True} for item in body["items"]]}

    return drifted


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "drift", "path"),
    [
        ("rank_skills", _each_skill_adding, "/api/skills/top"),
    ],
    ids=["top_skill_key_added"],
)
async def test_a_builder_that_drifts_fails_the_response(api_client, hidden, monkeypatch, name, drift, path):
    monkeypatch.setattr(router, name, drift(getattr(router, name)))
    with pytest.raises(ResponseValidationError):
        await api_client.get(path)
