"""The `roleband-top-picks` skill against the engine it drives.

The three files are what an assistant follows, unattended in a scheduled run:
a command, flag, field, step or code they name that the engine does not have
fails the run, and nobody is watching to fix it. So every name in them is
resolved here against the client's bundled index and the engine's own types,
and the numbers they state are the engine's.
"""

from __future__ import annotations

import io
import json
import re
import shlex
import typing
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from tracker.agents.operations.outcomes import OUTCOMES
from tracker.cli import commands
from tracker.cli.main import BUNDLE, UsageError, build_parser
from tracker.db.models import FEEDBACK_REASONS
from tracker.picks.brief import ROUTINE_PARTS, BriefBody, Check
from tracker.picks.queue import TRIAL_CAP
from tracker.picks.setup import STEPS
from tracker.picks.verdicts import (
    NEAR_MISS_REASONS,
    NOTE_MAX,
    PICK_REASONS,
    REASON_MAX,
    PassCode,
    Refusal,
)
from tracker.platform.agent_hosts import TOP_PICKS_SKILL
from tracker.settings_store import DAILY_CAP_DEFAULT, DAILY_CAP_MAX

FOLDER = TOP_PICKS_SKILL.source
FILES = {name: (FOLDER / name).read_text(encoding="utf-8") for name in TOP_PICKS_SKILL.files}

#: What each placeholder in the files stands for, as an assistant fills it in.
PLACEHOLDERS = {
    "RUN": "run_8f3k2a91c0de", "KEY": "picks-run-2026-11-26", "N": "4", "CURSOR": "50", "ID": "4821",
    "COMPANY": "acme", "YOUR_MODEL_NAME": "claude-opus-5-5",
}
#: The envelope every command prints, around `data`.
ENVELOPE = {"ok", "data", "error", "meta", "warnings", "code", "message", "details"}


def _spans(text: str) -> list[str]:
    """Every inline code span and fenced line."""
    fenced = re.findall(r"```[a-z]*\n(.*?)```", text, re.DOTALL)
    unfenced = re.sub(r"```[a-z]*\n.*?```", "", text, flags=re.DOTALL)
    return re.findall(r"`([^`\n]+)`", unfenced) + [line for block in fenced for line in block.splitlines()]


def _all_spans() -> list[tuple[str, str]]:
    return [(name, span) for name, text in FILES.items() for span in _spans(text)]


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


@cache
def _index() -> dict[str, dict[str, Any]]:
    document = json.loads(BUNDLE.read_text(encoding="utf-8"))
    return {entry["operation"]: entry for entry in document["operations"]}


#: The commands the client writes itself rather than from the index.
WRITTEN = ("status", "capabilities", "describe", "connect")


def _operation_of(words: list[str]) -> str | None:
    """The operation, or written command, that `words` (after `roleband`) name in full."""
    if len(words) == 1 and words[0] in WRITTEN:
        return words[0]
    return {commands.words_of(name): name for name in _index()}.get(tuple(words))


def _is_mention(words: list[str]) -> bool:
    """`roleband picks decide` named in a sentence, with nothing to run."""
    return all(re.fullmatch(r"[a-z][a-z-]*", word) for word in words[1:])


def _commands() -> list[tuple[str, str, str | None]]:
    """Every `roleband ...` command the files show, as (file, command line,
    the JSON piped into it). `roleband ...` alone stands for any command."""
    found = []
    for name, span in _all_spans():
        piped = None
        line = span
        if " | roleband " in span:
            echo, line = span.split(" | ", 1)
            piped = shlex.split(echo)[1]
        words = line.split()
        if len(words) > 1 and words[0] == "roleband" and words[1] != "..." and not _is_mention(words):
            found.append((name, line, piped))
    return found


def _mentions() -> list[tuple[str, str]]:
    return [(name, span) for name, span in _all_spans()
            if span.startswith("roleband ") and _is_mention(span.split())]


