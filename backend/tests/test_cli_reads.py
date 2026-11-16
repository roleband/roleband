"""The agent reads, through the `roleband` command.

`test_agent_reads.py` holds each read to its owner over HTTP. These
run the generated commands as a process against a real engine on a seeded
scratch database: each command's data is the engine's own answer on the same
route, so a command that built the wrong request (a field lost, a flag sent
as the wrong name, a path argument misplaced) fails here. They also hold the
exit codes an agent branches on, and that an excerpt's `continue_with` is a
call the command line can make as given, until the whole description is read.
"""

from __future__ import annotations

import asyncio
import http.client
import json
from urllib.parse import urlencode

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests import test_cli
from tests.test_cli import cli
from tracker.agents.operations.opportunities import DETAIL_BUDGET_BYTES
from tracker.api.agent_operations import PREFIX
from tracker.db.models import Job, Pursuit

#: The scratch home, the throwaway database and the engine of the client's own tests.
home = test_cli.home
engine_database = test_cli.engine_database
engine = test_cli.engine

_SENTENCE = 'Ship "the platform" — résumé reviews, 東京 & 5\\6 rollouts\n'


def _db(running, work):
    """Run `work` on the engine's database in one committed session."""

    async def go():
        database = create_async_engine(running.database_url)
        try:
            async with AsyncSession(database, expire_on_commit=False) as session:
                result = await work(session)
                await session.commit()
                return result
        finally:
            await database.dispose()

    return asyncio.run(go())


@pytest.fixture
def seeded(engine):
    from scripts.seed_synthetic import seed
    from tracker.agents.config import AgentAccessConfig, set_agent_access

    async def prepare(session: AsyncSession) -> None:
        await seed(session, 12, seed_value=1, derived=False, agent_tasks=True)
        await set_agent_access(session, AgentAccessConfig(enabled=True, allow_writes=False))

    _db(engine, prepare)
    return engine


def _engine_data(running, path: str, **params) -> dict:
    """The engine's own answer on a route, as the command must reproduce it."""
    connection = http.client.HTTPConnection("127.0.0.1", running.port, timeout=30)
    query = f"?{urlencode(params)}" if params else ""
    connection.request("GET", f"{PREFIX}{path}{query}")
    response = connection.getresponse()
    body = json.loads(response.read())
    assert body["ok"] is True, body
    return body["data"]


def _command(home, *args: str) -> dict:
    result = cli(home, *args, "--json")
    assert result.status == 0, result
    assert result.stderr == ""
    return result.envelope


async def _pursued_ids(session: AsyncSession) -> list[int]:
    return list((await session.scalars(select(Pursuit.job_id).order_by(Pursuit.job_id))).all())


def test_every_read_answers_through_its_command_as_the_engine_does(home, seeded):
    home.contexts(current="dev", dev={"url": seeded.url})
    pursued = _db(seeded, _pursued_ids)
    assert len(pursued) >= 4
    job_id = pursued[0]

    radar = _command(home, "radar", "summary")
    assert radar["operation"] == "radar.summary"
    assert radar["data"] == _engine_data(seeded, "/radar/summary")
    assert radar["data"]["active_pursuits"] == len(pursued)

    for view in ("summary", "detail", "evidence"):
        got = _command(home, "opportunities", "get", str(job_id), "--view", view)
        assert got["operation"] == "opportunities.get"
        assert got["data"]["view"] == view
        assert got["data"] == _engine_data(seeded, f"/opportunities/{job_id}", view=view)

    history = _command(home, "opportunities", "history", str(job_id))
    assert history["operation"] == "opportunities.history"
    assert history["data"] == _engine_data(seeded, f"/opportunities/{job_id}/history")

    one = _command(home, "pursuits", "get", str(job_id))
    assert one["operation"] == "pursuits.get"
    assert one["data"] == _engine_data(seeded, f"/pursuits/{job_id}")
    assert one["data"]["opportunity_id"] == job_id and one["data"]["revision"] >= 1

    contract = _command(home, "recipes", "contract", "get")
    assert contract["operation"] == "recipes.contract.get"
    assert contract["data"] == _engine_data(seeded, "/recipes/contract")


def test_pursuit_pages_follow_their_cursor_on_the_command_line(home, seeded):
    home.contexts(current="dev", dev={"url": seeded.url})
    whole = _command(home, "pursuits", "list", "--limit", "100")["data"]["items"]
    assert len(whole) > 2

    seen: list[dict] = []
    cursor: str | None = None
    while True:
        page = _command(home, "pursuits", "list", "--limit", "2", *(["--cursor", cursor] if cursor else []))
        seen.extend(page["data"]["items"])
        cursor = page["meta"]["next_cursor"]
        if cursor is None:
            break

    assert seen == whole
    stage = whole[0]["stage"]
    staged = _command(home, "pursuits", "list", "--stage", stage)["data"]["items"]
    assert staged and {item["stage"] for item in staged} == {stage}
    # A cursor read with another stage is refused, not silently restarted.
    first = _command(home, "pursuits", "list", "--limit", "1")
    other = next(item["stage"] for item in whole if item["stage"] != stage)
    refused = cli(home, "pursuits", "list", "--stage", other, "--cursor", first["meta"]["next_cursor"], "--json")
    assert refused.status == 2, refused
    assert refused.envelope["error"]["details"] == {"field": "cursor", "reason": "other_filters"}


