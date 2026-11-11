"""Pure-logic tests for the Pace assembly (no DB).

Pins the aging bands, the medians, the unknown ages beside them, the
per-company minimum, and the response model behind the Statistics "Pace"
sub-tab.
"""

from __future__ import annotations

from datetime import UTC, datetime

from tracker.analytics.velocity import (
    DURATION_KEY,
    MIN_DURATION_SAMPLE,
    _median,
    aging_histogram,
    build_velocity,
)


def test_median_even_odd_and_empty():
    assert _median([1, 2, 3]) == 2
    assert _median([1, 2, 3, 4]) == 2.5
    assert _median([]) is None
    assert _median([5]) == 5.0


def test_aging_histogram_band_boundaries_are_zero_filled():
    hist = aging_histogram([0, 6.9, 7, 13, 40, 90, 200])
    counts = {h["lo"]: h["count"] for h in hist}
    assert counts[0] == 2  # under a week: 0 and 6.9
    assert counts[7] == 2  # 1-2 weeks: 7 (inclusive) and 13
    assert counts[14] == 0  # zero-filled, band still present
    assert counts[30] == 1  # 1-2 months: 40
    assert counts[90] == 2  # 90 (inclusive) and 200
    assert len(hist) == 6  # every band present


def test_an_age_below_zero_is_the_first_band_so_the_bands_add_up():
    hist = aging_histogram([-0.5, 3])
    assert [(h["lo"], h["count"]) for h in hist][:2] == [(0, 2), (7, 0)]
    assert sum(h["count"] for h in hist) == 2


def _fixture():
    open_rows = [
        ("google", 2, False), ("google", 10, True), ("openai", 40, False),
        ("openai", 100, False), ("meta", 3, True),
    ]
    openings = [*[("google", "opened")] * 5, *[("openai", "opened")] * 8, ("meta", "opened")]
    # 6 roles came down with a known time posted (>= MIN_DURATION_SAMPLE),
    # so the overall median reports.
    came_down = [
        ("google", 10, False), ("google", 20, False), ("openai", 5, False),
        ("openai", 15, True), ("openai", 25, False), ("meta", 8, False),
    ]
    return open_rows, openings, came_down


def test_build_velocity_counts_openings_and_roles_that_came_down():
    v = build_velocity(*_fixture(), open_total=5, days=30)
    k = v["kpis"]
    assert (k["opened"], k["closed"]) == (14, 6)
    assert "updated" not in k and "net" not in k
    assert k["median_days_open"] == 10  # median of [2,3,10,40,100]
    assert k[DURATION_KEY] == 12.5  # median of [5,8,10,15,20,25]
    assert (k["closed_sample"], k["closed_unknown"], k["age_unknown"]) == (6, 0, 0)


def test_unknown_ages_stay_out_of_the_medians_and_bands_and_are_counted_beside_them():
    open_rows = [("a", 2, True), ("a", None, False), ("a", None, False), ("b", 40, False)]
    came_down = [("a", None, False), ("b", 12, True)]
    v = build_velocity(open_rows, [], came_down, open_total=4, days=30)
    k = v["kpis"]
    assert k["age_unknown"] == 2
    assert sum(b["count"] for b in v["aging"]) + k["age_unknown"] == k["open_total"]
    assert k["median_days_open"] == 21  # median of [2, 40]: the unknowns are not 0
    assert (k["closed"], k["closed_sample"], k["closed_unknown"]) == (2, 1, 1)
    assert sum(b["count"] for b in v["posted"]) == k["closed_sample"]
    # Each share is over the rows the bands draw.
    assert k["employer_dated_share"] == 1 / 2
    assert k["closed_employer_dated_share"] == 1.0
    # A company counts its unknown open roles; its median does not.
    a = next(c for c in v["by_company"] if c["company"] == "a")
    assert (a["open"], a["median_days_open"], a["closed"]) == (3, 2, 1)


def test_build_velocity_observed_duration_gated_by_min_sample():
    open_rows, openings, _ = _fixture()
    thin = [("google", 10, False), ("openai", 20, False)]  # only 2 < MIN_DURATION_SAMPLE
    assert MIN_DURATION_SAMPLE > 2
    v = build_velocity(open_rows, openings, thin, open_total=5, days=30)
    assert v["kpis"][DURATION_KEY] is None
    assert v["kpis"]["closed_sample"] == 2


def test_a_company_states_time_posted_only_from_five_known_durations():
    """Four known durations and three unknown are still too few for one
    company; five known give its median."""
    four = [("a", d, False) for d in (1, 2, 3, 4)] + [("a", None, False)] * 3
    v = build_velocity([], [], four, open_total=0, days=30)
    assert v["by_company"][0][DURATION_KEY] is None
    assert v["by_company"][0]["closed"] == 7
    five = [("a", d, False) for d in (1, 2, 3, 4, 50)]
    v = build_velocity([], [], five, open_total=0, days=30)
    assert v["by_company"][0][DURATION_KEY] == 3


