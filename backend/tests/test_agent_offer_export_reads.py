"""The offer, application and export reads answer what their dashboard routes
answer, leave out a category the person does not share, and export a packet
whose bytes are stable.

Every read runs against one scratch database seeded by `scripts.seed_synthetic`
(its corpus postings and pursuits), with the offer, the valuations and an
interview entered through the dashboard's own routes and stores. Each agent
read is compared with its dashboard route over real ASGI, every page of it
joined, so the comparison fails on a row either side adds, drops or spells
differently.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import select, update

import tracker.api.routers.agent as agent_router
from scripts.seed_synthetic import seed, task_req_id
from tracker.agents.config import AgentAccessConfig, set_agent_access
from tracker.agents.operations import export
from tracker.agents.operations.export import OUTSIDE, SECRET, Redactor, canonical
from tracker.agents.operations.search import PAGE_BUDGET_BYTES
from tracker.agents.operations.workspace import ensure_workspace_id
from tracker.agents.pursuits import InterviewWrite, add_interview, ensure_favorite
from tracker.api.agent_operations import PREFIX
from tracker.config import get_settings
from tracker.db.models import AppSetting, CompanyProfile, Job
from tracker.platform.paths import DATA_DIR
from tracker.profiles import store as profile_store

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_escape")]

OFFER = {
    "inputs": {
        "company": "stripe", "listed": False, "base": 212000, "bonus_pct": 15, "vehicle": "options",
        "grant_unit": "shares", "grant": 18000, "strike": 9.5, "price": None, "vesting": [25, 25, 25, 25],
        "sign_on": [40000, None],
    },
    "answered": ["company", "base", "stock", "strike", "vesting", "bonus", "sign_on"],
    "started_from": {"company": "stripe", "title": "Staff Software Engineer, Payments"},
}
#: Enough valuations that a small tier's page cannot hold them all.
VALUATION_COMPANIES = [f"private-co-{index:02d}" for index in range(40)]


@pytest_asyncio.fixture
async def workspace(db_session, api_client, scratch_scope):
    """The seeded workspace with agent reads on, an offer, forty valuations,
    an interview, and more roles starred than one board page holds."""
    await seed(db_session, 12, seed_value=1, derived=False, agent_tasks=True)
    await set_agent_access(db_session, AgentAccessConfig(enabled=True, allow_writes=False))
    await ensure_workspace_id(db_session)
    interviewing = await _job_id(db_session, "INTERVIEW")
    await add_interview(db_session, interviewing, InterviewWrite(
        label="System design with the platform team", scheduled_at=datetime.now(UTC) + timedelta(days=2),
        format="video",
    ), actor="user")
    for job_id in (await db_session.scalars(select(Job.id).order_by(Job.id).limit(14))).all():
        await ensure_favorite(db_session, job_id)
    await db_session.commit()
    assert (await api_client.put("/api/profile/offer", json=OFFER)).status_code == 200
    for index, company in enumerate(VALUATION_COMPANIES):
        body = {"unit": "per_share" if index % 2 else "company", "grant_at": 40 + index, "test_at": 60 + index,
                "share_count": None if index % 2 else 1_000_000_000 + index}
        assert (await api_client.put(f"/api/profile/offer/valuations/{company}", json=body)).status_code == 200
    return db_session


async def _job_id(session, key: str) -> int:
    return await session.scalar(select(Job.id).where(Job.req_id == task_req_id(key)))


async def _agent(api_client, path: str, **params):
    response = await api_client.get(f"{PREFIX}{path}", params=params)
    return response, response.json()


def _data(body: dict) -> dict:
    assert body["ok"] is True, body["error"]
    return body["data"]


async def _every_page(api_client, path: str, key: str, **params) -> tuple[list, list[dict]]:
    """Every item of a paged read, and each page's envelope."""
    items: list = []
    pages: list[dict] = []
    cursor = None
    while True:
        _, body = await _agent(api_client, path, **params, **({"cursor": cursor} if cursor else {}))
        items += _data(body)[key]
        pages.append(body)
        cursor = body["meta"]["next_cursor"]
        if cursor is None:
            return items, pages
        assert len(pages) < 50, "the cursor never ends"


async def _keep_back(session, **choices) -> None:
    await set_agent_access(session, AgentAccessConfig(enabled=True, categories=choices))
    await session.commit()


