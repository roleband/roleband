"""A level we cannot place is never priced as if it were known.

A posting whose title names no rung we can place (basis `unmapped`) keeps a
guessed band for sorting. Pricing that guess shows a firm figure for a level
the posting never stated: a "Product Manager" posting that states a base of
$151,200 to $223,200 was shown a Senior Product Manager's $390,000. So:

1. **No rung estimate.** Neither our resolver nor a plugin's answers a band
   whose basis is unplaced, in the scan and in the re-estimate alike.
2. **The stated range still shows,** whole: no equity, bonus or total is built
   from the guessed band, and nothing is reconciled against it.
3. **A placed level is priced as before:** the controls for both.
4. **Relevel re-estimates a row whose placement moves,** even when the band
   it keeps for sorting stays the same.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from tracker.analytics.comp_package import (
    NO_SPLIT_LEVEL_UNPLACED,
    PROV_STATED,
    build_job_package,
)
from tracker.comp_providers.base import CompContext, CompEstimate, CompProvider
from tracker.db.models import Job
from tracker.enrich.comp import OURS, CompResolver, EstimateSet
from tracker.enrich.enricher import Annotation, build_enriched
from tracker.enrich.level_mapper import read_level
from tracker.plugins import reestimate
from tracker.schema import LevelBand, LevelBasis, LevelConfidence, RawJob, RoleTrack
from tracker.workflows import relevel

PM = RawJob(company="google", req_id="pm-1", title="Product Manager", url="https://example.test/pm-1",
            locations=["Mountain View, CA"])


class _Senior(CompProvider):
    """Answers one figure for any senior posting, like a reference row would."""

    def __init__(self, provider: str, median: int) -> None:
        self.name, self.provider, self.median = "table", provider, median

    async def lookup(self, ctx: CompContext) -> CompEstimate | None:
        if ctx.band is not LevelBand.SENIOR:
            return None
        return CompEstimate(median=self.median, low=self.median - 20_000, high=self.median + 20_000,
                            currency="USD", source="Senior PM figure", detail={},
                            base_median=self.median // 2, base_low=self.median // 2 - 10_000,
                            base_high=self.median // 2 + 10_000, provider=self.provider)


def _estimates() -> EstimateSet:
    return EstimateSet(CompResolver([_Senior("manual", 390_000)]), ("tpl", CompResolver([_Senior("tpl", 400_000)])),
                       fingerprints={OURS: "fp-ours", "tpl": "fp-tpl"}, fingerprint="fp-shown")


def _annotation(basis: LevelBasis) -> Annotation:
    return Annotation(band=LevelBand.SENIOR, confidence=LevelConfidence.UNCONFIRMED, family="product_management",
                      location_groups=["silicon_valley"], track=RoleTrack.PRODUCT_PROGRAM, domains=[], basis=basis)


def test_the_fixture_title_is_one_we_cannot_place():
    """The case is the real reading, not one assumed for the test."""
    reading = read_level(PM)
    assert (reading.band, reading.basis) == (LevelBand.SENIOR, LevelBasis.UNMAPPED)


@pytest.mark.asyncio
async def test_an_unmapped_level_gets_no_estimate_from_any_source():
    enriched = await build_enriched(PM, _annotation(LevelBasis.UNMAPPED), _estimates())

    assert (enriched.comp_median, enriched.comp_base_median) == (None, None)
    assert enriched.comp_sources == []
    for source in (OURS, "tpl"):
        assert enriched.estimates[source]["comp_median"] is None
        assert enriched.estimates[source]["comp_base_median"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("basis", [LevelBasis.COMPANY, LevelBasis.STATED, LevelBasis.GENERIC, None])
async def test_a_placed_level_is_priced_as_before(basis):
    """The control: the refusal is for an unplaced level, not for this band or
    title. A NULL basis reads as generic, and generic words do place a band."""
    enriched = await build_enriched(PM, _annotation(basis), _estimates())

    assert enriched.estimates[OURS]["comp_median"] == 390_000
    # The job shows the selected source: the plugin's.
    assert enriched.comp_median == enriched.estimates["tpl"]["comp_median"] == 400_000


def _stored(level_basis: str | None) -> SimpleNamespace:
    return SimpleNamespace(company="google", level_band="senior", level_basis=level_basis,
                           family="product_management", location_groups=["silicon_valley"], title=PM.title)


@pytest.mark.asyncio
async def test_the_re_estimate_refuses_an_unmapped_level_too():
    """The re-estimate reads stored rows: it must apply the same rule, or the
    next reference change would bring the figure back."""
    refused = await reestimate._estimates(_estimates(), _stored("unmapped"))
    priced = await reestimate._estimates(_estimates(), _stored("company"))

    assert {source: row["comp_median"] for source, row in refused.items()} == {OURS: None, "tpl": None}
    assert {source: row["comp_median"] for source, row in priced.items()} == {OURS: 390_000, "tpl": 400_000}


# The posting's own words: a base range and nothing else.
STATED_BASE = {
    "disclosed": True, "base_min": 151_200, "base_max": 223_200, "currency": "USD", "pay_basis": "base",
    "pay_period": "year", "bonus_pct": None, "snippet": "$151,200 - $223,200 base", "confidence": "high",
}
# A measured split at the guessed band, the row a placed Senior would be scaled by.
SENIOR_PM = {("google", "product_management", "senior"): {
    "base_amount": 390_000, "stock_amount": 300_000, "bonus_amount": 60_000,
    "base_pct": 0.52, "stock_pct": 0.4, "bonus_pct": 0.08, "source": "acme-pay",
}}


def _package(level_placed: bool) -> dict:
    return build_job_package(company="google", band="senior", family="product_management", comp_low=None,
                             comp_median=None, comp_high=None, comp_provenance=None, disclosed=STATED_BASE,
                             baselines=SENIOR_PM, level_placed=level_placed)


def test_an_unmapped_level_shows_the_stated_base_whole():
    pkg = _package(level_placed=False)

    assert pkg["stated"] == {"low": 151_200, "high": 223_200}
    assert pkg["no_split_reason"] == NO_SPLIT_LEVEL_UNPLACED
    assert pkg["components"] == [] and pkg["total"] is None
    assert pkg["equity_basis"] is None
    # Nothing is checked against the guessed band's row either.
    assert (pkg["reconciliation"], pkg["market_gap"]) == (None, None)
    assert (pkg["split_source"], pkg["split_provider"]) == (None, None)


def test_a_placed_level_with_the_same_stated_base_is_split():
    """The control for the test above."""
    pkg = _package(level_placed=True)

    kinds = {c["kind"]: c for c in pkg["components"]}
    assert kinds["base"]["provenance"] == PROV_STATED
    assert "equity" in kinds and pkg["total"] is not None
    assert pkg["no_split_reason"] is None


_T0 = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_relevel_re_estimates_a_row_whose_placement_moves_but_not_its_band(db_session, monkeypatch):
    """Stored as unmapped Senior, the company's vocabulary now places it at
    Senior: the band is the same, the estimate is not."""
    refreshed: list[int] = []

    async def record(session, ids):
        refreshed.extend(ids)

    monkeypatch.setattr(relevel.reestimate, "refresh_jobs", record)
    # "Sr. Technical Program Manager" reads Senior on Amazon's own vocabulary.
    job = Job(company="amazon", req_id="tpm", dedupe_key="amazon:tpm", title="Sr. Technical Program Manager", url="https://example.test/tpm",
              locations=["Seattle, WA"], location_groups=["seattle"], domains=[], workplace_type="onsite",
              level_band="senior", level_confidence="unconfirmed", level_basis="unmapped",
              family="program_management", track="product_program", comp_currency="USD", status="open",
              in_scope=False, first_seen=_T0, last_seen=_T0, first_posted_at=_T0, description_sections=[])
    db_session.add(job)
    await db_session.commit()

    result = await relevel.relevel_jobs(db_session)
    await db_session.commit()
    await db_session.refresh(job)

    assert (job.level_band, job.level_basis) == ("senior", "company")
    assert result["band_moved"] == 0
    assert refreshed == [job.id]


def _posted(key: str, basis: str) -> Job:
    return Job(company="google", req_id=key, dedupe_key=f"google:{key}", title=PM.title, url=f"https://example.test/{key}",
               locations=["Mountain View, CA"], location_groups=["silicon_valley"], domains=[],
               workplace_type="onsite", level_band="senior", level_confidence="unconfirmed", level_basis=basis,
               family="product_management", track="product_program", comp_currency="USD", status="open",
               in_scope=True, first_seen=_T0, last_seen=_T0, first_posted_at=_T0, description_sections=[],
               disclosed_base_min=151_200, disclosed_base_max=223_200, disclosed_currency="USD",
               disclosed_pay_basis="base", disclosed_pay_period="year")


@pytest.mark.asyncio
async def test_the_job_detail_shows_an_unmapped_level_s_stated_base_whole(api_client, db_session):
    unmapped, placed = _posted("pm-u", "unmapped"), _posted("pm-p", "company")
    db_session.add_all([unmapped, placed])
    await db_session.commit()

    shown = (await api_client.get(f"/api/jobs/{unmapped.id}")).json()["comp_package"]
    control = (await api_client.get(f"/api/jobs/{placed.id}")).json()["comp_package"]

    assert shown["stated"] == {"low": 151_200, "high": 223_200}
    assert shown["no_split_reason"] == NO_SPLIT_LEVEL_UNPLACED
    assert shown["total"] is None
    assert control["stated"] == shown["stated"]
    assert control["no_split_reason"] != NO_SPLIT_LEVEL_UNPLACED
