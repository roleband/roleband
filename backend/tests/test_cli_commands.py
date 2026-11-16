"""`roleband <resource> <verb>`: every operation is a command, built from the bundle.

No operation has code of its own in the client. These hold that each catalog
operation comes out as a command with its fields as arguments, that a bundle
the client cannot lay out is refused rather than half-built, that a command
sends exactly the input it was given (`--input`, with flags adding only the
fields it leaves out), and
that help reads the bundle without loading the engine's models or an HTTP
library. The search and vocabulary commands also run end to end against a
real engine on a seeded scratch database.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests import test_cli
from tests.test_cli import BACKEND, Reply, Stub, _envelope, cli
from tracker.agents.operations.catalog import CATALOG
from tracker.cli import commands
from tracker.cli.errors import ClientError
from tracker.cli.main import BUNDLE, build_parser

#: The scratch home, the throwaway database and the engine of the client's own tests.
home = test_cli.home
engine_database = test_cli.engine_database
engine = test_cli.engine

def _bundle() -> dict:
    return json.loads(BUNDLE.read_text(encoding="utf-8"))


def _sample(field: commands.Field) -> str:
    if field.choices:
        return field.choices[0]
    return "1" if field.kind in ("integer", "number") else "x"


# --------------------------------------------------------------------------- #
# Every operation is a command
# --------------------------------------------------------------------------- #


def test_every_catalog_operation_is_a_command():
    parser = build_parser()
    built = {command.operation: command for command in commands.build(_bundle())}
    for descriptor in CATALOG:
        if descriptor.id in commands.HANDSHAKE:
            continue
        command = built.get(descriptor.id)
        assert command is not None, f"{descriptor.id} has no command"
        args = parser.parse_args([*command.words, *(_sample(field) for field in command.positional)])
        assert args.generated.operation == descriptor.id
        # Every field the operation requires can be given: as an argument, a
        # flag, or (for a nested one) through --input.
        schema = descriptor.input.model_json_schema()
        givable = {field.name for field in (*command.positional, *command.flags)} | set(command.input_only)
        assert set(schema.get("required", ())) <= givable, descriptor.id
    assert set(built) == {descriptor.id for descriptor in CATALOG} - commands.HANDSHAKE


def test_search_and_vocabulary_read_as_their_resource_and_verb():
    built = {command.operation: command for command in commands.build(_bundle())}
    search = built["opportunities.search"]
    assert search.words == ("opportunities", "search")
    assert {field.option for field in search.flags} >= {
        "--query", "--company", "--level-band", "--location", "--base-pay-min", "--saved-only", "--cursor", "--tier",
    }
    assert next(field for field in search.flags if field.name == "company").is_list
    assert next(field for field in search.flags if field.name == "sort").choices[0] == "best_match"
    assert built["vocabulary.list"].words == ("vocabulary", "list")


def _with(bundle: dict, operation: str, route: dict | None, **entry: object) -> dict:
    changed = copy.deepcopy(bundle)
    template = next(item for item in changed["operations"] if item["operation"] == "vocabulary.list")
    changed["operations"].append({**copy.deepcopy(template), "operation": operation, **entry})
    if route is not None:
        changed["routes"][operation] = route
    return changed


@pytest.mark.parametrize(
    ("operation", "route", "reason"),
    [
        ("widgets.list", None, "has no route"),
        ("status.check", {"method": "GET", "path": "/api/agent/v1/status/check"}, "already a command"),
        ("vocabulary.list.more", {"method": "GET", "path": "/api/agent/v1/v/more"}, "both a command and a group"),
        ("widgets.list", {"method": "GET", "path": "/elsewhere/widgets"}, "not an agent route"),
        ("widgets.get", {"method": "GET", "path": "/api/agent/v1/widgets/{widget_id}"}, "which its input does not"),
    ],
    ids=["no-route", "handshake-word", "group-and-leaf", "foreign-path", "unknown-path-field"],
)
def test_a_bundle_that_cannot_be_laid_out_is_refused(operation, route, reason):
    with pytest.raises(ValueError, match=reason):
        commands.build(_with(_bundle(), operation, route))


def test_a_field_named_like_a_client_option_is_refused():
    bundle = _with(_bundle(), "widgets.list", {"method": "GET", "path": "/api/agent/v1/widgets"})
    bundle["operations"][-1]["input_schema"] = {
        "type": "object", "properties": {"context": {"type": "string"}}, "additionalProperties": False,
    }
    with pytest.raises(ValueError, match="named like a client option"):
        commands.build(bundle)


def _without_routes(bundle: dict) -> None:
    del bundle["routes"]["vocabulary.list"]


def _without_operations(bundle: dict) -> None:
    del bundle["operations"]


def _with_a_nameless_operation(bundle: dict) -> None:
    bundle["operations"].append({"summary": "no name"})


@pytest.mark.parametrize("damage", [_without_routes, _without_operations, _with_a_nameless_operation])
@pytest.mark.parametrize("argv", [["vocabulary", "list", "--kind", "location"], ["vocabulary", "list", "--help"]])
def test_a_damaged_bundle_is_an_internal_error_not_a_traceback(tmp_path, monkeypatch, damage, argv):
    from io import StringIO

    from tracker.cli.main import run

    damaged = _bundle()
    damage(damaged)
    path = tmp_path / "operations.json"
    path.write_text(json.dumps(damaged), encoding="utf-8")
    monkeypatch.setattr("tracker.cli.main.BUNDLE", path)
    monkeypatch.setattr("tracker.cli.main._BUNDLE_CACHE", [])
    out = StringIO()
    status = run([*argv, "--json"], stdout=out, stderr=StringIO(), environ={})
    assert status == 1
    assert json.loads(out.getvalue())["error"]["code"] == "internal_error"


# --------------------------------------------------------------------------- #
# A request carries exactly what it was given
# --------------------------------------------------------------------------- #

_PAGE = {"total": 0, "count": 0, "sort": "newest", "order": "desc", "filters": {}, "columns": [], "rows": []}


def _query(path: str) -> dict:
    return parse_qs(urlsplit(path).query, keep_blank_values=True)


def test_flags_become_the_operations_query(home):
    with Stub(Reply(200, _envelope("opportunities.search", data=_PAGE))) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, "opportunities", "search", "--company", "acme", "--company", "Big Co",
                     "--saved-only", "--limit", "5", "--json")
    assert result.status == 0, result
    assert len(stub.requests) == 1
    assert urlsplit(stub.requests[0]).path == "/api/agent/v1/opportunities"
    assert _query(stub.requests[0]) == {"company": ["acme", "Big Co"], "saved_only": ["true"], "limit": ["5"]}


def test_input_from_a_file_sends_the_same_request(home, tmp_path):
    document = tmp_path / "search.json"
    document.write_text(json.dumps({"company": ["acme", "Big Co"], "saved_only": True, "limit": 5}))
    with Stub(Reply(200, _envelope("opportunities.search", data=_PAGE))) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, "opportunities", "search", "--input", f"@{document}", "--json")
    assert result.status == 0, result
    assert _query(stub.requests[0]) == {"company": ["acme", "Big Co"], "saved_only": ["true"], "limit": ["5"]}


def _piped(home, *args: str, stdin) -> test_cli.Result:
    """The command with `stdin` as its standard input: bytes in a pipe that
    then closes, `subprocess.DEVNULL`, or `open` for a pipe nothing writes to
    and that stays open until the command has ended."""
    command = [sys.executable, "-m", "tracker.cli", *args]
    if stdin == "open":
        process = subprocess.Popen(command, cwd=home.root, env=test_cli._env(home), stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            process.wait(timeout=30)
        finally:
            process.stdin.close()
        out, err = process.stdout.read(), process.stderr.read()
        process.stdout.close()
        process.stderr.close()
        return test_cli.Result(process.returncode, out.decode(), err.decode())
    pipe = {"input": stdin} if isinstance(stdin, bytes) else {"stdin": stdin}
    done = subprocess.run(command, cwd=home.root, env=test_cli._env(home), capture_output=True, timeout=30, **pipe)
    return test_cli.Result(done.returncode, done.stdout.decode(), done.stderr.decode())


@pytest.mark.skipif(sys.platform == "win32", reason="Windows pipes cannot be polled, so piped data runs as given")
@pytest.mark.parametrize("args", [
    ("opportunities", "search", "--json"),
    ("opportunities", "get", "--json"),
])
@pytest.mark.parametrize("lead", [b"", b" " * 9000], ids=["at-once", "after-whitespace"])
def test_data_piped_without_input_dash_is_refused_and_asks_no_engine(home, args, lead):
    """`echo '{...}' | roleband opportunities search` would otherwise answer every
    role, the filters silently dropped; a piped id would fail as a missing argument.
    Whitespace longer than one read before the data is still read past."""
    piped = lead + b'{"location": ["New York, NY"], "opportunity_id": 3}\n'
    with Stub(Reply(200, _envelope("opportunities.search", data=_PAGE))) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        refused = _piped(home, *args, stdin=piped)
    assert refused.status == 2, refused
    error = refused.envelope["error"]
    assert error["code"] == "invalid_arguments"
    assert "add --input - to read it" in error["message"]
    assert stub.requests == []


@pytest.mark.skipif(sys.platform == "win32", reason="Windows pipes cannot be polled, so piped data runs as given")
def test_blank_input_past_the_input_limit_is_refused_undecided(home, tmp_path):
    """The scan is bounded; a redirected file whose data starts after more
    blank bytes than any --input accepts is refused, never run unfiltered."""
    from tracker.cli.commands import MAX_INPUT_BYTES

    redirected = tmp_path / "padded.json"
    redirected.write_bytes(b" " * (MAX_INPUT_BYTES + 8192) + b'{"location": ["New York, NY"]}')
    with Stub(Reply(200, _envelope("opportunities.search", data=_PAGE))) as stub, redirected.open("rb") as handle:
        home.contexts(current="dev", dev={"url": stub.url})
        refused = _piped(home, "opportunities", "search", "--json", stdin=handle)
    assert refused.status == 2, refused
    assert refused.envelope["error"]["code"] == "invalid_arguments"
    assert stub.requests == []


@pytest.mark.parametrize("stdin", [b"", b"\n  \n", subprocess.DEVNULL, "open"],
                         ids=["empty-pipe", "blank-lines", "dev-null", "open-pipe-never-written"])
def test_a_standard_input_with_no_data_runs_the_command(home, stdin):
    """Agent hosts start commands with each of these; none holds input, so the search runs."""
    with Stub(Reply(200, _envelope("opportunities.search", data=_PAGE))) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        ran = _piped(home, "opportunities", "search", "--company", "acme", "--json", stdin=stdin)
    assert ran.status == 0, ran
    assert len(stub.requests) == 1 and _query(stub.requests[0]) == {"company": ["acme"]}


def test_data_piped_with_input_dash_is_the_input(home):
    with Stub(Reply(200, _envelope("opportunities.search", data=_PAGE))) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        ran = _piped(home, "opportunities", "search", "--input", "-", "--json", stdin=b'{"company": ["acme"]}')
    assert ran.status == 0, ran
    assert _query(stub.requests[0]) == {"company": ["acme"]}


def test_flags_add_the_fields_input_leaves_out_and_a_field_given_twice_is_refused(home, tmp_path):
    document = tmp_path / "search.json"
    document.write_text(json.dumps({"company": ["acme"], "limit": 5}))
    with Stub(Reply(200, _envelope("opportunities.search", data=_PAGE))) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        merged = cli(home, "opportunities", "search", "--input", f"@{document}", "--saved-only", "--json")
        overlapping = cli(home, "opportunities", "search", "--input", f"@{document}", "--company", "Big Co", "--json")
        # The same value twice is refused too: which one counts is never a question the caller has to ask.
        repeated = cli(home, "opportunities", "search", "--limit", "5", "--input", f"@{document}", "--json")
    assert merged.status == 0, merged
    assert _query(stub.requests[0]) == {"company": ["acme"], "limit": ["5"], "saved_only": ["true"]}
    for refused, field in ((overlapping, "company"), (repeated, "limit")):
        assert refused.status == 2, refused
        error = refused.envelope["error"]
        assert error["code"] == "invalid_arguments"
        assert f"--{field} and --input both give {field}" in error["message"]
        assert error["details"]["fields"] == [field]
    assert len(stub.requests) == 1


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("opportunities", "search", "--input", "search.json"), "@FILE"),
        (("opportunities", "search", "--limit", "many"), "invalid int"),
        (("opportunities", "search", "--sort", "relevance"), "invalid choice"),
        (("opportunities", "search", "--keyword", "x"), "unrecognized"),
        (("vocabulary", "list"), "--kind is required"),
        (("opportunities",), "Name a command after 'opportunities'"),
    ],
    ids=["input-without-at", "not-an-int", "unknown-sort", "unknown-flag", "missing-kind", "group-only"],
)
def test_a_command_refused_before_sending_asks_no_engine(home, args, message):
    with Stub(Reply(200, _envelope("opportunities.search", data=_PAGE))) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, *args, "--json")
    assert result.status == 2, result
    body = result.envelope
    assert body["error"]["code"] == "invalid_arguments"
    assert message in body["error"]["message"]
    assert stub.requests == []
    if args[0] == "opportunities" and len(args) > 1:
        assert body["operation"] == "opportunities.search"


def test_a_global_option_reads_the_same_after_any_word(home):
    with Stub(Reply(200, _envelope("opportunities.search", data=_PAGE))) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        for args in (("--json", "opportunities", "search"), ("opportunities", "--json", "search"),
                     ("opportunities", "search", "--json")):
            result = cli(home, *args)
            assert result.status == 0 and result.envelope["operation"] == "opportunities.search", (args, result)
        clash = cli(home, "opportunities", "--format", "json", "search", "--format", "human")
    assert clash.status == 2
    assert clash.envelope["error"]["message"] == "--format is given twice with different values"
    assert len(stub.requests) == 3


def test_a_parse_failure_names_the_command_not_a_word_in_a_value(home):
    result = cli(home, "opportunities", "search", "--query", "status", "--bogus", "--json")
    assert result.status == 2
    assert result.envelope["operation"] == "opportunities.search"


def test_an_input_document_must_be_one_object_with_unique_keys(tmp_path):
    for text, problem in (('["a"]', "not a JSON object"), ('{"a": 1, "a": 2}', "unique keys"), ("{", "unique keys")):
        path = tmp_path / "input.json"
        path.write_text(text)
        with pytest.raises(ClientError, match=problem):
            commands.read_input(f"@{path}")


def _command(method: str, path: str, properties: dict, required: tuple[str, ...] = ()) -> commands.Command:
    bundle = _with(_bundle(), "widgets.get", {"method": method, "path": path})
    bundle["operations"][-1]["input_schema"] = {
        "type": "object", "properties": properties, "required": list(required), "additionalProperties": False,
    }
    return next(command for command in commands.build(bundle) if command.operation == "widgets.get")


def _widget_parser():
    properties = {"widget_id": {"type": "string"}, "view": {"enum": ["summary", "detail"], "type": "string"}}
    bundle = _with(_bundle(), "widgets.get", {"method": "GET", "path": "/api/agent/v1/widgets/{widget_id}"})
    bundle["operations"][-1]["input_schema"] = {
        "type": "object", "properties": properties, "required": ["widget_id"], "additionalProperties": False,
    }
    return build_parser(bundle)


def test_a_path_field_is_a_positional_argument_and_quoted():
    args = _widget_parser().parse_args(["widgets", "get", "a/b c", "--view", "detail"])
    command = args.generated
    assert [field.name for field in command.positional] == ["widget_id"]
    data = commands.payload(command, args)
    assert data == {"widget_id": "a/b c", "view": "detail"}
    assert commands.request(command, data) == ("/api/agent/v1/widgets/a%2Fb%20c?view=detail", None)


def test_a_path_field_comes_from_the_argument_or_the_input_once(tmp_path):
    document = tmp_path / "widget.json"
    document.write_text(json.dumps({"widget_id": "w1", "view": "summary"}))
    parser = _widget_parser()
    alone = parser.parse_args(["widgets", "get", "--input", f"@{document}"])
    assert commands.payload(alone.generated, alone) == {"widget_id": "w1", "view": "summary"}
    both = parser.parse_args(["widgets", "get", "w2", "--input", f"@{document}"])
    with pytest.raises(ClientError, match="given both as an argument and in --input"):
        commands.payload(both.generated, both)
    neither = parser.parse_args(["widgets", "get", "--view", "detail"])
    with pytest.raises(ClientError, match="WIDGET_ID is required"):
        commands.payload(neither.generated, neither)


def test_a_write_sends_its_input_as_a_body_and_a_document_only_by_input():
    command = _command("POST", "/api/agent/v1/widgets/{widget_id}",
                       {"widget_id": {"type": "integer"}, "document": {"type": "object"}}, ("widget_id", "document"))
    assert command.input_only == ("document",)
    assert commands.request(command, {"widget_id": 4, "document": {"a": [1, None]}}) == (
        "/api/agent/v1/widgets/4", {"document": {"a": [1, None]}},
    )


def test_a_read_leaves_a_null_out_and_cannot_carry_an_object_in_its_address():
    command = _command("GET", "/api/agent/v1/widgets", {
        "view": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
        "tag": {"type": "array", "items": {"type": "string"}},
        "limit": {"type": "integer", "default": 20},
    })
    assert commands.request(command, {"view": None, "tag": ["a"]}) == ("/api/agent/v1/widgets?tag=a", None)
    # A null where the schema takes none, or defaults to something else, would
    # silently change the request: an integer with a default, a list with none declared.
    for name in ("limit", "tag"):
        with pytest.raises(ClientError, match=f"{name} cannot be null"):
            commands.request(command, {name: None})
    for value in ({"a": 1}, [["a"]], ["a", None]):
        with pytest.raises(ClientError, match="carries no object"):
            commands.request(command, {"tag": value})


def test_an_input_document_with_a_null_field_searches_as_if_it_were_left_out(home, tmp_path):
    document = tmp_path / "search.json"
    document.write_text(json.dumps({"query": None, "location": ["London"]}))
    with Stub(Reply(200, _envelope("opportunities.search", data=_PAGE))) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, "opportunities", "search", "--input", f"@{document}", "--json")
        document.write_text(json.dumps({"location": None}))
        refused = cli(home, "opportunities", "search", "--input", f"@{document}", "--json")
    assert result.status == 0, result
    assert _query(stub.requests[0]) == {"location": ["London"]}
    # location takes a list and declares no null default: leaving it out would not mean the same.
    assert refused.status == 2 and "location cannot be null" in refused.envelope["error"]["message"]
    assert len(stub.requests) == 1


# --------------------------------------------------------------------------- #
# Help loads nothing of the engine
# --------------------------------------------------------------------------- #

_HELP_PROBE = """
import contextlib, io, json, sys
from tracker.cli.main import main
helped = []
for argv in json.loads(sys.argv[1]):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        status = main(argv)
    helped.append((status, out.getvalue()[:6]))