# --- offer.get ---------------------------------------------------------------- #


async def test_the_offer_and_every_valuation_read_as_the_offer_route_reads_them(workspace, api_client):
    dashboard = (await api_client.get("/api/profile/offer")).json()

    valuations, pages = await _every_page(api_client, "/offer", "valuations")

    assert len(pages) > 1, "forty valuations fit one small page; the budget is not exercised"
    assert all(_data(page)["offer"] == dashboard["offer"] for page in pages)
    assert all(_data(page)["valuation_count"] == len(VALUATION_COMPANIES) for page in pages)
    # Each valuation once: a page that repeats one would hide in the mapping below.
    assert len(valuations) == len(VALUATION_COMPANIES)
    assert {item.pop("company"): item for item in valuations} == dashboard["valuations"]
    assert [page["warnings"][0]["code"] for page in pages[:-1]] == ["page_shortened"] * (len(pages) - 1)
    assert pages[-1]["warnings"] == []
    assert pages[0]["meta"]["data_classes"] == ["offer"]


async def test_a_full_tier_page_holds_more_valuations_than_a_small_one(workspace, api_client):
    _, small = await _agent(api_client, "/offer")
    _, full = await _agent(api_client, "/offer", tier="full")

    assert len(_data(full)["valuations"]) > len(_data(small)["valuations"])
    assert len(json.dumps(small["data"], ensure_ascii=False, separators=(",", ":")).encode()) <= 4_100


async def test_a_stored_offer_the_route_cannot_read_reads_as_none_here_too(workspace, api_client):
    await workspace.execute(
        update(AppSetting).where(AppSetting.key == "stock_offer")
        .values(value={**OFFER, "saved_at": "2026-11-10T00:00:00Z", "invented": 1})
    )
    await workspace.commit()

    _, body = await _agent(api_client, "/offer")

    assert (await api_client.get("/api/profile/offer")).json()["offer"] is None
    assert _data(body)["offer"] is None
    assert _data(body)["valuation_count"] == len(VALUATION_COMPANIES)


async def test_a_cursor_from_another_workspace_or_read_is_refused(workspace, api_client):
    _, first = await _agent(api_client, "/offer")
    cursor = first["meta"]["next_cursor"]

    response, body = await _agent(api_client, "/applications", cursor=cursor)

    assert response.status_code == 422
    assert body["error"]["details"] == {"field": "cursor", "reason": "other_request"}


@pytest.mark.parametrize("choice", ["not_shared", "local_only"])
async def test_an_offer_kept_from_assistants_is_refused_with_nothing_of_it(workspace, api_client, choice):
    await _keep_back(workspace, offer=choice)

    response, body = await _agent(api_client, "/offer")

    assert response.status_code == 403
    assert body["ok"] is False and body["data"] is None
    assert body["error"]["code"] == "category_disabled"
    assert body["error"]["details"] == {"category": "offer", "setting": "agent_access.categories.offer"}
    assert "212000" not in response.text and "private-co" not in response.text
    # The pipeline is another category, still shared.
    assert (await _agent(api_client, "/applications"))[1]["ok"] is True


# --- applications.board and applications.calendar ----------------------------- #


async def test_the_board_answers_every_card_the_board_route_does(workspace, api_client):
    dashboard = (await api_client.get("/api/applications")).json()["applications"]

    cards, pages = await _every_page(api_client, "/applications", "applications")

    assert len(pages) > 1, "the board fits one small page; the budget is not exercised"
    assert sorted(cards, key=lambda card: card["job_id"]) == sorted(dashboard, key=lambda card: card["job_id"])
    assert all(_data(page)["total"] == len(dashboard) for page in pages)
    stages = ["saved", "researching", "networking", "applied", "interviewing"]
    assert [card["stage"] for card in cards] == sorted(
        (card["stage"] for card in cards), key=stages.index
    ), "the board is not in the pipeline's order"
    interviewing = next(card for card in cards if card["stage"] == "interviewing")
    assert interviewing["next_interview"]["label"] == "System design with the platform team"


async def test_a_stage_filter_reads_only_that_stage(workspace, api_client):
    cards, _ = await _every_page(api_client, "/applications", "applications", stage="applied")

    assert [card["job_id"] for card in cards] == [await _job_id(workspace, "FOLLOWUP")]


