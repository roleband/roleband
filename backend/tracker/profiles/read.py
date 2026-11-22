"""The company profile reads: the roster, one company, its claims and its prices.

The dashboard's Companies screen (`api/routers/companies.py`) and the agent
operations (`agents/operations/companies.py`) both answer from these, so a
company reads the same through either. Values are resolved from multi-source
claims (`profiles/resolve.py`), so every field carries its provenance: which
source won, how fresh it is, and which other sources disagree.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, nullslast, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.analytics.comp_package import country_rows
from tracker.comp_providers.base import OUR_PAY_COUNTRY
from tracker.company_discovery import COMPANY_DISCOVERY, SECTORS
from tracker.company_store import unfollowed_company_slugs
from tracker.config import Settings
from tracker.db.models import CompanyBenefit, CompanyCompLevel, CompanyFact, CompanyProfile
from tracker.db.queries.companies import open_counts_by_company
from tracker.db.queries.reference_pay import (
    admit_benefits,
    admit_levels,
    benefit_scope,
    level_scope,
    reference_ladder,
)
from tracker.enrich.classify import location_groups_for
from tracker.levels.atlas import load_level_base
from tracker.levels.pay import PAY_POLICIES, bonus_ratio_for, profile_offer
from tracker.plugin_manifest import CORE_SOURCES
from tracker.plugins.registry import COMPANY_BENEFITS, COMPANY_FACTS, PAY_LEVELS, reader_providers
from tracker.profiles import prices as price_store
from tracker.profiles import store as profile_store
from tracker.profiles.benefits_builtin import (
    dataset_benefit_notes,
    dataset_benefits,
    plugin_benefits,
)
from tracker.taxonomy.comp_families import REFERENCE_FAMILY
from tracker.taxonomy.locations import LOCATION_GROUPS

#: The fields a profile resolves, in the order the profile shows them.
PROFILE_FIELDS = ("is_public", "ticker", "headcount", "hq_city", "website", "equity_vehicle", "vesting_schedule")
#: The slots a company profile is built from; their plugins are what it credits.
PROFILE_SLOTS = (PAY_LEVELS, COMPANY_FACTS, COMPANY_BENEFITS)
#: Price-history ranges the profile sparkline offers, mapped to a lookback window.
PRICE_RANGES = {"1m": 31, "3m": 93, "6m": 186, "1y": 366}
DEFAULT_PRICE_RANGE = "3m"


async def company_locations(session: AsyncSession, slug: str) -> list[dict]:
    """Open-role count per canonical city for one company, busiest first.

    Derived live from open in-scope jobs (`location_cities`, the lexical
    labels written with the job's places): offices are observed from
    postings, never declared, so the view stays current with every scrape.
    Each city carries the coarse location-group slugs its label falls into
    (the scope-filter axis) as badges, read again from the label, not from
    the job's own `location_groups`.

    `country` names the country-kind group explicitly instead of leaving the
    caller to guess which slug in `groups` is one. The guess ("the first
    entry that appears in the generated country table") holds only while no
    metro slug collides with a country slug, a convention rather than a
    contract, and the dashboard keeps no mirror of this taxonomy.
    `None` is a real answer, not a failure: `Wilmington, DE` resolves to no
    country because `de` is deliberately excluded from the US state tokens
    (`taxonomy.locations`), so the caller must have somewhere to put an
    unmapped city. A Canadian province code that `_CA_PROVINCE_CODES` admits
    ("Toronto, ON") resolves to Canada when the label carries no US state and
    no US signal.
    """
    rows = await session.execute(
        text(
            "SELECT city, count(*) AS n FROM"
            " (SELECT unnest(location_cities) AS city FROM jobs"
            "  WHERE company = :slug AND status = 'open' AND in_scope) t"
            " GROUP BY city ORDER BY n DESC, city"
        ),
        {"slug": slug},
    )
    out = []
    for city, n in rows.all():
        groups = location_groups_for([city])
        country = next(
            (s for s in groups if LOCATION_GROUPS.get(s, {}).get("kind") == "country"),
            None,
        )
        out.append({"city": city, "open_count": n, "groups": groups, "country": country})
    return out


async def board_count(session: AsyncSession, slug: str, hidden: list[str]) -> int:
    """The company's open roles as the Board counts them: none when it is off
    the Board (hidden, or not followed), so a "View N open roles"
    link never promises rows its Board will not show."""
    if slug in hidden:
        return 0
    return (await open_counts_by_company(session)).get(slug, 0)


def _profile_field(profile: CompanyProfile, field: str) -> dict:
    """A value plus everything a reader needs to say how much to trust it."""
    meta = (profile.field_meta or {}).get(field) or {}
    return {
        "value": getattr(profile, field, None),
        # The source is a code the reader names; the stored English label
        # stays in `field_meta` and never reaches the wire.
        "source": meta.get("source"),
        "observed_at": meta.get("observed_at"),
        "freshness": meta.get("freshness"),
        "is_manual": meta.get("is_manual", False),
        "conflicts": [
            {k: v for k, v in conflict.items() if k != "source_label"} for conflict in meta.get("conflicts", [])
        ],
    }


def _plugin_field(resolved: dict | None) -> dict:
    """A field the selected plugin answers, as `_profile_field` shapes ours: its
    value resolved now from its own claims, or empty where it has not read the
    company (never ours in its place)."""
    resolved = resolved or {}
    return {
        "value": resolved.get("value"),
        "source": resolved.get("source"),
        "observed_at": resolved.get("observed_at"),
        "freshness": resolved.get("freshness"),
        "is_manual": False,
        "conflicts": [
            {k: v for k, v in conflict.items() if k != "source_label"} for conflict in resolved.get("conflicts", [])
        ],
    }


async def profile_list(session: AsyncSession, hidden: list[str]) -> dict:
    """Every company profile off no Board, with its data-health badge, sectors,
    researched mark and latest price: the Companies roster."""
    profiles_stmt = select(CompanyProfile).order_by(CompanyProfile.slug)
    if hidden:
        profiles_stmt = profiles_stmt.where(CompanyProfile.slug.notin_(hidden))
    profiles = (await session.execute(profiles_stmt)).scalars().all()

    # "Levels imported" counts the reference ladder only, so the figure keeps
    # meaning one rung each rather than growing with every family harvested.
    providers = await reader_providers(session)
    counts: dict[str, int] = {}
    for rung in admit_levels(
        providers,
        (
            await session.execute(
                select(
                    CompanyCompLevel.company_slug, CompanyCompLevel.family, CompanyCompLevel.provider,
                    CompanyCompLevel.level_label, CompanyCompLevel.aliases, CompanyCompLevel.band,
                    CompanyCompLevel.band_source, CompanyCompLevel.country,
                ).where(reference_ladder(), *level_scope(providers))
            )
        ).all(),
        keep=lambda r: r.band is not None and r.country == OUR_PAY_COUNTRY,
    ):
        counts[rung.company_slug] = counts.get(rung.company_slug, 0) + 1

    # Latest cached quote per public company, so a row can show a price
    # without a round-trip. Absent for privates (and publics not yet fetched).
    prices = await price_store.latest_price_map(session)

    # Company size from the source answering it: the selected
    # plugin's, resolved from its claims, or ours from the profile column.
    facts_plugin = providers.source_for(COMPANY_FACTS)
    plugin_values = await profile_store.plugin_fields(session, providers) if facts_plugin else {}

    items = []
    for p in profiles:
        switched = profile_store.PLUGIN_FIELDS if facts_plugin else frozenset()
        theirs = plugin_values.get(p.slug, {})
        conflicts = [
            f for f in (p.field_meta or {})
            if f not in switched and (p.field_meta[f] or {}).get("conflicts")
        ] + [f for f in sorted(switched) if (theirs.get(f) or {}).get("conflicts")]
        price = prices.get(p.slug)
        items.append(
            {
                "slug": p.slug,
                "display_name": p.display_name,
                "logo_url": p.logo_url,
                "brand_color": p.brand_color,
                "is_public": p.is_public,
                "ticker": p.ticker,
                "equity_vehicle": p.equity_vehicle,
                "headcount": (theirs.get("headcount") or {}).get("value") if facts_plugin else p.headcount,
                "data_health": p.data_health,
                "conflict_fields": conflicts,
                "mapped_levels": counts.get(p.slug, 0),
                "sectors": list(catalog.sectors) if (catalog := COMPANY_DISCOVERY.get(p.slug)) else [],
                "in_dataset": p.slug in PAY_POLICIES,
                "price": price["price"] if price else None,
                "change_pct": price["change_pct"] if price else None,
                "currency": price["currency"] if price else None,
                "price_as_of": price["as_of"] if price else None,
            }
        )
    return {
        "items": items,
        "sectors": [sector.slug for sector in SECTORS],
        "attribution": providers.attribution(PROFILE_SLOTS),
    }


def _level_base_row(slug: str, row: dict[str, str]) -> dict:
    """One `level_base.csv` row as the profile shows it, with the company's
    bonus target where its policy states one (never a guessed 0), its stock
    where the dataset holds it, and a total only when all three are known."""
    def num(name: str) -> int | None:
        return int(row[name]) if row[name] else None

    base = int(row["base_usd"])
    ratio = bonus_ratio_for(slug, row["band"])
    stock = num("stock_usd")
    return {
        "band": row["band"], "base_usd": base,
        "bonus_ratio": None if ratio is None else round(ratio, 4),
        "bonus_usd": None if ratio is None else round(base * ratio), "below_lower": False,
        "stock_usd": stock,
        "total_usd": None if ratio is None or stock is None else base + round(base * ratio) + stock,
    }


async def profile_detail(session: AsyncSession, slug: str, hidden: list[str]) -> dict | None:
    """One company: resolved identity with provenance, comp baseline, benefits;
    None when there is no profile by that slug."""
    profile = await session.get(CompanyProfile, slug)
    if profile is None:
        return None

    # The baseline table is one row per band, read off the reference ladder; the
    # per-family ladders feed the job package, not this panel. It is US pay, as
    # every figure of ours is: a plugin's rungs for another country price only
    # postings there.
    providers = await reader_providers(session)
    levels = admit_levels(providers, (
        await session.execute(
            select(CompanyCompLevel)
            .where(
                CompanyCompLevel.company_slug == slug,
                reference_ladder(),
                *level_scope(providers),
            )
            # Label then id break tc ties, so equal medians never swap places
            # between two reads of the same data.
            .order_by(
                nullslast(CompanyCompLevel.tc_median.desc()),
                CompanyCompLevel.level_label,
                CompanyCompLevel.id,
            )
        )
    ).scalars().all())
    # The rows the estimate reads for a US posting, by the same screen: a
    # worldwide mix or a rung stated for another country is not shown as US pay.
    levels = country_rows(levels, OUR_PAY_COUNTRY)

    benefits = admit_benefits(providers, (
        await session.execute(
            select(CompanyBenefit)
            .where(CompanyBenefit.company_slug == slug, *benefit_scope(providers))
            .order_by(
                CompanyBenefit.category,
                nullslast(CompanyBenefit.value_usd.desc()),
                CompanyBenefit.name,
            )
        )
    ).scalars().all())

    # One source answers: the selected plugin's rows, none for a
    # company it has not read, or our dataset when no plugin is selected.
    # Our per-level base, the reference family, only while no pay
    # plugin is selected: one source answers the section.
    level_base = [] if providers.source_for(PAY_LEVELS) else [
        _level_base_row(slug, row) for row in load_level_base().get((slug, REFERENCE_FAMILY), ())]
    # A level paying less base than the one under it is shown, and said: the
    # figures carry their counts, there is no floor.
    for lower, row in zip(level_base, level_base[1:], strict=False):
        row["below_lower"] = row["base_usd"] < lower["base_usd"]

    benefits_plugin = providers.source_for(COMPANY_BENEFITS)
    benefit_groups = plugin_benefits(benefits) if benefits_plugin else dataset_benefits(slug)
    benefit_notes = [] if benefits_plugin else dataset_benefit_notes(slug)

    # Open-role count for the "View N open roles" jump to the board.
    open_roles = await board_count(session, slug, hidden)
    unfollowed = slug in await unfollowed_company_slugs(session)

    # Offices & where the open roles are, observed from live postings.
    locations = await company_locations(session, slug)
    hq = (profile.hq_city or "").strip().lower()
    for loc in locations:
        loc["is_hq"] = bool(hq) and loc["city"].lower().startswith(hq)

    # The choices offered when a field needs review: every source's latest
    # claim, most-trusted first. Suggesting beats making the person retype.
    candidates = await profile_store.candidates_for(session, slug)
    # One source per field: ours, except company size while a plugin
    # is selected for facts, which shows the plugin's or nothing.
    facts_plugin = providers.source_for(COMPANY_FACTS)
    plugin_values = (await profile_store.plugin_fields(session, providers, [slug])).get(slug, {})

    fields = {}
    for f in PROFILE_FIELDS:
        if facts_plugin and f in profile_store.PLUGIN_FIELDS:
            entry = _plugin_field(plugin_values.get(f))
            entry["answered_by"] = facts_plugin
            entry["editable"] = False  # a pin would be ours: refused while the plugin answers
        else:
            entry = _profile_field(profile, f)
            entry["answered_by"] = None
            entry["editable"] = True
        entry["candidates"] = candidates.get(f, [])
        fields[f] = entry

    return {
        "slug": profile.slug,
        "display_name": profile.display_name,
        "logo_url": profile.logo_url,
        "brand_color": profile.brand_color,
        "data_health": profile.data_health,
        "needs_review": _needs_review(profile, fields),
        # Every identity field carries its own provenance + conflicts.
        "fields": fields,
        "comp_levels": [
            {
                "level_label": r.level_label,
                "band": r.band,
                "currency": r.currency,
                "tc_median": r.tc_median,
                "base_amount": r.base_amount,
                "stock_amount": r.stock_amount,
                "bonus_amount": r.bonus_amount,
                "base_pct": r.base_pct,
                "stock_pct": r.stock_pct,
                "bonus_pct": r.bonus_pct,
                "source": r.provider,  # the publisher of the row
                "source_url": r.source_url,
            }
            for r in levels
        ],
        "level_base": level_base,
        # Perks are never summed into a total: overlapping perks and
        # unknown values make any sum a claim nobody measured.
        "benefits": benefit_groups,
        "benefit_notes": benefit_notes,
        "offer_policy": profile_offer(slug),
        "comp_notes": profile.comp_notes,
        "open_roles": open_roles,
        "unfollowed": unfollowed,
        "locations": locations,
        # Credited only where its data shows: not on a company it has not read.
        "attribution": providers.attribution(PROFILE_SLOTS, slug),
        # Sources the dashboard has no name for (a plugin's, or the ones it
        # adopts) are named by the plugin; ours it names from its catalog.
        "source_names": dict(providers.fact_labels),
        "sources": {
            "pay": providers.answering(PAY_LEVELS, slug),
            "benefits": providers.answering(COMPANY_BENEFITS, slug),
            "company_size": providers.answering(COMPANY_FACTS, slug),
        },
    }


def _needs_review(profile: CompanyProfile, fields: dict) -> list[dict]:
    """The manual-enrichment worklist for one company.

    A field needs review when sources disagree (`conflict`), when the winning claim
    has aged past its TTL (`stale`), or when nothing asserts it at all (`missing`).
    Each item carries a `suggestion` — our best guess at the right answer — so the
    workflow is "confirm or correct", not "go find it yourself".
    """
    required = set(profile_store.REQUIRED_FIELDS)
    out: list[dict] = []
    for name, f in fields.items():
        if f["is_manual"]:
            continue  # a human already settled this one
        if not f["editable"]:
            continue  # a plugin answers it: nothing of ours to confirm or correct
        if f["conflicts"]:
            reason = "conflict"
        elif f["freshness"] == "stale":
            reason = "stale"
        elif f["value"] is None and name in required:
            # Only REQUIRED fields count as missing. Optional ones (vesting_schedule)
            # are absent for almost every company and would flood the worklist with
            # noise nobody intends to fill in.
            reason = "missing"
        else:
            continue
        # Suggest the highest-trust candidate that actually asserts a value.
        suggestion = next(
            (c for c in f["candidates"] if c["value"] is not None), None
        )
        out.append(
            {
                "field": name,
                "reason": reason,
                "current": f["value"],
                "suggestion": suggestion,
                "candidates": f["candidates"],
            }
        )
    order = {"conflict": 0, "stale": 1, "missing": 2}
    out.sort(key=lambda i: order.get(i["reason"], 9))
    return out


async def profile_claims(session: AsyncSession, slug: str) -> list[dict]:
    """Every claim every source has made about the company, newest first within
    a field: the evidence behind a conflict badge."""
    providers = await reader_providers(session)
    # The claims of the source answering each field: ours, except
    # company size while a plugin is selected for facts.
    plugin = providers.source_for(COMPANY_FACTS)
    ours = CompanyFact.source.in_(sorted(CORE_SOURCES))
    if plugin is not None:
        switched = CompanyFact.field.in_(sorted(profile_store.PLUGIN_FIELDS))
        shown = or_(and_(~switched, ours),
                    and_(switched, providers.where(COMPANY_FACTS, CompanyFact.source, CompanyFact.company_slug)))
    else:
        shown = ours
    rows = (
        await session.execute(
            select(CompanyFact)
            .where(CompanyFact.company_slug == slug, shown)
            # Two sources can observe a field at the same moment: the source, then the id, keeps one order on every read.
            .order_by(CompanyFact.field, CompanyFact.observed_at.desc(), CompanyFact.source, CompanyFact.id.desc())
        )
    ).scalars().all()
    return [
        {
            "field": r.field,
            "value": (r.value or {}).get("v"),
            "source": r.source,
            "rank": providers.rank_of(r.source),
            "observed_at": r.observed_at,
        }
        for r in rows
    ]


async def profile_prices(
    session: AsyncSession, slug: str, price_range: str, *, settings: Settings, today: date | None = None
) -> dict[str, Any]:
    """Daily OHLC bars over one of `PRICE_RANGES`, oldest first, with the latest
    quote. Empty, not missing, for a company with no prices: a private company
    is a valid, price-less profile. The credit names the source of the bars
    shown, and `feed_configured` says whether a price key is set, so an empty
    chart can say what to do. An unknown range reads as the default."""
    shown = price_range if price_range in PRICE_RANGES else DEFAULT_PRICE_RANGE
    since = (today or datetime.now(UTC).date()) - timedelta(days=PRICE_RANGES[shown])
    bars = await price_store.price_history(session, slug, since)
    quote = (await price_store.latest_price_map(session, [slug])).get(slug)
    return {
        "slug": slug,
        "range": shown,
        "currency": (quote or {}).get("currency", "USD"),
        "latest": quote,
        "bars": bars,
        "attribution": await price_store.shown_attribution(session, slug) if bars else None,
        "feed_configured": (await price_store.api_key(session, settings))[0] is not None,
    }