loaded = sorted({name.split(".")[0] for name in sys.modules} & {"pydantic", "httpx", "sqlalchemy", "fastapi"})
print(json.dumps({"helped": helped, "loaded": loaded}))
"""


def test_help_for_every_command_loads_no_model_or_http_library(home):
    argvs = [["--help"], ["capabilities", "--offline", "--json"], ["opportunities", "search", "--bogus", "--json"]]
    argvs += [[*command.words, "--help"] for command in commands.build(_bundle())]
    result = subprocess.run(
        [sys.executable, "-c", _HELP_PROBE, json.dumps(argvs)],
        cwd=home.root, env=test_cli._env(home),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["loaded"] == []
    assert [status for status, _ in report["helped"]] == [0, 0, 2] + [0] * (len(argvs) - 3)
    assert all(text == "usage:" for _, text in report["helped"][3:])


def test_the_probe_sees_a_library_a_command_loads():
    """Negative control: the probe would notice pydantic if help pulled it in."""
    result = subprocess.run(
        [sys.executable, "-c", "import tracker.agents.operations.catalog\n" + _HELP_PROBE, "[]"],
        cwd=BACKEND, env={**test_cli._system_env(), "PYTHONPATH": str(BACKEND), "PATH": os.environ.get("PATH", "")},
        capture_output=True, text=True, timeout=60,
    )
    assert "pydantic" in json.loads(result.stdout)["loaded"]


# --------------------------------------------------------------------------- #
# A person at a terminal
# --------------------------------------------------------------------------- #


def test_a_search_page_reads_as_a_table_for_a_person(home):
    page = {
        "total": 31, "count": 2, "sort": "newest", "order": "desc", "filters": {"location": ["london"]},
        "columns": ["id", "title", "company", "location", "more_locations", "workplace", "level", "listed_days",
                    "stated_pay", "estimated_pay", "pursuit"],
        "rows": [
            [4821, "Staff PM\x1b[31m", "acme", "London, UK", 2, "hybrid", "staff", 3, "120000-150000 GBP/year base",
             "180000 USD total", "applied"],
            [4822, "Senior PM", "beta", None, 0, "remote", None, None, None, None, None],
        ],
    }
    reply = _envelope("opportunities.search", data=page,
                      meta={"observed_at": "2026-11-13T14:00:00Z", "next_cursor": "c1.2.0.0123456789abcdef",
                            "partial": False, "truncated": True, "data_classes": []},
                      warnings=({"code": "ranking_truncated", "message": "More postings match\x1b[2J than ranked."},))
    with Stub(Reply(200, reply)) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, "opportunities", "search", "--location", "london", "--format", "human")
    assert result.status == 0, result
    lines = result.stdout.splitlines()
    assert lines[0] == "2 of 31, newest first"
    assert "4821" in lines[1] and "Staff PM\\u001b[31m" in lines[1] and "acme" in lines[1]
    assert "London, UK +2" in lines[1] and "stated 120000-150000 GBP/year base" in lines[1]
    assert "estimate 180000 USD total" in lines[1] and "applied" in lines[1]
    assert "\x1b" not in result.stdout
    assert lines[-1] == "more: --cursor c1.2.0.0123456789abcdef"
    # A warning qualifies the page, so a person sees it, escaped like any text.
    assert result.stderr == "warning: More postings match\\u001b[2J than ranked.\n"



@pytest.mark.parametrize("fmt", ["--json", "--format=human"])
def test_output_is_utf8_whatever_the_locale_encodes(home, fmt):
    """Broken rule caught: on Windows a pipe takes the ANSI code page, which
    cannot encode most titles, so the client crashed or wrote mojibake."""
    page = {**_PAGE, "total": 1, "count": 1, "columns": ["id", "title", "company", "location", "more_locations",
            "workplace", "level", "listed_days", "stated_pay", "estimated_pay", "pursuit"],
            "rows": [[7, "产品经理 · Ingénieure", "acme", None, 0, None, None, None, None, None, None]]}
    with Stub(Reply(200, _envelope("opportunities.search", data=page))) as stub:
        home.contexts(current="dev", dev={"url": stub.url})
        result = cli(home, "opportunities", "search", fmt, PYTHONIOENCODING="ascii")
    assert result.status == 0, result
    assert "产品经理 · Ingénieure" in result.stdout

# --------------------------------------------------------------------------- #
# A real engine on a seeded scratch database
# --------------------------------------------------------------------------- #


@pytest.fixture
def seeded_engine(engine):
    from scripts.seed_synthetic import seed
    from tracker.agents.config import AgentAccessConfig, set_agent_access

    async def prepare() -> None:
        database = create_async_engine(engine.database_url)
        try:
            async with AsyncSession(database, expire_on_commit=False) as session:
                await seed(session, 30, seed_value=1, derived=False, agent_tasks=True)
                await set_agent_access(session, AgentAccessConfig(enabled=True, allow_writes=True))
                await session.commit()
        finally:
            await database.dispose()

    asyncio.run(prepare())
    return engine


def test_search_and_vocabulary_against_a_real_engine(home, seeded_engine):
    home.contexts(current="dev", dev={"url": seeded_engine.url})

    places = cli(home, "vocabulary", "list", "--kind", "location", "--contains", "york", "--json")
    assert places.status == 0, places
    listed = [entry for entry in places.envelope["data"]["items"] if entry["open_roles"] > 0]
    assert listed, places.envelope["data"]
    place = listed[0]

    found = cli(home, "opportunities", "search", "--location", place["name"], "--family", "Product Management",
                "--limit", "3", "--json")
    assert found.status == 0, found
    body = found.envelope
    assert body["operation"] == "opportunities.search"
    assert body["data"]["filters"] == {"family": ["product_management"], "location": [place["value"]]}
    assert 1 <= body["data"]["count"] <= 3
    if body["data"]["total"] > 3:
        following = cli(home, "opportunities", "search", "--location", place["name"], "--family",
                        "Product Management", "--cursor", body["meta"]["next_cursor"], "--json")
        assert following.status == 0, following
        assert not {row[0] for row in following.envelope["data"]["rows"]} & {row[0] for row in body["data"]["rows"]}

    unknown = cli(home, "opportunities", "search", "--location", "Seatle", "--json")
    assert unknown.status == 2, unknown
    error = unknown.envelope["error"]
    assert error["code"] == "invalid_input"
    assert error["details"]["unknown"] == [{"filter": "location", "value": "Seatle"}]
    assert error["next_actions"] == [{"operation": "vocabulary.list", "arguments": {"kind": "location"}}]

    person = cli(home, "opportunities", "search", "--format", "human")
    assert person.status == 0, person
    assert person.stdout.splitlines()[0].endswith(", newest first")


@pytest.mark.parametrize(
    ("sort", "order", "label"),
    [("best_match", None, "best match first"), ("newest", "asc", "oldest first"), ("title", "desc", "title Z to A"),
     ("title", "asc", "title A to Z")],
)
def test_a_page_says_its_order(sort, order, label):
    from io import StringIO

    from tracker.cli.render import write_human

    out = StringIO()
    data = {**_PAGE, "sort": sort, "order": order}
    write_human({"ok": True, "operation": "opportunities.search", "data": data, "meta": {}}, out, StringIO())
    assert out.getvalue() == f"0 of 0, {label}\n"


def test_a_path_argument_and_a_posted_read_reach_a_real_engine(home, seeded_engine, tmp_path):
    """The two other shapes a route takes: a field in the path, and a read whose input is a body."""
    home.contexts(current="dev", dev={"url": seeded_engine.url})
    listed = cli(home, "opportunities", "search", "--limit", "1", "--json")
    assert listed.status == 0, listed
    first = listed.envelope["data"]["rows"][0][0]

    got = cli(home, "opportunities", "get", str(first), "--view", "summary", "--json")
    assert got.status == 0, got
    assert got.envelope["operation"] == "opportunities.get"
    assert got.envelope["data"]["id"] == first

    missing = cli(home, "opportunities", "get", "999999999", "--json")
    assert missing.envelope["operation"] == "opportunities.get"
    assert missing.envelope["error"]["code"] == "not_found", missing

    document = tmp_path / "recipe.json"
    document.write_text(json.dumps({"document": {"version": 99}}))
    validated = cli(home, "recipes", "validate", "--input", f"@{document}", "--json")
    assert validated.envelope["operation"] == "recipes.validate"
    assert validated.status in (0, 2), validated
    if validated.status == 2:
        assert validated.envelope["error"]["code"] == "invalid_input", validated


def test_a_keyed_write_runs_once_under_its_key_against_a_real_engine(home, seeded_engine):
    """A generated write command sends its input as the body under an
    idempotency key; the same key again replays, and the receipt reads back."""
    home.contexts(current="dev", dev={"url": seeded_engine.url})
    listed = cli(home, "opportunities", "search", "--limit", "1", "--json")
    first = listed.envelope["data"]["rows"][0][0]
    key = "idk_cli_commands_test_0001"

    saved = cli(home, "pursuits", "save", str(first), "--priority", "4", "--idempotency-key", key, "--json")
    assert saved.status == 0, saved
    assert saved.envelope["operation"] == "pursuits.save"
    assert saved.envelope["meta"]["idempotency_key"] == key
    assert saved.envelope["meta"]["replayed"] is False

    again = cli(home, "pursuits", "save", str(first), "--priority", "4", "--idempotency-key", key, "--json")
    assert again.status == 0, again
    assert again.envelope["meta"]["replayed"] is True

    other = cli(home, "pursuits", "save", str(first), "--priority", "2", "--idempotency-key", key, "--json")
    assert other.envelope["error"]["code"] == "idempotency_conflict", other

    receipt = cli(home, "receipts", "get", "--operation", "pursuits.save", "--key", key, "--json")
    assert receipt.status == 0, receipt
    assert receipt.envelope["operation"] == "receipts.get"


def test_the_documented_patch_call_clears_a_due_date_with_input_and_control_flags(home, seeded_engine, tmp_path):
    """The command contract's own call, `pursuits patch ID --input @FILE
    --if-revision N --idempotency-key KEY --format json`: the file's explicit
    null clears the due date, every field it leaves out stays put, the call
    written all in JSON works the same, and a flag naming a field the file
    also gives is refused before anything is sent."""
    home.contexts(current="dev", dev={"url": seeded_engine.url})

    def run(*args: str) -> dict:
        result = cli(home, *args)
        assert result.status == 0, result
        return result.envelope

    target = run("pursuits", "list", "--limit", "1", "--json")["data"]["items"][0]["job_id"]
    revision = run("pursuits", "get", str(target), "--json")["data"]["revision"]
    due = "2026-12-01T09:00:00+00:00"
    run("pursuits", "patch", str(target), "--if-revision", str(revision), "--next-action", "Call the recruiter",
        "--next-action-due", due, "--notes", "Met at the meetup", "--json")
    before = run("pursuits", "get", str(target), "--json")["data"]
    assert before["next_action_due"] is not None and before["next_action"] == "Call the recruiter"

    follow_up = tmp_path / "follow-up.json"
    follow_up.write_text(json.dumps({"next_action_due": None}))
    documented = ("pursuits", "patch", str(target), "--input", f"@{follow_up}", "--if-revision",
                  str(before["revision"]), "--idempotency-key", "run-42-followup", "--format", "json")
    cleared = run(*documented)
    assert cleared["meta"]["idempotency_key"] == "run-42-followup"
    after = run("pursuits", "get", str(target), "--json")["data"]
    assert after["next_action_due"] is None
    assert {key: after[key] for key in ("next_action", "notes", "stage", "priority")} == {
        key: before[key] for key in ("next_action", "notes", "stage", "priority")
    }
    assert after["revision"] == before["revision"] + 1

    # A retry of the same call under its key replays: it writes nothing more.
    again = run(*documented)
    assert again["meta"]["replayed"] is True
    assert run("pursuits", "get", str(target), "--json")["data"]["revision"] == after["revision"]

    # The same kind of call with the revision inside the file.
    whole = tmp_path / "whole.json"
    whole.write_text(json.dumps({"if_revision": after["revision"], "next_action": None}))
    run("pursuits", "patch", str(target), "--input", f"@{whole}", "--idempotency-key", "run-42-whole", "--json")
    latest = run("pursuits", "get", str(target), "--json")["data"]
    assert latest["next_action"] is None and latest["notes"] == "Met at the meetup"

    # The revision in the file and as a flag: refused, naming the field, and nothing is written.
    overlap = tmp_path / "overlap.json"
    overlap.write_text(json.dumps({"if_revision": latest["revision"], "notes": None}))
    refused = cli(home, "pursuits", "patch", str(target), "--input", f"@{overlap}", "--if-revision",
                  str(latest["revision"]), "--idempotency-key", "run-42-overlap", "--json")
    assert refused.status == 2, refused
    assert refused.envelope["error"]["code"] == "invalid_arguments"
    assert "if_revision" in refused.envelope["error"]["message"]
    unchanged = run("pursuits", "get", str(target), "--json")["data"]
    assert unchanged["notes"] == "Met at the meetup" and unchanged["revision"] == latest["revision"]
    lookup = cli(home, "receipts", "get", "--operation", "pursuits.patch", "--key", "run-42-overlap", "--json")
    assert lookup.envelope["ok"] is False, lookup
