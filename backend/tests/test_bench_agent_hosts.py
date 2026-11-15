"""The bench's CLI mode and its Codex host, held to what makes a trial count.

A CLI trial is graded on what the trial's own `roleband` logged. These tests
hold the ways a run could look right and measure something else: a host that
was still offered the MCP server, a `roleband` that ran from elsewhere on the
PATH, a model's arguments that went through a shell, a Codex run that read the
person's config or the bench's answers.
"""

from __future__ import annotations

import asyncio
import contextlib
import difflib
import json
import os
import socket
import subprocess
import tomllib
from pathlib import Path

import httpx
import pytest

import scripts.bench_agent_tasks as bench
from scripts.bench_agent_tasks import (
    CliSetup,
    Engine,
    Transcript,
    claude_command,
    cli_breaches,
    cli_setup,
    codex_command,
    codex_overrides,
    grade_trial,
    load_corpus,
    operation_of,
    parse_claude_stream,
    parse_codex_events,
    prepare_connect,
    prohibited_effects,
    read_cli_log,
    recording_proxy,
    recovery_turns,
    roleband_arguments,
    roleband_invocations,
    run_local,
    run_roleband,
    settle_cli_calls,
    verify_cli_calls,
)
from tests.test_bench_agent_tasks import EXPECTATIONS, TASKS, _state

KNOWN = bench.known_operations()


def _cli(tmp_path: Path, *, port: int = 9, connect: dict | None = None, url: str | None = None,
         records: list[dict] | None = None) -> CliSetup:
    """The trial's command, pinned to an engine that is not there unless `url` names one."""
    engine = Engine(url=url or f"http://127.0.0.1:{port}", workspace_id=None, operations=["status", "capabilities"],
                    records=records if records is not None else [])
    cwd = tmp_path / "host-cwd"
    cwd.mkdir(exist_ok=True)
    return cli_setup(tmp_path / "ws" / "runs" / "r" / "t-0", engine, connect or {"instructions": "Use roleband."},
                     cwd=cwd)


def _shell(command: str, **extra) -> dict:
    return {"kind": "shell", "command": command, "roleband": roleband_invocations(command), "refused": False, **extra}


# --- naming a call --------------------------------------------------------------


@pytest.mark.parametrize(("argv", "operation"), [
    (["status"], "status"),
    (["--context", "bench", "status", "--json"], "status"),
    (["describe", "opportunities.search"], "describe"),
    (["--json", "opportunities", "search", "--query", "pm"], "opportunities.search"),
    (["opportunities", "get", "4821", "--view", "detail"], "opportunities.get"),
    (["pursuits", "patch", "4821", "--input", "-"], "pursuits.patch"),
    (["recipes", "draft", "save", "--input", "-"], "recipes.draft.save"),
    (["sources", "inspect", "https://example.test"], "sources.inspect"),
    (["no-such", "thing"], "no_such.thing"),
    ([], "roleband"),
])
def test_a_command_is_named_by_the_operation_it_calls(argv, operation):
    assert operation_of(argv, KNOWN) == operation


def test_a_network_or_recipe_command_is_a_prohibited_effect_as_its_tool_was():
    calls = [{"name": operation_of(["sources", "inspect", "x"], KNOWN)},
             {"name": operation_of(["recipes", "draft", "save"], KNOWN)},
             {"name": operation_of(["capabilities"], KNOWN)}]
    assert prohibited_effects(TASKS["discover_overdue"], [], calls) == [
        "called sources.inspect", "called recipes.draft.save"]


def test_a_search_that_dropped_a_filter_starts_recovery_through_the_command_too():
    envelope = json.dumps({"ok": True, "data": {"items": [], "dropped_filters": ["locations"]}})
    calls = [{"name": "opportunities.search", "result": envelope}, {"name": "opportunities.search", "result": "{}"}]
    assert recovery_turns(calls) == 1
    assert recovery_turns([{"name": "opportunities.search", "result": json.dumps({"ok": True, "data": {}})}]) == 0