def test_a_command_named_in_a_sentence_exists():
    named = _mentions()
    assert ("setup.md", "roleband picks decide") in named
    for file, span in named:
        assert _operation_of(span.split()[1:]) is not None, (file, span)


def _filled(line: str) -> list[str]:
    words = shlex.split(line)
    return [PLACEHOLDERS.get(word, word) for word in words if word != "..."]


def _piped(text: str) -> dict[str, Any]:
    """A piped JSON example with its stand-ins filled: `{...}` and `[...]`
    are any object and list."""
    text = text.replace("{...}", "{}").replace("[...]", "[]")
    text = re.sub(r'"([A-Z_]+)"', lambda match: json.dumps(PLACEHOLDERS.get(match.group(1), match.group(1))), text)
    text = re.sub(r"\b([A-Z_]+)\b", lambda match: PLACEHOLDERS.get(match.group(1), match.group(1)), text)
    document = json.loads(text)
    assert isinstance(document, dict)
    return document


def test_the_files_show_the_routine_and_setup_commands():
    lines = {line.split(" --")[0] for _, line, _ in _commands()}
    for expected in ("roleband picks status", "roleband picks begin", "roleband picks decide", "roleband picks next",
                     "roleband picks finish", "roleband brief patch", "roleband background set",
                     "roleband background add-document", "roleband picks switch", "roleband picks samples"):
        assert expected in lines, expected


@pytest.mark.parametrize(("file", "line", "piped"), _commands(), ids=lambda value: str(value)[:60])
def test_every_command_names_an_operation_the_client_takes_with_flags_it_has(file, line, piped, tmp_path):
    """A command that names no operation, a flag the operation lacks, a
    piped field outside its input, or a required field left out fails here."""
    words = _filled(line)
    if "PATH" in words:
        cv = tmp_path / "cv.pdf"
        cv.write_bytes(b"%PDF-1.4\n")
        words[words.index("PATH")] = str(cv)
    try:
        args = build_parser().parse_args(words[1:])
    except UsageError as error:
        pytest.fail(f"{file}: {line}: {error}")
    generated = getattr(args, "generated", None)
    assert generated is not None, f"{file}: {line} names no operation of the index"
    schema = _index()[generated.operation]["input_schema"]
    data = _piped(piped) if piped is not None else None
    if data is not None:
        assert set(data) <= set(schema["properties"]), (file, line, sorted(set(data) - set(schema["properties"])))
    if "..." in line:
        # The rest of the command is given elsewhere in the files.
        return
    stdin = io.StringIO(json.dumps(data)) if data is not None else None
    sent = commands.payload(generated, args, stdin=stdin)
    assert set(schema.get("required", [])) <= set(sent), (file, line)
    if generated.keyed:
        assert args.idempotency_key, f"{file}: {line} is a write and names no --idempotency-key"


# --------------------------------------------------------------------------- #
# Fields and codes
# --------------------------------------------------------------------------- #


def _operations_named() -> set[str]:
    named = {_operation_of(span.split()[1:]) for _, span in _mentions()}
    for _, line, _ in _commands():
        words = [word for word in _filled(line)[1:] if not word.startswith("-")]
        named |= {_operation_of(words[:cut]) for cut in range(1, len(words) + 1)}
    return {name for name in named if name in _index()}


def _walk(schema: Any, definitions: dict[str, Any], prefix: str, out: dict[str, bool], names: set[str],
          seen: tuple[str, ...] = ()) -> None:
    """Every field path under `schema` into `out` (True for an object whose
    fields are not listed), and every field name and enum value into `names`."""
    if not isinstance(schema, dict):
        return
    if "$ref" in schema:
        ref = schema["$ref"].rsplit("/", 1)[-1]
        if ref not in seen:
            _walk(definitions[ref], definitions, prefix, out, names, (*seen, ref))
        return
    names.update(str(value) for value in schema.get("enum", []) if isinstance(value, str))
    if isinstance(schema.get("const"), str):
        names.add(schema["const"])
    for key in ("anyOf", "oneOf", "allOf"):
        for option in schema.get(key, []):
            _walk(option, definitions, prefix, out, names, seen)
    if "items" in schema:
        _walk(schema["items"], definitions, prefix, out, names, seen)
    properties = schema.get("properties")
    if schema.get("type") == "object" and not properties:
        out[prefix] = True
    for field, child in (properties or {}).items():
        names.add(field)
        path = f"{prefix}.{field}"
        out.setdefault(path, False)
        _walk(child, definitions, path, out, names, seen)


