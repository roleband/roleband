"""`GET /api/statistics/pay-table`: the companies hiring at one level in one country.

The route's job is which roles reach the builder (`test_pay_table.py` owns the
arithmetic): the country by any place the role lists, the level, the side, and
estimates read as US dollars for US pay only. An estimated base and an
estimated total never share a field: a base beside a total reads as a
lower-paying company.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from tests.factories import T0, make_company, make_job
from tracker.company_directory import FOLLOWED_WITH_SET
from tracker.db.models import Job, JobPlaceSet, JobPlaceSetMember, JobSkill, SkillConcept

pytestmark = pytest.mark.usefixtures("no_escape")

ROUTE = "/api/statistics/pay-table"
US = "?country=US&level=staff"


def _posting(req: str, company: str = "google", **over) -> Job:
    """An open staff product manager in Silicon Valley at `company`. A posting
    carries its place's whole parent chain, as the enricher writes it."""
    over.setdefault("dedupe_key", f"{company}:{req}")
    over.setdefault("location_groups", ["silicon_valley", "united_states", "north_america"])
    return make_job(req, company=company, **over)


def _posted(req: str, lo: int, hi: int, **over) -> Job:
    return _posting(req, disclosed_base_min=lo, disclosed_base_max=hi, disclosed_pay_basis="base",
                    disclosed_currency="USD", disclosed_pay_period="year", structured_at=T0, **over)


async def _rows(api_client, query: str = US) -> dict[str, dict]:
    body = (await api_client.get(f"{ROUTE}{query}")).json()
    return {row["company"]: row for row in body["rows"]}


@pytest.mark.asyncio
async def test_an_estimated_base_and_an_estimated_total_never_share_a_field(api_client, db_session):
    db_session.add(_posted("b1", 240_000, 300_000, comp_component="base", comp_median=None,
                           comp_base_median=242_000, comp_provider="builtin"))
    db_session.add(_posted("t1", 240_000, 300_000, company="meta", comp_component="total", comp_median=500_000,
                           comp_base_median=None, comp_provider="static"))
    await db_session.commit()

    rows = await _rows(api_client)
    assert rows["google"]["estimate_base"]["low"] == 242_000
    assert rows["google"]["estimate_total"] is None
    assert rows["meta"]["estimate_total"]["low"] == 500_000
    assert rows["meta"]["estimate_base"] is None


@pytest.mark.asyncio
async def test_a_company_joins_the_country_by_any_place_but_prices_only_that_countrys_roles(api_client, db_session):
    # "US or Canada": the role is hiring in the US, so GitLab has a row, but its
    # range may be Canada's and never becomes the US figure.
    db_session.add(_posted("ca", 203_200, 304_800, company="gitlab",
                           locations=["United States", "Canada"],
                           location_groups=["united_states", "canada", "north_america"]))
    await db_session.commit()

    rows = await _rows(api_client)
    assert rows["gitlab"]["open_roles"] == 1
    assert (rows["gitlab"]["low"], rows["gitlab"]["reason"]) == (None, "several_countries")


@pytest.mark.asyncio
async def test_an_estimate_for_pay_outside_the_us_is_no_estimate_here(api_client, db_session):
    db_session.add(_posting("uk", locations=["London, UK"], location_groups=["london", "uk", "europe"],
                            comp_component="total", comp_median=400_000, comp_provider="static"))
    await db_session.commit()

    uk = (await api_client.get(f"{ROUTE}?country=GB&level=staff")).json()
    assert uk["estimates"] is False
    assert [r["estimate_total"] for r in uk["rows"]] == [None]


@pytest.mark.asyncio
async def test_the_level_and_the_side_narrow_the_rows(api_client, db_session):
    db_session.add_all([
        make_company("google", "Google"),
        make_company("acme", "Acme", source=FOLLOWED_WITH_SET),
    ])
    db_session.add(_posted("s1", 240_000, 300_000))
    db_session.add(_posted("p1", 300_000, 400_000, level_band="principal"))
    db_session.add(_posted("a1", 200_000, 260_000, company="acme"))
    await db_session.commit()

    staff = await _rows(api_client)
    assert sorted(staff) == ["acme", "google"]
    assert staff["acme"]["followed_as_set"] is True and staff["google"]["followed_as_set"] is False
    assert sorted(await _rows(api_client, "?country=US&level=principal")) == ["google"]
    assert sorted(await _rows(api_client, f"{US}&side=other")) == ["acme"]
    assert sorted(await _rows(api_client, f"{US}&side=yours")) == ["google"]