async def test_the_calendar_answers_what_the_calendar_route_does(workspace, api_client):
    now = datetime.now(UTC)
    span = {"start": (now - timedelta(days=7)).isoformat(), "end": (now + timedelta(days=14)).isoformat()}
    dashboard = (await api_client.get("/api/applications/calendar", params=span)).json()["items"]

    items, pages = await _every_page(api_client, "/applications/calendar", "items", **span)

    assert items == dashboard
    assert {item["kind"] for item in items} == {"interview", "step"}
    assert _data(pages[0])["total"] == len(dashboard)


@pytest.mark.parametrize(("start", "end", "reason"), [
    ("2026-11-20T00:00:00+00:00", "2026-11-10T00:00:00+00:00", "before_start"),
    ("2026-11-01T00:00:00+00:00", "2026-12-31T00:00:00+00:00", "span_too_long"),
])
async def test_a_calendar_span_the_route_refuses_is_refused(workspace, api_client, start, end, reason):
    response, body = await _agent(api_client, "/applications/calendar", start=start, end=end)

    assert response.status_code == 422
    assert body["error"]["details"]["reason"] == reason


async def test_a_calendar_bound_without_an_offset_is_invalid(workspace, api_client):
    response, body = await _agent(
        api_client, "/applications/calendar", start="2026-11-01T00:00:00", end="2026-11-08T00:00:00+00:00"
    )

    assert response.status_code == 422
    assert body["error"]["code"] == "invalid_input"


async def test_pursuits_kept_from_assistants_close_the_board_and_the_calendar(workspace, api_client):
    await _keep_back(workspace, private_pursuit="not_shared")
    now = datetime.now(UTC)

    board, board_body = await _agent(api_client, "/applications")
    calendar, calendar_body = await _agent(
        api_client, "/applications/calendar",
        start=(now - timedelta(days=7)).isoformat(), end=(now + timedelta(days=14)).isoformat(),
    )

    for response, body in ((board, board_body), (calendar, calendar_body)):
        assert response.status_code == 403
        assert body["error"]["code"] == "category_disabled"
        assert body["error"]["details"]["category"] == "private_pursuit"
        assert "System design" not in response.text and "thank-you" not in response.text
    assert (await _agent(api_client, "/offer"))[1]["ok"] is True


async def test_a_board_card_leaves_its_posting_out_when_postings_are_not_shared(workspace, api_client):
    shared, _ = await _every_page(api_client, "/applications", "applications", tier="full")
    posting = {"company", "title", "level_band", "posting_status"}
    assert shared and all(posting <= card.keys() for card in shared)
    await _keep_back(workspace, public_posting="not_shared")

    cards, pages = await _every_page(api_client, "/applications", "applications", tier="full")

    assert cards == [{k: v for k, v in card.items() if k not in posting} for card in shared]
    assert pages[0]["meta"]["data_classes"] == ["private_pursuit"]


# --- doctor ------------------------------------------------------------------- #

PLANTED_KEY = "sk-ant-api03-PLANTEDsecretKEY0123456789abcdefXYZ"
PLANTED_PASSWORD = "hunter2-planted-password"
PLANTED_PATH = "/Users/someone-else/private/pgdata"
#: A price-data key's shape, built at run time so the secret scan reads no key in this file.
PRICE_DATA_PLANT = "0123456789abcdef" * 2