def test_an_excerpt_continues_with_commands_that_read_the_whole_description(home, seeded):
    home.contexts(current="dev", dev={"url": seeded.url})
    job_id = _db(seeded, _pursued_ids)[0]
    text = _SENTENCE * 900

    async def lengthen(session: AsyncSession) -> None:
        await session.execute(update(Job).where(Job.id == job_id).values(description_text=text))

    _db(seeded, lengthen)

    first = cli(home, "opportunities", "get", str(job_id), "--view", "detail", "--json")
    assert first.status == 0, first
    pages = [first.envelope]
    assert pages[0]["meta"]["truncated"] is True
    assert [w["code"] for w in pages[0]["warnings"]] == ["truncated"]
    while calls := [c for c in pages[-1]["data"]["excerpt"]["continue_with"] if c["operation"] == "opportunities.get"]:
        assert len(pages) < 20
        arguments = dict(calls[0]["arguments"])
        # The call as given: the id is the path argument, every other key a flag.
        argv = [str(arguments.pop("opportunity_id"))]
        for key, value in arguments.items():
            argv += [f"--{key.replace('_', '-')}", str(value)]
        pages.append(_command(home, "opportunities", "get", *argv))

    assert len(pages) > 2
    assert "".join(page["data"]["description"] for page in pages) == text
    for page in pages:
        data = json.dumps(page["data"], ensure_ascii=False, separators=(",", ":")).encode()
        assert len(data) <= DETAIL_BUDGET_BYTES["small"]


def test_a_summary_names_the_read_that_gives_the_postings_text(home, seeded):
    """`opportunities get ID` is the facts alone; following its `continue_with`
    as given reads the description, and a posting with no text names nothing."""
    home.contexts(current="dev", dev={"url": seeded.url})
    job_id, other = _db(seeded, _pursued_ids)[:2]
    text = "Lead the payments platform.\n" * 3

    async def describe(session: AsyncSession) -> None:
        await session.execute(update(Job).where(Job.id == job_id).values(description_text=text))
        await session.execute(
            update(Job).where(Job.id == other).values(description_text=None, description_sections=[])
        )

    _db(seeded, describe)

    summary = _command(home, "opportunities", "get", str(job_id))["data"]
    assert summary["view"] == "summary" and "description" not in summary
    [step] = summary["continue_with"]
    assert step["operation"] == "opportunities.get"
    arguments = dict(step["arguments"])
    argv = [str(arguments.pop("opportunity_id"))]
    for key, value in arguments.items():
        argv += [f"--{key.replace('_', '-')}", str(value)]
    detail = _command(home, "opportunities", "get", *argv)["data"]
    assert detail["view"] == "detail" and detail["description"] == text

    assert _command(home, "opportunities", "get", str(other))["data"]["continue_with"] == []


def test_the_reads_branch_on_their_exit_codes(home, seeded):
    home.contexts(current="dev", dev={"url": seeded.url})

    for argv in (("opportunities", "get", "999999999"), ("opportunities", "history", "999999999"),
                 ("pursuits", "get", "999999999")):
        missing = cli(home, *argv, "--json")
        assert missing.status == 5, missing
        assert missing.envelope["error"]["code"] == "not_found"

    bad_view = cli(home, "opportunities", "get", "1", "--view", "summary", "--description-from", "3", "--json")
    assert bad_view.status == 2, bad_view
    assert bad_view.envelope["error"]["details"]["field"] == "description_from"

    # A loopback address is no public page: refused before anything is fetched.
    blocked = cli(home, "sources", "inspect", "--url", "http://127.0.0.1:9/careers", "--json")
    assert blocked.status == 2, blocked
    assert blocked.envelope["error"]["details"] == {"field": "url", "reason": "blocked_destination"}

    # The person turns agent access off: every one of these reads is refused.
    assert seeded.put_json("/api/intelligence/agents", {"enabled": False, "allow_writes": False}) == 200
    for argv in (("radar", "summary"), ("opportunities", "get", "1"), ("opportunities", "history", "1"),
                 ("pursuits", "list"), ("pursuits", "get", "1"), ("recipes", "contract", "get"),
                 ("sources", "inspect", "--url", "https://example.com/")):
        refused = cli(home, *argv, "--json")
        assert refused.status == 4, (argv, refused)
        assert refused.envelope["error"]["code"] == "access_disabled"