@cache
def _known() -> tuple[dict[str, bool], frozenset[str]]:
    paths: dict[str, bool] = {}
    names: set[str] = set()
    for operation in _operations_named():
        entry = _index()[operation]
        for kind, prefix in (("output_schema", "data"), ("input_schema", "input")):
            schema = entry[kind]
            _walk(schema, schema.get("$defs", {}), prefix, paths, names)
    brief = BriefBody.model_json_schema()
    _walk(brief, brief.get("$defs", {}), "brief", paths, names)
    # The command itself, and what the engine's types name that no schema lists.
    names |= {"roleband", *WRITTEN} | set(OUTCOMES) | set(STEPS) | set(FEEDBACK_REASONS) | ENVELOPE
    names |= set(typing.get_args(Refusal))
    return paths, frozenset(names)


def test_every_data_path_the_files_name_is_in_an_answer():
    """`data.setup.next_step` and the like: the field an assistant reads must
    be one the operation answers."""
    paths, _ = _known()
    for file, span in _all_spans():
        for path in re.findall(r"^(?:data|error)(?:\.[a-z_]+)+$", span):
            if path.startswith("error."):
                assert path.split(".")[1] in ENVELOPE, (file, path)
                continue
            parts = path.split(".")
            prefixes = [".".join(parts[:cut]) for cut in range(1, len(parts))]
            # A path under an object whose fields the schema does not list is
            # the furthest the index can vouch for.
            assert path in paths or any(paths.get(prefix) for prefix in prefixes), (file, path)


def test_every_name_the_files_put_in_code_is_one_the_engine_has():
    """A field, code or value in backticks, such as `against_baseline`,
    `needs_the_person` or `between_roles`, must exist: a verdict field the
    engine removed (a `catch`) or a code it never sends fails here."""
    paths, names = _known()
    relative = {path.split(".", 1)[1] for path in paths if "." in path}
    unknown = []
    for file, span in _all_spans():
        if re.fullmatch(r"[a-z][a-z0-9_]*", span):
            if span not in names:
                unknown.append((file, span))
        elif re.fullmatch(r"[a-z_]+(\.[a-z_]+)+", span) and not span.endswith(".md") and not span.startswith(
                ("data.", "error.")):
            if not any(path == span or path.endswith(f".{span}") for path in relative):
                unknown.append((file, span))
    assert unknown == []


def test_no_file_asks_for_a_catch():
    for name, text in FILES.items():
        assert re.search(r"\bcatch\b", text, re.IGNORECASE) is None, name


def test_each_exit_status_the_files_pair_with_a_code_is_that_codes():
    pairs = [(int(status), code) for text in FILES.values()
             for status, code in re.findall(r"exits? (\d+) with\s+`([a-z_]+)`", text)]
    assert pairs, "the files name the codes an assistant stops on"
    for status, code in pairs:
        assert code in OUTCOMES and OUTCOMES[code].exit_status == status, (status, code)


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    following = re.search(r"^## ", text[start + len(heading):], re.MULTILINE)
    return text[start: start + len(heading) + following.start()] if following else text[start:]


def _ticked(text: str) -> list[str]:
    return re.findall(r"`([a-z_]+)`", text)