async def test_the_doctor_reports_the_status_checks_and_redacts_every_planted_secret(
    workspace, api_client, monkeypatch
):
    planted = get_settings().model_copy(update={
        "anthropic_api_key": PLANTED_KEY,
        "tiingo_api_key": PRICE_DATA_PLANT,
        "database_url_override": f"postgresql+asyncpg://roleband:{PLANTED_PASSWORD}@db.example:5432/roleband",
        "scraper_proxy_url": SecretStr(f"http://proxy-user:{PLANTED_PASSWORD}@proxy.example:8080"),
        "db_pgdata": PLANTED_PATH,
        "cache_dir_override": str(DATA_DIR / "cache"),
        "scraper_user_agent": f"RoleBand probe (token={PLANTED_KEY})",
        "freshness_max_hours": 30,
    })
    # The negative control: the engine really runs with these values.
    assert planted.anthropic_api_key == PLANTED_KEY
    monkeypatch.setattr(agent_router, "get_settings", lambda: planted)

    response, body = await _agent(api_client, "/doctor", tier="full")

    report = _data(body)
    for secret in (PLANTED_KEY, PLANTED_PASSWORD, PLANTED_PATH, "someone-else", PRICE_DATA_PLANT):
        assert secret not in response.text
    settings = {entry["name"]: entry["value"] for entry in report["settings"]}
    assert settings["anthropic_api_key"] == SECRET
    assert settings["tiingo_api_key"] == SECRET
    assert settings["database_url_override"] == SECRET
    assert settings["scraper_proxy_url"] == SECRET
    assert settings["db_pgdata"] == OUTSIDE
    assert settings["cache_dir_override"] == "workspace/cache"
    assert settings["freshness_max_hours"] == 30
    assert "postgres_port" not in settings, "a setting at its default is listed"
    assert report["redacted"] >= 6
    checks = {check["check"]: check for check in report["checks"]}
    assert checks["database"]["state"] == "ok"
    assert checks["agent_access"]["summary"].startswith("reads on, changes off")
    states = [check["state"] for check in report["checks"]]
    assert states == sorted(states, key=["failing", "attention", "ok"].index)
    assert body["meta"]["data_classes"] == ["public_posting"]


async def test_a_small_doctor_cuts_its_settings_and_says_how_to_read_them_all(workspace, api_client, monkeypatch):
    many = get_settings().model_copy(update={
        "scraper_user_agent": "RoleBand " + "x" * 3_000, "embedding_model": "m" * 2_000,
    })
    monkeypatch.setattr(agent_router, "get_settings", lambda: many)

    _, small = await _agent(api_client, "/doctor")
    _, full = await _agent(api_client, "/doctor", tier="full")

    assert _data(small)["continue_with"] == [{"operation": "doctor", "arguments": {"tier": "full"}}]
    assert small["warnings"][0]["code"] == "page_shortened"
    assert len(_data(small)["settings"]) < len(_data(full)["settings"])
    assert _data(full)["continue_with"] == [] and _data(full)["settings_left_out"] == []


async def test_a_setting_too_long_for_the_full_tier_is_shortened_with_a_marker(workspace, api_client, monkeypatch):
    agent = "RoleBand probe/" + "x" * 200_000
    long = get_settings().model_copy(update={"scraper_user_agent": agent})
    monkeypatch.setattr(agent_router, "get_settings", lambda: long)

    response, body = await _agent(api_client, "/doctor", tier="full")

    report = _data(body)
    assert report["settings_shortened"] == ["scraper_user_agent"] and report["settings_left_out"] == []
    settings = {entry["name"]: entry["value"] for entry in report["settings"]}
    shown = settings["scraper_user_agent"]
    marker = f"\u2026 [shortened from {len(agent)} characters]"
    assert shown.endswith(marker)
    assert agent.startswith(shown.removesuffix(marker)) and len(shown) > 1_000, "most of the room shows the value"
    assert len(response.content) < len(agent)
    assert body["warnings"][0]["code"] == "page_shortened"


async def test_a_secret_at_the_cut_of_a_shortened_setting_stays_redacted(workspace, api_client, monkeypatch):
    """Redaction reads the whole value before it is cut: a key that the cut
    would split leaves no part of itself."""

    def doctor(agent: str) -> dict:
        settings = get_settings().model_copy(update={"scraper_user_agent": agent})
        return export.doctor_report(
            {"db": "ok"}, settings=settings, access=AgentAccessConfig(enabled=True), engine_version="0",
            workspace=DATA_DIR, tier="full",
        ).model_dump(mode="json")

    plain = doctor("a" * 200_000)
    kept = len(next(e["value"] for e in plain["settings"] if e["name"] == "scraper_user_agent").split("\u2026")[0])
    # The key straddles where the plain value is cut, with ten of its characters before the cut.
    report = doctor("a" * (kept - 10) + f" token={PLANTED_KEY} " + "b" * 200_000)

    shown = next(entry["value"] for entry in report["settings"] if entry["name"] == "scraper_user_agent")
    assert report["settings_shortened"] == ["scraper_user_agent"]
    assert PLANTED_KEY[:6] not in json.dumps(report)
    assert "token=[" in shown, "the cut lands in the redaction, not in the key"


def _json_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