@pytest.mark.parametrize(("command", "count"), [
    ("roleband status", 1),
    ("roleband status && roleband capabilities --json", 2),
    ("ROLEBAND_AGENT=1 roleband describe pursuits.patch", 1),
    ("/somewhere/bin/roleband status | head -5", 1),
    ("(roleband status)", 1),
    ("echo roleband status", 0),
    ("cat expectations.json", 0),
])
def test_the_roleband_calls_in_a_shell_command_line_are_counted(command, count):
    assert roleband_invocations(command) == count


# --- the trial's own command ----------------------------------------------------


@pytest.mark.asyncio
async def test_the_trial_command_logs_each_call_it_answers(tmp_path):
    cli = _cli(tmp_path)
    offline = await run_roleband(cli, ["capabilities", "--offline"], cwd=tmp_path)
    unreachable = await run_roleband(cli, ["status"], cwd=tmp_path)

    assert offline["exit_code"] == 0 and json.loads(offline["stdout"])["ok"] is True
    # The context names a port nothing listens on: the engine is unavailable, never another one.
    assert unreachable["exit_code"] == 3
    assert json.loads(unreachable["stdout"])["error"]["code"] == "engine_unavailable"
    logged = read_cli_log(cli)
    assert [(call["name"], call["args"], call["exit_code"], call["is_error"]) for call in logged] == [
        ("capabilities", ["capabilities", "--offline"], 0, False),
        ("status", ["status"], 3, True),
    ]
    assert logged[0]["result"] == offline["stdout"]
    assert (cli.bin_dir / "roleband").exists() and [path.name for path in cli.bin_dir.iterdir()] == ["roleband"]


@pytest.mark.asyncio
async def test_arguments_reach_the_command_as_given_with_no_shell_between(tmp_path):
    cli = _cli(tmp_path)
    marker = tmp_path / "PWNED"
    argv = ["describe", f"; touch {marker}", f"$(touch {marker})", "`touch PWNED`", "| cat"]
    ran = await run_roleband(cli, argv, cwd=tmp_path)

    assert ran["exit_code"] == 2  # not an operation id: refused by the client's own parser
    assert not marker.exists() and not (tmp_path / "PWNED").exists()
    assert read_cli_log(cli)[0]["args"] == argv
    with pytest.raises(TypeError):
        await run_roleband(cli, "status --json", cwd=tmp_path)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_the_trial_command_runs_this_checkout_whatever_the_host_puts_on_pythonpath(tmp_path):
    """Isolated like the app's own command: a `tracker` package on the host's
    PYTHONPATH, or a context file the host names, changes nothing."""
    evil = tmp_path / "evil" / "tracker"
    evil.mkdir(parents=True)
    (evil / "__init__.py").write_text("raise SystemExit('the wrong client ran')\n")
    planted = tmp_path / "planted-ran"
    (evil.parent / "sitecustomize.py").write_text(f"open({str(planted)!r}, 'w').close()\n")
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"format": 1, "current": "x", "contexts": {"x": {"url": "http://127.0.0.1:1"}}}))
    cli = _cli(tmp_path)
    cli.env = {**cli.env, "PYTHONPATH": str(evil.parent), "ROLEBAND_CLI_CONFIG": str(other)}
    ran = await run_roleband(cli, ["status"], cwd=tmp_path)
    assert not planted.exists()
    assert ran["exit_code"] == 3, ran["stderr"]
    error = json.loads(ran["stdout"])["error"]
    assert error["code"] == "engine_unavailable"
    assert (error["details"]["context"], error["details"]["url"]) == ("bench", "http://127.0.0.1:9")


def test_a_model_s_arguments_are_a_list_never_a_command_line():
    assert roleband_arguments({"args": ["capabilities", "--json"]}) == ["capabilities", "--json"]
    assert roleband_arguments({"args": '["status"]'}) == ["status"]
    assert roleband_arguments({"args": ["roleband", "status"]}) == ["status"]
    for bad in ({"args": "status --json"}, {"args": ["status", 3]}, {"args": None}, {}, ["status"]):
        with pytest.raises(ValueError):
            roleband_arguments(bad)


# --- breaches: what fails a CLI trial whatever it answered ----------------------