def test_the_setup_steps_are_the_engines_in_its_order():
    """`connect` is done whenever the command answers, so `next_step` never
    names it; every other step has its own part, in the engine's order."""
    headings = re.findall(r"^## `([a-z_]+)`$", FILES["setup.md"], re.MULTILINE)
    assert headings == [step for step in STEPS if step != "connect"]


def test_the_pass_codes_are_the_engines():
    line = next(line for line in FILES["judging.md"].split("\n\n") if line.startswith("Pass codes:"))
    assert _ticked(line) == list(typing.get_args(PassCode))


def test_the_refusal_table_covers_every_code_the_engine_sends_and_no_other():
    table = _section(FILES["judging.md"], "## When `picks decide` refuses an item")
    body = table.split("|---|---|", 1)[1]
    rows = [row.split("|")[1] for row in body.splitlines() if row.startswith("| `")]
    named = [code for row in rows for code in _ticked(row)]
    assert sorted(named) == sorted(typing.get_args(Refusal))
    assert len(named) == len(set(named))


def test_the_rule_forms_are_the_engines():
    forms = [typing.get_args(model.model_fields["form"].annotation)[0]
             for model in typing.get_args(typing.get_args(Check)[0])]
    rules = _section(FILES["setup.md"], "## `rules`")
    paragraph = next(part for part in rules.split("\n\n") if "checkable form in `check`" in part)
    assert _ticked(paragraph.split("checkable form in `check`:")[1].split(".")[0]) == forms


def test_the_not_for_me_reasons_are_the_ones_the_app_stores():
    paragraph = next(part for part in FILES["judging.md"].split("\n\n") if "A Not for me carries why" in part)
    assert sorted(_ticked(paragraph.split("`reaction.reason`:")[1].split(", and")[0])) == sorted(FEEDBACK_REASONS)


def test_the_parts_a_run_may_change_are_the_engines():
    paragraph = next(part for part in FILES["judging.md"].split("\n\n") if "In a run you may change only" in part)
    assert sorted(_ticked(paragraph.split("change only")[1].split(";")[0])) == sorted(ROUTINE_PARTS)


# --------------------------------------------------------------------------- #
# The numbers
# --------------------------------------------------------------------------- #


def test_the_verdict_table_states_the_engines_counts_and_lengths():
    table = _section(FILES["judging.md"], "## The verdict")
    reasons = next(row for row in table.splitlines() if row.startswith("| `reasons` |"))
    pick, near_miss, passed = (cell.strip() for cell in reasons.split("|")[2:5])
    assert pick == f"{PICK_REASONS[0]} to {PICK_REASONS[1]}"
    assert NEAR_MISS_REASONS[0] == NEAR_MISS_REASONS[1] and near_miss.startswith(f"{NEAR_MISS_REASONS[0]}:")
    assert passed == "none"
    assert f"at most {REASON_MAX} characters for `opening` and `rest` together" in table
    assert f"at most {NOTE_MAX} characters" in table


def test_the_example_reason_fits_the_engines_form():
    from tracker.picks.verdicts import ReasonIn, clean_reason, sentence

    block = re.search(r"```json\n(.*?)\n```", FILES["judging.md"], re.DOTALL)
    assert block is not None
    reason = json.loads(block.group(1))
    stored = clean_reason(ReasonIn(reason["rest"], reason["brief_item"], reason["opening"]))
    assert sentence(stored) == "Staff level, one step above your Senior role today."
    assert len(sentence(stored)) <= REASON_MAX


def test_the_daily_limit_and_the_trial_are_the_engines():
    setup = FILES["setup.md"]
    assert f"You read at most {DAILY_CAP_DEFAULT:,} roles a day" in setup
    assert f"from 1 to {DAILY_CAP_MAX:,}" in setup
    assert f"{DAILY_CAP_DEFAULT:,} a day unless they\nchanged it" in FILES["SKILL.md"]
    assert f"It hands up to {TRIAL_CAP} open roles" in setup