async def test_a_full_doctor_stays_within_its_budget_and_shortens_only_the_long_setting():
    """A long setting near the edge of the full tier: the names of the settings
    shortened must still fit beside the values, and a short setting is never
    cut to make room for the long one."""
    status = {"db": "ok", "supervisor": {"state": "running"}}
    base = get_settings().model_copy(update={"search_llm_model": "m" * 40, "stale_run_minutes": 12_345})

    def report(length: int) -> dict:
        settings = base.model_copy(update={"scraper_user_agent": "R" + "x" * length})
        return export.doctor_report(
            status, settings=settings, access=AgentAccessConfig(enabled=True), engine_version="0",
            workspace=DATA_DIR, tier="full",
        ).model_dump(mode="json")

    budget = PAGE_BUDGET_BYTES["full"]
    edge = budget - _json_size(report(0)) + 10
    reports = [report(length) for length in range(edge - 200, edge + 40)]
    assert max(_json_size(r) for r in reports) <= budget
    assert {tuple(r["settings_shortened"]) for r in reports} == {(), ("scraper_user_agent",)}
    for r in reports:
        settings = {entry["name"]: entry["value"] for entry in r["settings"]}
        assert settings["search_llm_model"] == "m" * 40 and settings["stale_run_minutes"] == 12_345
        assert r["settings_left_out"] == []


async def test_settings_whose_markers_do_not_fit_are_left_out_by_name_within_the_room():
    """The last resort: with no room for even the markers, settings are left
    out by name, and the names left out take room too."""
    entries = [
        export.DoctorSetting(name=f"setting_{index}", value="v" * (index * 37 % 300)) for index in range(40)
    ]
    names = sum(_json_size(entry.name) + 1 for entry in entries)
    for room in range(names, names + 4_000, 41):
        kept, shortened, left_out = export._fit_full(entries, room)
        used = sum(_json_size(entry.model_dump(mode="json")) + 1 for entry in kept)
        used += sum(_json_size(name) + 1 for name in [*shortened, *left_out])
        assert used <= room, room
        assert {entry.name for entry in kept} | set(left_out) == {entry.name for entry in entries}
        assert set(shortened) <= {entry.name for entry in kept}


@pytest.mark.parametrize(("raw", "kept", "gone"), [
    ("connect to https://user:pa55word@host.example/path", "https://[redacted]@host.example/path", "pa55word"),
    ("GET https://api.example/v1?a=1&api_key=abcd1234efgh&b=2", "&api_key=[redacted]&b=2", "abcd1234efgh"),
    ("Authorization: Bearer abc.def-ghi_jkl", "Authorization: [redacted]", "abc.def-ghi_jkl"),
    ("token ghp_abcdefghijklmnopqrstuvwxyz0123", "token [redacted]", "ghp_abcdefghij"),
    ("read /etc/roleband/secret.env failed", f"read {OUTSIDE} failed", "/etc/roleband"),
    ("data in \\\\nas\\private\\alice\\pgdata", f"data in {OUTSIDE}", "alice"),
    ("data in C:\\Users\\alice\\pgdata", f"data in {OUTSIDE}", "alice"),
    ("GET https://api.example?api_key=prefix@secretsuffix", "?api_key=[redacted]", "secretsuffix"),
    ("GET https://api.example#token=prefix@secretsuffix", "#token=[redacted]", "secretsuffix"),
    ("see https://example.com/docs/a/b for help", "see https://example.com/docs/a/b for help", None),
])
async def test_the_redactor_replaces_each_shape_of_secret_and_keeps_ordinary_text(raw, kept, gone):
    redactor = Redactor(DATA_DIR)

    out = redactor.text(raw)

    assert kept in out
    if gone is None:
        assert out == raw and redactor.count == 0
    else:
        assert gone not in out and redactor.count >= 1


@pytest.mark.parametrize("path", [
    "C:\\Users\\Alice Smith\\private\\pgdata", "/Users/Alice Smith/private/pgdata", "~/Alice Smith/pgdata",
])
async def test_a_path_valued_setting_is_redacted_whole_spaces_included(path):
    redactor = Redactor(DATA_DIR)

    assert redactor.value("db_pgdata", path) == OUTSIDE
    assert redactor.count == 1