def test_build_velocity_by_company_ranked_by_opened_with_medians():
    v = build_velocity(*_fixture(), open_total=5, days=30)
    order = [c["company"] for c in v["by_company"]]
    assert order == ["openai", "google", "meta"]  # opened 8 > 5 > 1
    openai = v["by_company"][0]
    assert openai["open"] == 2 and openai["closed"] == 3
    assert openai["median_days_open"] == 70  # median of [40,100]
    assert openai[DURATION_KEY] is None  # 3 durations: under the minimum


def test_the_duration_is_never_named_a_time_to_fill():
    """`median_time_to_fill` would assert a hire from a posting going away.

    The measure goes out under one name, in the payload and in the response
    model the OpenAPI document is built from, the thin-sample None included.
    """
    from tracker.api.routers.statistics import VelocityOut

    reported = build_velocity(*_fixture(), open_total=5, days=30)
    open_rows, openings, _ = _fixture()
    thin = build_velocity(open_rows, openings, [("google", 10, False)], open_total=5, days=30)

    for payload in (reported, thin):
        rows = [payload["kpis"], *payload["by_company"]]
        assert rows, "the fixture must produce rows for this contract to mean anything"
        for row in rows:
            assert DURATION_KEY in row
            assert not [key for key in row if "fill" in key], row
    assert reported["kpis"][DURATION_KEY] is not None
    assert thin["kpis"][DURATION_KEY] is None
    served = VelocityOut.model_json_schema()["$defs"]
    assert not [
        (model, field)
        for model, spec in served.items()
        for field in spec.get("properties", {})
        if "fill" in field
    ]


def test_the_response_model_drops_nothing_build_velocity_reports():
    """A `response_model` FILTERS: a field it omits leaves the payload silently.

    That is the whole hazard of modelling a route as a typed model rather than
    a bare dict — the alias, or a KPI nobody thought to declare, would simply stop
    being served with every test still green. Imported here (not at module
    scope) so the pure-logic suite above keeps costing no API import.
    """
    from tracker.api.routers.statistics import VelocityOut

    # The route adds where the figures start (`since`) beside what
    # `build_velocity` reports.
    since = datetime(2026, 11, 3, 6, 2, tzinfo=UTC)
    payload = {**build_velocity(*_fixture(), open_total=5, days=30), "since": since}
    assert VelocityOut.model_validate(payload).model_dump() == payload

    empty = {**build_velocity([], [], [], open_total=0, days=7), "since": None}
    assert VelocityOut.model_validate(empty).model_dump() == empty


def test_build_velocity_empty_is_safe():
    v = build_velocity([], [], [], open_total=0, days=7)
    assert v["kpis"]["opened"] == 0 and v["kpis"]["median_days_open"] is None
    assert v["by_company"] == []
    assert sum(b["count"] for b in v["aging"]) == 0
    assert len(v["aging"]) == 6
    assert (v["kpis"]["employer_dated_share"], v["kpis"]["closed_employer_dated_share"]) == (None, None)


def test_reposts_and_finds_already_listed_are_their_own_buckets_never_opened():
    openings = [*[("google", "opened")] * 4, *[("google", "reposted")] * 3, *[("google", "already_listed")] * 2]
    v = build_velocity([("google", 5, False)], openings, [], open_total=1, days=30)
    k = v["kpis"]
    assert (k["opened"], k["reposted"], k["already_listed"]) == (4, 3, 2)
    assert v["by_company"][0]["reposted"] == 3


def test_posted_bands_count_each_role_that_came_down_once_on_the_aging_bands():
    """Pace draws how long roles stayed up beside the age of open roles, on
    the same bands, so the two read as one pair."""
    came_down = [("a", 3, False), ("a", 10, False), ("b", 45, False), ("b", 200, False)]
    v = build_velocity([("a", 1, False)], [], came_down, open_total=1, days=30)
    assert [(b["lo"], b["count"]) for b in v["posted"]] == [(0, 1), (7, 1), (14, 0), (30, 1), (60, 0), (90, 1)]
    assert [b["lo"] for b in v["posted"]] == [b["lo"] for b in v["aging"]]


def test_every_company_that_opened_or_closed_a_role_keeps_its_row():
    """Twenty companies opened roles and one only closed one: the table lists
    all twenty-one, past the limit, so its Opened and Closed columns add up
    to the tiles; a company with neither fills the table only up to it."""
    open_rows = [(f"c{i}", 5, False) for i in range(20)] + [("quiet", 9, False)]
    openings = [(f"c{i}", "opened") for i in range(20)]
    v = build_velocity(open_rows, openings, [("gone", 30, False)], open_total=21, days=30, company_limit=15)
    names = [c["company"] for c in v["by_company"]]
    assert len(names) == 21 and "gone" in names and "quiet" not in names
    assert sum(c["opened"] for c in v["by_company"]) == v["kpis"]["opened"]
    assert sum(c["closed"] for c in v["by_company"]) == v["kpis"]["closed"]
    few = build_velocity(open_rows[-1:], [], [], open_total=1, days=30)
    assert [c["company"] for c in few["by_company"]] == ["quiet"]
