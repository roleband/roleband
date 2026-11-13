"""A role's pay package, built the one way every screen reads it.

Job detail shows one role's package and the Stock tab sums many, so both build
it here from the same inputs: the estimate of the source answering pay, the
band the posting states, the company's rungs for the posting's own country,
and whether the level is placed. The arithmetic is `analytics.comp_package`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.analytics.comp_package import (
    Baselines,
    build_job_package,
    country_rows,
    select_baselines,
)
from tracker.api.serializers.jobs import disclosed_comp
from tracker.comp_providers.base import OUR_PAY_COUNTRY
from tracker.db.models import Job, JobCompEstimate
from tracker.db.queries.reference_pay import package_rows_for
from tracker.enrich.enricher import ESTIMATE_FIELDS
from tracker.plugins.registry import PAY_LEVELS, Providers
from tracker.schema import OUR_ESTIMATE_SOURCE, UNPLACED_BASIS_VALUES
from tracker.taxonomy.locations import pay_country

_IDS_PER_READ = 10_000


def shown_source(providers: Providers) -> str:
    """The source whose figures a screen shows: the plugin answering pay, or ours."""
    return providers.source_for(PAY_LEVELS) or OUR_ESTIMATE_SOURCE


def stored_estimate(job: Job) -> dict[str, Any]:
    """The estimate copied onto the job: what a job no re-estimate has reached shows."""
    return {name: getattr(job, name) for name in ESTIMATE_FIELDS}


def role_package(
    job: Job,
    estimate: Mapping[str, Any],
    *,
    baselines: Baselines,
    providers: Providers,
    disclosed: dict | None,
) -> dict:
    """One role's package. `estimate` carries `ESTIMATE_FIELDS` of the shown
    source; `baselines` are the company's rungs for the posting's country."""
    country = pay_country(job.location_groups)
    return build_job_package(
        company=job.company,
        band=job.level_band,
        family=job.family,
        title=job.title,
        comp_low=estimate["comp_low"],
        comp_median=estimate["comp_median"],
        comp_high=estimate["comp_high"],
        comp_provenance=estimate["comp_provenance"],
        disclosed=disclosed,
        baselines=baselines,
        base_estimate=(
            {"low": estimate["comp_base_low"], "median": estimate["comp_base_median"],
             "high": estimate["comp_base_high"], "provider": estimate["comp_provider"],
             "as_of": estimate["comp_as_of"]}
            if estimate["comp_base_median"] is not None else None
        ),
        heuristic=shown_source(providers) == OUR_ESTIMATE_SOURCE,
        # Our split heuristic is measured on US pay only.
        us_pay=country == OUR_PAY_COUNTRY,
        covered=providers.answering(PAY_LEVELS, job.company)["covered"],
        # A NULL basis is an older row whose band was read as a level.
        level_placed=job.level_basis not in UNPLACED_BASIS_VALUES,
    )


def baselines_for(rows: Iterable[Any], country: str | None) -> Baselines:
    """The ONE rung per (company, family, band) a posting in `country` is
    measured against. A worldwide-mix row is not US pay and never measures one."""
    return select_baselines(country_rows(list(rows), country))


async def role_packages(
    session: AsyncSession, jobs: Sequence[Job], providers: Providers
) -> list[tuple[Job, dict]]:
    """Every job's package, in two reads however many jobs: the shown source's
    estimates and the companies' rungs."""
    if not jobs:
        return []
    shown = shown_source(providers)
    ids = [job.id for job in jobs]
    estimates: dict[int, dict[str, Any]] = {}
    # A statement carries at most 32,767 bound values.
    for start in range(0, len(ids), _IDS_PER_READ):
        for row in (
            await session.scalars(
                select(JobCompEstimate).where(
                    JobCompEstimate.source == shown,
                    JobCompEstimate.job_id.in_(ids[start:start + _IDS_PER_READ]),
                )
            )
        ).all():
            estimates[row.job_id] = {name: getattr(row, name) for name in ESTIMATE_FIELDS}
    rungs: dict[str, list[Any]] = {}
    for row in await package_rows_for(session, providers, {job.company for job in jobs}):
        rungs.setdefault(row.company_slug, []).append(row)
    measured: dict[tuple[str, str | None], Baselines] = {}
    out = []
    for job in jobs:
        country = pay_country(job.location_groups)
        key = (job.company, country)
        if key not in measured:
            measured[key] = baselines_for(rungs.get(job.company, ()), country)
        out.append((job, role_package(
            job,
            estimates.get(job.id) or stored_estimate(job),
            baselines=measured[key],
            providers=providers,
            disclosed=disclosed_comp(job),
        )))
    return out