async def test_a_path_inside_the_workspace_is_kept_relative_to_it():
    assert Redactor(DATA_DIR).text(f"wrote {DATA_DIR / 'logs' / 'run.log'}") == "wrote workspace/logs/run.log"


# --- context.export ----------------------------------------------------------- #


async def _profile(session, slug: str) -> None:
    now = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    session.add(CompanyProfile(slug=slug, display_name=slug.title()))
    await session.flush()
    for field, value, source in (("is_public", True, "sec_edgar"), ("ticker", "SYN", "sec_edgar"),
                                 ("headcount", 4200, "estimated")):
        await profile_store.record_fact(session, slug, field, value, source, observed_at=now)
    await profile_store.resolve_and_materialize(session, slug, now=now)
    await session.commit()


async def _export(api_client, opportunity_id: int, **params) -> tuple[str, dict, list[dict]]:
    """The packet joined from every part, the manifest, and each part's envelope."""
    parts: list[dict] = []
    text = ""
    arguments: dict = {"tier": "full", **params}
    while True:
        _, body = await _agent(api_client, f"/opportunities/{opportunity_id}/context", **arguments)
        data = _data(body)
        assert data["packet_offset"] == len(text)
        text += data["packet"]
        parts.append(body)
        if not data["continue_with"]:
            return text, data["manifest"], parts
        follow = data["continue_with"][0]
        assert follow["operation"] == "context.export"
        arguments = {key: value for key, value in follow["arguments"].items() if key != "opportunity_id"}
        assert len(parts) < 50, "the parts never end"


async def test_an_export_of_unchanged_inputs_is_byte_identical_and_its_hashes_prove_it(workspace, api_client):
    job_id = await _job_id(workspace, "INTERVIEW")
    await _profile(workspace, (await workspace.get(Job, job_id)).company)

    first, manifest, _ = await _export(api_client, job_id)
    # The posting is seen again by a later scan; its content does not move.
    await workspace.execute(update(Job).where(Job.id == job_id).values(last_seen=datetime.now(UTC) + timedelta(hours=1)))
    await workspace.commit()
    second, again, _ = await _export(api_client, job_id)

    assert second == first
    assert again["packet_sha256"] == manifest["packet_sha256"] == hashlib.sha256(first.encode()).hexdigest()
    assert manifest["packet_bytes"] == len(first.encode()) and manifest["packet_chars"] == len(first)
    posting_stamps = {c["name"]: c for c in again["components"]}["posting"]["source_timestamps"]
    assert posting_stamps["last_seen"] != {c["name"]: c for c in manifest["components"]}["posting"][
        "source_timestamps"]["last_seen"]
    packet = json.loads(first)
    assert canonical(packet) == first
    for component in manifest["components"]:
        assert component["sha256"] == hashlib.sha256(canonical(packet["components"][component["name"]]).encode()).hexdigest()
    assert [c["name"] for c in manifest["components"]] == ["posting", "pay", "company", "pursuit"]
    assert manifest["left_out"] == []


async def test_an_export_carries_what_the_dashboard_shows_of_the_posting_its_pay_and_its_company(
    workspace, api_client
):
    job_id = await _job_id(workspace, "INTERVIEW")
    job = await workspace.get(Job, job_id)
    await _profile(workspace, job.company)

    text, manifest, _ = await _export(api_client, job_id)
    packet = json.loads(text)["components"]

    _, detail = await _agent(api_client, f"/opportunities/{job_id}", view="detail", tier="full")
    shown = _data(detail)
    assert packet["posting"]["description"] == shown["description"]
    assert packet["posting"]["description_sections"] == shown["description_sections"]
    assert packet["posting"]["title"] == shown["title"]
    for field in ("employer_stated_pay", "estimated_total_comp", "estimated_base", "estimate_component"):
        assert packet["pay"][field] == shown[field]
    assert packet["pursuit"]["pursuit"] == shown["pursuit"]
    profile = (await api_client.get(f"/api/company-profiles/{job.company}")).json()
    stamps = {c["name"]: c["source_timestamps"] for c in manifest["components"]}["company"]
    for field, value in packet["company"]["fields"].items():
        assert value == {
            "value": profile["fields"][field]["value"], "source": profile["fields"][field]["source"],
            "answered_by": None,
        }
        stated, observed = profile["fields"][field]["observed_at"], stamps[f"observed_at:{field}"]
        assert (observed is None) == (stated is None)
        if stated is not None:
            assert datetime.fromisoformat(observed) == datetime.fromisoformat(stated)