def _claude_events(*, servers: list, tools: list, tool: str, command: str | None = None, answer: dict) -> str:
    use = {"type": "tool_use", "id": "t1", "name": tool, "input": {"command": command} if command else {}}
    events = [
        {"type": "system", "subtype": "init", "model": "m", "mcp_servers": servers, "tools": tools},
        {"type": "assistant", "message": {"content": [use]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "2"}]}},
        {"type": "result", "result": f"ANSWER: {json.dumps(answer)}", "usage": {"input_tokens": 5, "output_tokens": 1}},
    ]
    return "\n".join(json.dumps(event) for event in events)


def test_claude_in_cli_mode_has_no_mcp_server_and_only_roleband_in_bash(tmp_path):
    cli = _cli(tmp_path, connect={"instructions": "Use roleband.", "claude_settings_path": "/s.json"})
    command = claude_command("claude", "go", interface="cli", cli=cli)
    assert "--mcp-config" not in command and "--strict-mcp-config" in command
    assert command[command.index("--tools") + 1] == "Bash"
    assert command[command.index("--allowedTools") + 1] == "Bash(roleband *)"
    assert command[command.index("--settings") + 1] == "/s.json"
    assert command[command.index("--setting-sources") + 1] == ""
    mcp = claude_command("claude", "go", interface="mcp", mcp_config=tmp_path / "mcp.json")
    assert mcp[mcp.index("--tools") + 1] == "" and "Bash(roleband *)" not in mcp


def test_a_cli_trial_that_fell_back_to_mcp_fails_with_the_right_answer(tmp_path):
    right = {"overdue_follow_ups": 2}
    stream = _claude_events(servers=[{"name": "roleband", "status": "connected"}],
                            tools=["Bash", "mcp__roleband__get_pursuits"], tool="mcp__roleband__get_pursuits",
                            answer=right)
    transcript = parse_claude_stream(stream, interface="cli")
    cli = _cli(tmp_path)
    transcript.breaches += cli_breaches(transcript.host_calls, [], cli, tmp_path / "ws")
    grade = grade_trial(TASKS["discover_overdue"], EXPECTATIONS, right, _state(), _state(), [], transcript.breaches)
    assert not grade["success"]
    assert "offered MCP server roleband" in grade["prohibited_effects"]
    assert "used mcp__roleband__get_pursuits outside the command line" in grade["prohibited_effects"]
    # The same answer through the command alone passes.
    clean = parse_claude_stream(_claude_events(servers=[], tools=["Bash"], tool="Bash", command="roleband status",
                                               answer=right), interface="cli")
    logged = [{"name": "status", "result": "{}", "is_error": False}]
    clean.breaches += cli_breaches(clean.host_calls, logged, cli, tmp_path / "ws")
    assert grade_trial(TASKS["discover_overdue"], EXPECTATIONS, right, _state(), _state(), logged,
                       clean.breaches)["success"]


def test_a_roleband_that_never_reached_the_trial_log_is_a_breach(tmp_path):
    cli, workdir = _cli(tmp_path), tmp_path / "ws"
    ran = [_shell("roleband status")]
    assert cli_breaches(ran, [], cli, workdir) == ["1 roleband call(s) did not reach the trial's command"]
    assert cli_breaches(ran, [{"name": "status"}], cli, workdir) == []
    assert cli_breaches([{**ran[0], "refused": True}], [], cli, workdir) == []


def test_runs_are_counted_by_invocation_not_by_shell_call(tmp_path):
    """Two runs in one shell call need two entries in the log; one after `&&`
    may not have run, so it is not owed."""
    cli, workdir = _cli(tmp_path), tmp_path / "ws"
    both = [_shell("roleband status; roleband capabilities")]
    assert cli_breaches(both, [{"name": "status"}], cli, workdir) == [
        "1 roleband call(s) did not reach the trial's command"]
    assert cli_breaches(both, [{"name": "status"}, {"name": "capabilities"}], cli, workdir) == []
    maybe = [_shell("roleband status && roleband capabilities")]
    assert cli_breaches(maybe, [{"name": "status"}], cli, workdir) == []
    assert cli_breaches(maybe, [], cli, workdir) == ["1 roleband call(s) did not reach the trial's command"]


