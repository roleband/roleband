"""A stated total the posting calls on-target earnings is named base plus
commission, never total pay, and no equity is ever built on it."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tracker.db.models import Job
from tracker.pay_disclosure import names_on_target_earnings

_T0 = datetime(2026, 11, 1, tzinfo=UTC)

OKTA_LIKE = (
    "Below is the annual On Target Earnings (OTE) range for candidates located in the San Francisco "
    "Bay area. Your actual OTE will depend on your experience.\n\n"
    "The OTE range for this position located in the San Francisco Bay area is between: "
    "$184,000—$230,000 USD"
)
PLAIN_TOTAL = "The total compensation range for this role is $184,000 - $230,000."
# The boilerplate under every band at some employers: about other roles, not this band.
SALES_ASIDE = (
    "The base salary range for this role is $184,000 - $230,000. "
    "Sales positions generally offer a competitive On Target Earnings (OTE) incentive compensation structure."
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (OKTA_LIKE, True),
        ("Annual on-target earnings: $184,000 to $230,000.", True),
        (PLAIN_TOTAL, False),
        (SALES_ASIDE, False),
        # A condition after the name guards it as much as one before it.
        ("The total compensation range is $184,000 to $230,000 (on-target earnings for sales roles only).", False),
        ("For sales roles, the OTE range is $184,000 to $230,000.", False),
        # Another band's label names that band, not this one.
        ("Total compensation is $184,000 to $230,000, including base pay and equity.\n\n"
         "For account executives, OTE is $250,000 to $300,000.", False),
        # Its own sentence, or a heading with no figure of its own, names it.
        ("Total compensation is $184,000 to $230,000.\n\n"
         "For account executives, OTE is $250,000 to $300,000. This role's OTE is $184,000 to $230,000.", True),
        # The band is not in the text: nothing locates it, so nothing is named.
        ("Our OTE ranges are competitive.", False),
        (None, False),
    ],
)
def test_names_on_target_earnings_reads_the_band_s_own_sentence(text, expected):
    assert names_on_target_earnings(text, [184_000, 230_000]) is expected


def _job(key: str, *, basis: str, text: str) -> Job:
    return Job(company="okta", req_id=key, dedupe_key=f"okta:{key}", title="Enterprise Account Executive",
               url=f"https://example.test/{key}", locations=["San Francisco, CA"],
               location_groups=["silicon_valley"], domains=[], workplace_type="onsite", level_band="senior",
               level_confidence="unconfirmed", level_basis="company", family="sales", status="open",
               in_scope=True, first_seen=_T0, last_seen=_T0, first_posted_at=_T0, description_sections=[],
               description_text=text, structured_at=_T0, disclosed_base_min=184_000, disclosed_base_max=230_000,
               disclosed_currency="USD", disclosed_pay_basis=basis, disclosed_pay_period="year",
               comp_low=250_000, comp_median=300_000, comp_high=350_000, comp_currency="USD")


@pytest.mark.asyncio
async def test_job_detail_names_an_ote_total_and_builds_no_equity_on_it(api_client, db_session):
    ote = _job("ote", basis="total", text=OKTA_LIKE)
    total = _job("total", basis="total", text=PLAIN_TOTAL)
    # A base band in a posting that also says OTE: only a stated total is renamed.
    base = _job("base", basis="base", text=OKTA_LIKE)
    db_session.add_all([ote, total, base])
    await db_session.commit()

    async def package(job: Job) -> dict:
        return (await api_client.get(f"/api/jobs/{job.id}")).json()["comp_package"]

    shown = await package(ote)
    assert shown["on_target_earnings"] is True
    assert shown["total"] == {"low": 184_000, "high": 230_000, "provenance": "stated"}
    assert shown["components"] == []
    assert shown["equity_basis"] is None

    assert (await package(total))["on_target_earnings"] is False
    assert (await package(base))["on_target_earnings"] is False