async def test_a_fact_confirmed_again_moves_the_manifest_not_the_packet(workspace, api_client):
    job_id = await _job_id(workspace, "INTERVIEW")
    slug = (await workspace.get(Job, job_id)).company
    await _profile(workspace, slug)
    first, manifest, _ = await _export(api_client, job_id)

    # The source states the same headcount again a week later.
    profile = await workspace.get(CompanyProfile, slug)
    meta = dict(profile.field_meta)
    meta["headcount"] = {**meta["headcount"], "observed_at": "2026-11-08T12:00:00+00:00"}
    await workspace.execute(update(CompanyProfile).where(CompanyProfile.slug == slug).values(field_meta=meta))
    await workspace.commit()
    second, again, _ = await _export(api_client, job_id)

    assert second == first
    stamps = [{c["name"]: c["source_timestamps"] for c in m["components"]}["company"] for m in (manifest, again)]
    assert stamps[0]["observed_at:headcount"] != stamps[1]["observed_at:headcount"]


async def test_a_part_of_a_packet_that_changed_since_is_refused(workspace, api_client):
    job_id = await _job_id(workspace, "INTERVIEW")
    await workspace.execute(update(Job).where(Job.id == job_id).values(description_text="Long text. " * 3_000))
    await workspace.commit()
    _, first = await _agent(api_client, f"/opportunities/{job_id}/context", tier="small")
    arguments = _data(first)["continue_with"][0]["arguments"]
    assert arguments["packet_sha256"] == _data(first)["manifest"]["packet_sha256"]
    follow = {key: value for key, value in arguments.items() if key != "opportunity_id"}
    # Unchanged, the next part reads.
    assert (await _agent(api_client, f"/opportunities/{job_id}/context", **follow))[1]["ok"] is True

    await workspace.execute(update(Job).where(Job.id == job_id).values(description_text="Other text. " * 3_000))
    await workspace.commit()
    response, body = await _agent(api_client, f"/opportunities/{job_id}/context", **follow)

    assert response.status_code == 409 and body["error"]["code"] == "revision_conflict"
    assert body["error"]["details"]["expected_packet_sha256"] == follow["packet_sha256"]
    assert body["error"]["next_actions"][0]["arguments"] == {"opportunity_id": job_id, "tier": "small"}


async def test_a_later_part_without_its_packet_hash_is_refused_before_it_is_read(workspace, api_client):
    job_id = await _job_id(workspace, "INTERVIEW")

    response, body = await _agent(api_client, f"/opportunities/{job_id}/context", tier="small", packet_from=10)

    assert body["ok"] is False and body["error"]["code"] == "invalid_input", body
    assert (await _agent(api_client, f"/opportunities/{job_id}/context", tier="small", packet_from=0))[1]["ok"]


async def test_an_export_changes_when_an_input_changes_and_only_that_component_moves(workspace, api_client):
    job_id = await _job_id(workspace, "INTERVIEW")
    before, manifest, _ = await _export(api_client, job_id)

    await workspace.execute(update(Job).where(Job.id == job_id).values(description_text="A rewritten description."))
    await workspace.commit()
    after, moved, _ = await _export(api_client, job_id)

    assert after != before and moved["packet_sha256"] != manifest["packet_sha256"]
    hashes = {c["name"]: c["sha256"] for c in manifest["components"]}
    changed = [c["name"] for c in moved["components"] if c["sha256"] != hashes[c["name"]]]
    assert changed == ["posting"]


async def test_pursuits_kept_from_assistants_are_left_out_of_the_export(workspace, api_client):
    job_id = await _job_id(workspace, "INTERVIEW")
    shared, with_pursuit, _ = await _export(api_client, job_id)
    await _keep_back(workspace, private_pursuit="not_shared")

    kept, without, _ = await _export(api_client, job_id)

    assert "Onsite loop booked" in shared
    assert "Onsite loop booked" not in kept and "Prepare two incident" not in kept
    assert "pursuit" not in json.loads(kept)["components"]
    assert without["left_out"] == ["private_pursuit"]
    assert [c["name"] for c in without["components"]] == ["posting", "pay", "company"]
    assert without["packet_sha256"] != with_pursuit["packet_sha256"]