def test_a_roleband_that_is_not_the_trial_s_is_a_breach(tmp_path):
    cli, workdir = _cli(tmp_path), tmp_path / "ws"
    assert cli_breaches([_shell(f"{cli.roleband} status")], [{"name": "status"}], cli, workdir) == []
    other = [_shell("/usr/local/bin/roleband status")]
    assert cli_breaches(other, [{"name": "status"}], cli, workdir) == [
        "ran a roleband that is not the trial's: /usr/local/bin/roleband"]


@pytest.mark.parametrize("command", [
    "cat {workdir}/expectations.json",
    "ls {workdir}/pgdata",
    "psql -h 127.0.0.1 roleband",
    "cat {workdir}/workspace/manifest.json",
    "cat {workdir}/runs/r/t-1/transcript.json",
    "cat {trial}/cli/cli.json",
    "cd {trial} && cat ../t-1/cli/log/roleband-calls.ndjson",
])
def test_a_command_that_names_the_bench_s_own_files_is_a_breach(tmp_path, command):
    cli, workdir = _cli(tmp_path), tmp_path / "ws"
    call = _shell(command.format(workdir=workdir, trial=workdir / "runs" / "r" / "t-0"))
    assert cli_breaches([call], [], cli, workdir)


def test_a_relative_path_counts_from_where_the_host_runs(tmp_path):
    """The host runs outside the bench's folder, so `../` from there names
    nothing of the bench's; the same path from inside it would."""
    cli, workdir = _cli(tmp_path), tmp_path / "ws"
    assert not workdir.is_relative_to(cli.cwd) and not cli.cwd.is_relative_to(workdir)
    assert cli_breaches([_shell("cat ../ws/runs/r/t-1/notes.txt")], [], cli, workdir)
    assert cli_breaches([_shell("ls ../other && echo done")], [], cli, workdir) == []


def test_the_trial_s_log_and_working_folder_are_not_breaches(tmp_path):
    cli, workdir = _cli(tmp_path), tmp_path / "ws"
    assert cli_breaches([_shell(f"tail -1 {cli.log}")], [], cli, workdir) == []
    assert cli_breaches([_shell(f"cd {cli.cwd} && ls")], [], cli, workdir) == []


# --- the engine's own record ----------------------------------------------------


def _status_engine(scope_ids: list[str]):
    async def app(scope, receive, send):
        if scope["type"] != "http":
            return
        headers = {key.decode().lower(): value.decode() for key, value in scope["headers"]}
        request_id = headers.get(bench.REQUEST_ID_HEADER.lower(), "none")
        scope_ids.append(request_id)
        body = json.dumps({"contract_version": "1.0", "request_id": request_id, "workspace_id": None,
                           "operation": "status", "ok": True, "data": {"state": "ready"}, "meta": {},
                           "warnings": [], "error": None}).encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
    return app


@contextlib.asynccontextmanager
async def _serve(app):
    import uvicorn

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="warning"))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    while not server.started:
        await asyncio.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{listener.getsockname()[1]}"
    finally:
        server.should_exit = True
        await task
        listener.close()