@pytest.mark.asyncio
async def test_a_role_listed_in_several_places_counts_once(api_client, db_session):
    members = [
        _posted("m1", 240_000, 300_000),
        _posted("m2", 240_000, 300_000, locations=["New York, NY, USA"],
                location_groups=["new_york", "united_states", "north_america"]),
    ]
    db_session.add_all(members)
    await db_session.flush()
    place_set = JobPlaceSet(company="google", title="product manager", text_hash="a" * 32, size=len(members),
                            places=[job.locations[0] for job in members], rule_version="t1")
    db_session.add(place_set)
    await db_session.flush()
    db_session.add_all([
        JobPlaceSetMember(job_id=job.id, set_id=place_set.id, status="auto") for job in members
    ])
    await db_session.commit()

    rows = await _rows(api_client)
    assert rows["google"]["open_roles"] == 1


@pytest.mark.asyncio
async def test_a_country_we_cannot_place_answers_an_empty_table(api_client, db_session):
    db_session.add(_posted("s1", 240_000, 300_000))
    await db_session.commit()

    body = (await api_client.get(f"{ROUTE}?country=ZZ&level=staff")).json()
    assert (body["rows"], body["currency"], body["estimates"]) == ([], None, False)
    assert body["by_discipline"]["disciplines"] == []


async def _names(db_session, job: Job, slug: str) -> None:
    """The posting names this skill, as a skills read counts it."""
    concept = (await db_session.scalars(select(SkillConcept).where(SkillConcept.slug == slug))).first()
    if concept is None:
        concept = SkillConcept(slug=slug, display=slug.title(), facet="tool", category="language",
                               description=f"{slug}.", taxonomy_version="1")
        db_session.add(concept)
        await db_session.flush()
    db_session.add(JobSkill(
        job_id=job.id, concept_id=concept.id, importance_score=80, importance_band="core", confidence="high",
        modality="required", content_hash=f"{job.id}-{slug}", extractor_version="2.0.0", taxonomy_version="1",
    ))


@pytest.mark.asyncio
async def test_the_skill_narrows_the_estimate_as_it_narrows_the_row(api_client, db_session):
    """A row's estimate rests on the roles its figure rests on. Without the
    skill on the estimate read, the untouched role's $900K would widen it."""
    python = _posted("py", 200_000, 300_000, comp_component="base", comp_median=None,
                     comp_base_median=240_000, comp_provider="builtin")
    other = _posted("other", 200_000, 300_000, comp_component="base", comp_median=None,
                    comp_base_median=900_000, comp_provider="builtin")
    db_session.add_all([python, other])
    await db_session.flush()
    await _names(db_session, python, "python")
    await db_session.commit()

    every = await _rows(api_client)
    assert every["google"]["estimate_base"] == {
        "low": 240_000, "high": 900_000, "families": ["product_management"],
    }
    narrowed = await _rows(api_client, f"{US}&skill=python")
    assert narrowed["google"]["open_roles"] == 1
    assert narrowed["google"]["estimate_base"] == {
        "low": 240_000, "high": 240_000, "families": ["product_management"],
    }


@pytest.mark.asyncio
async def test_a_total_in_another_currency_is_no_dollar_estimate(api_client, db_session):
    # The posting's pay is for the US, but its estimate is not in dollars, so
    # it is unpriced here: nothing is converted.
    db_session.add(_posted("gbp", 200_000, 300_000, comp_component="total", comp_median=400_000,
                           comp_currency="GBP", comp_provider="static"))
    await db_session.commit()

    rows = await _rows(api_client)
    assert rows["google"]["estimate_total"] is None


@pytest.mark.asyncio
async def test_a_picked_discipline_keeps_the_countrys_currency_for_every_discipline(api_client, db_session):
    """The comparison shows every discipline, so the country's currency cannot
    come from the picked one: a discipline with no range of its own would
    otherwise leave every range reading as another currency."""
    db_session.add_all([
        _posted("pm", 200_000, 300_000, family="product_management"),
        _posted("swe", 260_000, 360_000, family="software_engineering"),
    ])
    await db_session.commit()

    body = (await api_client.get(f"{ROUTE}{US}&family=data_science")).json()
    assert body["currency"] == "USD"
    assert {d["family"]: d["ranges"] for d in body["by_discipline"]["disciplines"]} == {
        "product_management": 1, "software_engineering": 1,
    }
    assert [d["picked"] for d in body["by_discipline"]["disciplines"]] == [False, False]


@pytest.mark.asyncio
async def test_an_unknown_level_is_refused(api_client):
    assert (await api_client.get(f"{ROUTE}?country=US&level=overlord")).status_code == 422
    assert (await api_client.get(f"{ROUTE}?country=United+States&level=staff")).status_code == 422