async def test_market_statistics_not_shared_leave_the_estimates_out_of_the_export(workspace, api_client):
    job_id = await _job_id(workspace, "INTERVIEW")
    shared, _, _ = await _export(api_client, job_id)
    pay = json.loads(shared)["components"]["pay"]
    assert pay["estimated_total_comp"] is not None and pay["estimate_sources"]
    await _keep_back(workspace, market_statistic="not_shared", private_pursuit="not_shared")

    kept, manifest, _ = await _export(api_client, job_id)

    components = json.loads(kept)["components"]
    assert components["pay"] == {"employer_stated_pay": pay["employer_stated_pay"]}
    # The company's facts are market statistics, as companies.get answers them.
    assert "company" in json.loads(shared)["components"]
    assert "company" not in components
    assert manifest["left_out"] == ["market_statistic", "private_pursuit"]
    stamps = {c["name"]: c["source_timestamps"] for c in manifest["components"]}
    assert list(stamps) == ["posting", "pay"]
    assert list(stamps["pay"]) == ["stated_pay_read_at"]


async def test_a_packet_longer_than_the_budget_comes_in_parts_that_join_to_its_bytes(workspace, api_client):
    job_id = await _job_id(workspace, "INTERVIEW")
    await workspace.execute(update(Job).where(Job.id == job_id).values(
        description_text=('A "quoted" paragraph with é and 漢字.\n' * 1_200)
    ))
    await workspace.commit()

    small, manifest, parts = await _export(api_client, job_id, tier="small")
    whole, _, full_parts = await _export(api_client, job_id, tier="full")

    assert len(parts) > len(full_parts) >= 2
    assert small == whole
    assert hashlib.sha256(small.encode()).hexdigest() == manifest["packet_sha256"]
    for part in parts:
        assert len(json.dumps(part["data"], ensure_ascii=False, separators=(",", ":")).encode()) <= 15_000
    assert parts[0]["warnings"][0]["code"] == "page_shortened"
    assert parts[-1]["warnings"] == []


async def test_an_export_of_an_unknown_opportunity_is_not_found(workspace, api_client):
    response, body = await _agent(api_client, "/opportunities/987654/context")

    assert response.status_code == 404
    assert body["error"]["code"] == "not_found"


# --- the schema namespace ----------------------------------------------------- #


async def test_no_two_models_share_a_name_in_the_api_schema():
    """Agent shapes and the dashboard's share one OpenAPI namespace. Two models
    of one name are both renamed to their module paths, which renames a type
    the dashboard imports by name and breaks its build, not this suite."""
    from tracker.api.app import app

    names = app.openapi()["components"]["schemas"]

    assert [name for name in names if name.startswith("tracker__")] == []
    assert {"ApplicationCard", "CalendarInterview", "OfferInputs", "BoardCard", "KeptOfferInputs"} <= set(names)


async def test_the_full_doctor_cuts_to_the_longest_length_that_fits_even_past_a_whole_value():
    """Raising the length past a value's own size keeps it whole and drops its
    marker, so a longer cut can fit where a shorter one did not. Each room
    gets the longest cut that fits, measured against every length in turn."""
    entries = [export.DoctorSetting(name="a", value="a" * 100), export.DoctorSetting(name="b", value="b" * 1000)]

    def used(cap: int) -> int:
        kept = [export._shorten(entry, cap) for entry in entries]
        names = [entry.name for entry, held in zip(entries, kept, strict=True) if held is not entry]
        return sum(_json_size(h.model_dump(mode="json")) + 1 for h in kept) + sum(_json_size(n) + 1 for n in names)

    sizes = {cap: used(cap) for cap in range(0, 1_010)}
    whole_a_fits_only_past_its_size = 0
    for room in range(150, 1_200, 3):
        fitting = {cap for cap, size in sizes.items() if size <= room}
        if not fitting:
            continue
        best = max(fitting)
        if any(cap + 1 not in fitting for cap in fitting if cap < best):
            whole_a_fits_only_past_its_size += 1
        kept, shortened, left_out = export._fit_full(entries, room)
        assert kept == [export._shorten(entry, best) for entry in entries], room
        assert left_out == []
    assert whole_a_fits_only_past_its_size, "the sweep reaches a room where the cut is not monotonic"