@pytest.mark.asyncio
async def test_an_answer_counts_only_if_the_engine_gave_it(tmp_path):
    seen: list[str] = []
    async with _serve(_status_engine(seen)) as engine_url, recording_proxy(engine_url) as (proxy_url, proxy):
        cli = _cli(tmp_path, url=proxy_url, records=proxy.records)
        ran = await run_roleband(cli, ["status"], cwd=cli.cwd)
        people = await run_roleband(cli, ["status", "--format", "human"], cwd=cli.cwd)
        alone = await run_roleband(cli, ["capabilities", "--offline"], cwd=cli.cwd)
        assert (ran["exit_code"], people["exit_code"], alone["exit_code"]) == (0, 0, 0)

        logged = read_cli_log(cli)
        assert verify_cli_calls(logged, proxy.records) == []
        assert [call["verified"] for call in logged] == [True, False, False]
        assert json.loads(logged[0]["result"])["data"] == {"state": "ready"}
        assert len(seen) == len(proxy.records) == 2 and proxy.records[0]["request_id"] == seen[0]

        # A log line the engine never wrote: changed data under a real request id, and an invented one.
        forged = json.loads(ran["stdout"])
        forged["data"] = {"state": "ready", "overdue": 2}
        with cli.log.open("a") as log:
            for envelope in (forged, {**forged, "request_id": "invented"}):
                log.write(json.dumps({"argv": ["status"], "exit_code": 0, "stdout": json.dumps(envelope),
                                      "stderr": ""}) + "\n")
        logged = read_cli_log(cli)
        assert verify_cli_calls(logged, proxy.records) == [
            "the log's answer to status is not the engine's",
            "the log holds an answer to status the engine never gave",
        ]
        assert logged[-1]["result"] == "" and "invented" in logged[-1]["stdout"]

        # A request that bypassed the trial's command shows in the proxy's record alone.
        env = {key: os.environ[key] for key in ("HOME", "PATH") if key in os.environ}
        bypass = await asyncio.create_subprocess_exec(
            *bench._client_command("--context", "bench", "status"),
            env={**env, "ROLEBAND_CLI_CONFIG": cli.env["ROLEBAND_CLI_CONFIG"]},
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        assert await asyncio.wait_for(bypass.wait(), 60) == 0
        assert verify_cli_calls(read_cli_log(cli)[:3], proxy.records) == [
            "the engine was reached 1 time(s) outside the trial's command"]


def test_connect_writes_to_the_trial_s_folders_whatever_the_host_sets(tmp_path):
    cli = _cli(tmp_path)
    home, elsewhere = tmp_path / "home", tmp_path / "elsewhere"
    home.mkdir()
    env = {"HOME": str(home), "PATH": os.environ["PATH"], "CODEX_HOME": str(elsewhere),
           "CLAUDE_CONFIG_DIR": str(elsewhere)}
    for host in ("codex", "claude-code"):
        result = subprocess.run([str(cli.roleband), "connect", host, "--apply", "--json"], env=env,
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout[-400:]
    assert not elsewhere.exists() and not (home / ".codex").exists() and not (home / ".claude").exists()
    connect = cli.roleband.parent.parent / "connect"
    assert any((connect / "codex").iterdir()) and any((connect / "claude").iterdir())


# --- the local loop's one tool --------------------------------------------------


def _reply(**message) -> httpx.Response:
    return httpx.Response(200, json={"usage": {"prompt_tokens": 100, "completion_tokens": 10}, "choices": [{
        "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
        "message": {"role": "assistant", "content": None, **message}}]})


@pytest.mark.asyncio
async def test_the_local_loop_runs_the_trial_command_and_grades_on_its_log(monkeypatch, tmp_path):
    cli = _cli(tmp_path)
    sent: list[dict] = []
    replies = iter([
        _reply(tool_calls=[{"id": "c1", "type": "function", "function": {
            "name": "roleband", "arguments": json.dumps({"args": ["capabilities", "--offline"]})}}]),
        _reply(tool_calls=[{"id": "c2", "type": "function", "function": {
            "name": "roleband", "arguments": json.dumps({"args": "capabilities --offline"})}}]),
        _reply(content='ANSWER: {"overdue_follow_ups": 2}'),
    ])

    def answer(request):
        sent.append(json.loads(request.content))
        return next(replies)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(answer), **kw))
    monkeypatch.delenv(bench.API_KEY_ENV, raising=False)
    trial = tmp_path / "trial"
    transcript = await run_local("go", tmp_path, "", host="lmstudio", model="m", base_url="http://127.0.0.1:1/v1",
                                 interface="cli", cli=cli, trial_dir=trial)

    assert transcript.error is None
    assert [tool["function"]["name"] for tool in sent[0]["tools"]] == ["roleband"]
    assert "Use roleband." in sent[0]["messages"][0]["content"]
    first, second = transcript.tool_calls
    assert (first["name"], first["exit_code"], first["is_error"]) == ("capabilities", 0, False)
    assert json.loads(json.loads(sent[1]["messages"][-1]["content"])["stdout"])["ok"] is True
    # A command line as one string is refused, not split by a shell.
    assert second["is_error"] and second.get("ran") is False and "list of strings" in second["result"]
    settle_cli_calls(transcript, cli, tmp_path, host="lmstudio")
    assert transcript.breaches == []
    # A call the tool made that the log never saw is a breach.
    cli.log.write_text("")
    settle_cli_calls(transcript, cli, tmp_path, host="lmstudio")
    assert transcript.breaches and "differ" in transcript.breaches[0]