# --------------------------------------------------------------------------- #
# The skill as a host loads it
# --------------------------------------------------------------------------- #


def test_the_skill_names_its_folder_and_its_version():
    text = FILES["SKILL.md"]
    assert text.startswith(f"---\nname: {TOP_PICKS_SKILL.name}\ndescription: ")
    assert f"<!-- {TOP_PICKS_SKILL.name} skill, version {TOP_PICKS_SKILL.version}." in text
    description = text.split("description: ", 1)[1].split("\n", 1)[0]
    # The phrases the person says, and the scheduled task's own words. The
    # app's onboarding hands the person "set up my top picks" in each language
    # it ships, so the other two are named for a host that matches on words.
    for phrase in ("set up my top picks", "update my top picks", "run the RoleBand top picks check",
                   "in any language", "configura mis destacados", "设置我的首选"):
        assert phrase in description


def test_the_routine_reads_the_next_cursor_from_the_answer_that_handed_the_batch():
    """Only the answers that hand a batch carry `next_cursor`; a routine that
    looks for it in `picks decide`'s answer finds none and closes the run
    after the first batch."""
    carrying = set()
    for operation in ("picks.begin", "picks.next", "picks.decide"):
        paths: dict[str, bool] = {}
        schema = _index()[operation]["output_schema"]
        _walk(schema, schema.get("$defs", {}), "data", paths, set())
        if "data.next_cursor" in paths:
            carrying.add(operation)
    assert carrying == {"picks.begin", "picks.next"}
    routine = _section(FILES["SKILL.md"], "## The routine")
    step = " ".join(next(step for step in re.split(r"^\d\. ", routine, flags=re.MULTILINE)
                         if "`data.next_cursor`" in step).split())
    assert "(`picks begin` or `picks next`; `picks decide` has none)" in step


def test_the_routine_applies_reactions_and_follows_the_cursor_on_an_empty_batch():
    """`picks begin` hands the reactions that came after the last finished
    run started, so a run that finishes without applying them loses them."""
    routine = _section(FILES["SKILL.md"], "## The routine")
    steps = re.split(r"^\d\. ", routine, flags=re.MULTILINE)[1:]
    reactions = next(number for number, step in enumerate(steps, 1) if "`data.reactions`" in step)
    empty = next(number for number, step in enumerate(steps, 1) if "`data.batch` is empty" in step)
    decide = next(number for number, step in enumerate(steps, 1) if "| roleband picks decide" in step)
    paging = next(number for number, step in enumerate(steps, 1) if "`data.next_cursor`" in step)
    finish = next(number for number, step in enumerate(steps, 1) if "roleband picks finish" in step)
    assert reactions < empty < decide < paging < finish
    assert f"go to step {paging}" in steps[empty - 1]
    assert f"repeat from step {empty}" in steps[paging - 1]
    assert f"If it is null, go to step {finish}" in steps[paging - 1]


def test_the_scheduled_task_asks_for_the_writes_by_name():
    """Claude's app tells a scheduled run to write only what its task asks
    for, so the task's prompt names the two writes of the routine."""
    routine = _section(FILES["setup.md"], "## `routine`")
    prompt = re.search(r'"(Run the RoleBand top picks check now\..*?)"', routine, re.DOTALL)
    assert prompt is not None
    words = " ".join(prompt.group(1).split())
    assert "`roleband picks decide`" in words and "`roleband picks finish`" in words
    assert "roleband-top-picks skill" in words


def test_the_reference_files_are_named_where_the_skill_sends_the_assistant():
    for name in TOP_PICKS_SKILL.files[1:]:
        assert f"`{name}`" in FILES["SKILL.md"], name


@pytest.mark.parametrize("name", TOP_PICKS_SKILL.files)
def test_no_file_carries_an_em_dash(name):
    assert "—" not in FILES[name]


def test_the_source_is_the_folder_connect_installs():
    assert Path(FOLDER).name == TOP_PICKS_SKILL.name