# --- Codex ----------------------------------------------------------------------


def _codex_cli(tmp_path: Path) -> CliSetup:
    return _cli(tmp_path, connect={"instructions": 'Say "roleband".\nThen\\stop.',
                                   "codex_config": {"sandbox_workspace_write": {"network_access": True}}})


def test_codex_never_reads_the_person_s_config_or_rules(tmp_path):
    for command in (
        codex_command("codex", "go", interface="mcp", cwd=tmp_path, mcp_server={"command": "py", "args": []}),
        codex_command("codex", "go", interface="cli", cwd=tmp_path, cli=_codex_cli(tmp_path)),
    ):
        assert {"--ignore-user-config", "--ignore-rules", "--ephemeral"} <= set(command)
        assert command[-2:] == ["--", "go"]
        assert not any("auth" in part or ".codex" in part for part in command)


def test_codex_through_mcp_has_the_server_and_no_shell(tmp_path):
    command = codex_command("codex", "go", interface="mcp", cwd=tmp_path,
                            mcp_server={"command": "/py", "args": ["-m", "tracker.mcp.server"], "env": {"A": "b"}})
    overrides = [command[index + 1] for index, part in enumerate(command) if part == "-c"]
    assert "features.shell_tool=false" in overrides and "features.unified_exec=false" in overrides
    assert command[command.index("-s") + 1] == "read-only"
    assert 'mcp_servers.roleband.command="/py"' in overrides
    assert 'mcp_servers.roleband.env.A="b"' in overrides


def test_codex_through_the_command_has_no_mcp_server_and_connect_s_network_setting(tmp_path):
    cli = _codex_cli(tmp_path)
    command = codex_command("codex", "go", interface="cli", cwd=tmp_path, cli=cli)
    overrides = [command[index + 1] for index, part in enumerate(command) if part == "-c"]
    assert not any(item.startswith("mcp_servers") for item in overrides)
    assert "features.shell_tool=false" not in overrides
    assert command[command.index("-s") + 1] == "workspace-write"
    assert "sandbox_workspace_write.network_access=true" in overrides
    assert command[command.index("--add-dir") + 1] == str(cli.log.parent)
    instructions = next(item for item in overrides if item.startswith("developer_instructions="))
    assert tomllib.loads(instructions)["developer_instructions"] == cli.instructions


def test_settings_reach_codex_as_toml_that_reads_back_the_same():
    settings = {"a": {"b": True, "c": 'quote " and \\ and\nnewline', "d": ["x", 2], "e": {"f": "g"}}}
    pairs = codex_overrides(settings)
    assert pairs[::2] == ["-c"] * (len(pairs) // 2)
    merged: dict = {}
    for pair in pairs[1::2]:
        key, value = pair.split("=", 1)
        node = merged
        *path, last = key.split(".")
        for part in path:
            node = node.setdefault(part, {})
        node[last] = tomllib.loads(f"v = {value}")["v"]
    assert merged == settings


def _codex_events(*items: dict, usage: dict | None = None) -> str:
    events = [{"type": "thread.started"}, {"type": "turn.started"},
              *({"type": "item.completed", "item": item} for item in items),
              {"type": "turn.completed", "usage": usage or {"input_tokens": 10, "output_tokens": 3}}]
    return "\n".join(json.dumps(event) for event in events)


def test_codex_mcp_events_become_graded_calls_and_a_shell_command_a_breach():
    tool = {"type": "mcp_tool_call", "server": "roleband", "tool": "get_pursuits", "arguments": {},
            "result": {"content": [{"type": "text", "text": "[]"}]}, "status": "completed"}
    shell = {"type": "command_execution", "command": "/bin/zsh -lc 'cat x'", "aggregated_output": "", "exit_code": 0}
    message = {"type": "agent_message", "text": 'Done.\nANSWER: {"overdue_follow_ups": 2}'}
    transcript = parse_codex_events(_codex_events(tool, message), interface="mcp")
    assert [(call["name"], call["result"]) for call in transcript.tool_calls] == [("get_pursuits", "[]")]
    assert transcript.breaches == [] and (transcript.tokens_in, transcript.tokens_out) == (10, 3)
    assert json.loads(transcript.final_text.split("ANSWER: ")[1]) == {"overdue_follow_ups": 2}
    leaked = parse_codex_events(_codex_events(tool, shell, message), interface="mcp")
    assert leaked.breaches == ["ran a shell command in MCP mode: cat x"]


def test_a_codex_cli_trial_that_used_mcp_fails(tmp_path):
    tool = {"type": "mcp_tool_call", "server": "roleband", "tool": "get_pursuits", "arguments": {},
            "result": {"content": []}, "status": "completed"}
    shell = {"type": "command_execution", "command": ["/bin/zsh", "-lc", "roleband status"], "exit_code": 0}
    transcript = parse_codex_events(_codex_events(tool, shell), interface="cli")
    assert transcript.tool_calls == []
    assert [call["command"] for call in transcript.host_calls if call["kind"] == "shell"] == ["roleband status"]
    breaches = cli_breaches(transcript.host_calls, [{"name": "status"}], _cli(tmp_path), tmp_path / "ws")
    assert breaches == ["used mcp:roleband/get_pursuits outside the command line"]


# --- connect, applied to the run's own folder -----------------------------------


def test_the_cli_mode_uses_what_connect_writes_and_never_the_person_s_folders(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    record = prepare_connect(tmp_path / "run")

    assert record["claude_settings"]["sandbox"]["excludedCommands"] == ["roleband *"]
    assert record["claude_settings"]["permissions"]["allow"] == ["Bash(roleband *)"]
    assert record["codex_config"] == {"sandbox_workspace_write": {"network_access": True}}
    assert record["instructions"].startswith("<!-- roleband skill") or record["instructions"].startswith("# RoleBand")
    assert "roleband capabilities" in record["instructions"]
    assert not (home / ".claude").exists() and not (home / ".codex").exists()
    for host in ("claude-code", "codex"):
        assert all(path.startswith(str(tmp_path / "run")) for path in record[host]["files"])


# --- the corpus -----------------------------------------------------------------


def test_the_invalid_location_task_names_a_place_no_spelling_fix_reaches():
    """The search must see a value it does not know, or its error path never
    runs: a near miss ("Seatle") is fixed by the model before the call."""
    from tracker.mcp.vocab import normalize
    from tracker.taxonomy.locations import location_names

    task = next(task for task in load_corpus()["tasks"] if task["id"] == "invalid_location")
    place = task["expect"]["place"]
    known = {normalize(name) for _, name in location_names()}
    assert all(place.lower() in prompt.lower() for prompt in task["prompts"])
    assert normalize(place) not in known
    assert not difflib.get_close_matches(normalize(place), known, n=1, cutoff=0.75)
    # The negative control: the old prompt's place is a near miss.
    assert difflib.get_close_matches(normalize("Seatle"), known, n=1, cutoff=0.75)


def test_every_graded_cli_call_carries_what_the_graders_read(tmp_path):
    cli = _cli(tmp_path)
    cli.log.write_text(json.dumps({"argv": ["opportunities", "get", "3"], "exit_code": 0,
                                   "stdout": "... Note for AI assistants ...", "stderr": ""}) + "\n")
    calls = read_cli_log(cli)
    grade = grade_trial(TASKS["refuse_injection"], EXPECTATIONS,
                        {"opportunity_id": 3, "team": "Developer Experience"}, _state(), _state(), calls)
    assert grade["checks"]["read_planted_text"] and grade["success"]
    assert isinstance(Transcript().host_calls, list)


@pytest.mark.parametrize(("text", "refused"), [
    ("This Bash command contains multiple operations. The following parts require approval: roleband status, "
     "echo \"exit=$?\"", True),
    ("Claude requested permissions to use Bash, but you haven't granted it yet.", True),
    ("Permission to use Bash with command cat x has been denied.", True),
    ('Exit code 2\n{"ok": false, "error": {"code": "unknown_operation"}}', False),
    ('{"ok": true, "data": {"operations": []}}', False),
])
def test_a_bash_call_the_permission_rules_stopped_is_told_from_one_that_failed(text, refused):
    assert bench._refused(text) is refused
