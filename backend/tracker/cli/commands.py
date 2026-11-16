"""`roleband <resource> <verb>`: one command per operation, from the bundled index.

Nothing here is written per operation. Each operation the engine's catalog
lists in `operations.json`, with its route, becomes a command: its dotted id
is the command's words (`opportunities.search` is `opportunities search`,
`recipes.contract.get` is `recipes contract get`, an underscore in a segment
is a hyphen), each field the route takes in its path is a positional
argument, and every other scalar or list field of its input schema is a flag
(`level_band` is `--level-band`; a list flag is repeated for more values).
`--input @FILE` or `--input -` gives the input as one JSON object, for nested
or long input and for an explicit null; path arguments and field flags add the
fields it does not carry, and a field given both ways is an error, never a
silent precedence.

The handshake operations (`status`, `capabilities`, `describe`) keep their own
commands, which answer offline too. Standard library only: `--help` builds
every command from the bundle without loading the engine's models.
"""

from __future__ import annotations

import argparse
import json
import os
import select
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

from tracker.cli.errors import ClientError

#: The prefix every agent route lives under.
PREFIX = "/api/agent/v1"
#: Operations the client answers with its own commands.
HANDSHAKE = frozenset({"status", "capabilities", "describe"})
#: Options every command or the client itself takes; no input field may claim one.
RESERVED = frozenset({
    "format", "json", "non_interactive", "context", "timeout", "help", "version", "input",
    "idempotency_key", "offline",
})
#: The most `--input` may hold, as the engine accepts.
MAX_INPUT_BYTES = 1024 * 1024
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class Field:
    name: str
    #: The JSON type a flag reads: string, integer, number or boolean.
    kind: str
    is_list: bool
    choices: tuple[str, ...] | None
    required: bool
    default: Any
    help: str | None
    #: True when the schema accepts null and declares null its default, so
    #: leaving the field out asks for exactly what a null does.
    null_default: bool = False

    @property
    def option(self) -> str:
        return "--" + self.name.replace("_", "-")


@dataclass(frozen=True)
class Command:
    operation: str
    words: tuple[str, ...]
    summary: str
    access: str
    keyed: bool
    method: str
    path: str
    #: Path fields, in the order the path names them.
    positional: tuple[Field, ...]
    flags: tuple[Field, ...]
    #: Required fields no flag can give (nested objects): only `--input` gives them.
    input_only: tuple[str, ...]


def words_of(operation: str) -> tuple[str, ...]:
    return tuple(segment.replace("_", "-") for segment in operation.split("."))


def build(bundle: dict[str, Any]) -> list[Command]:
    """A command for each operation in the bundle that is not a handshake
    operation. A bundle that cannot be laid out as commands is refused: an
    operation with no route, a field named like a client option, or two
    commands sharing words."""
    routes: dict[str, dict[str, str]] = bundle.get("routes") or {}
    built: list[Command] = []
    for entry in bundle["operations"]:
        operation = entry["operation"]
        if operation in HANDSHAKE:
            continue
        route = routes.get(operation)
        if route is None:
            raise ValueError(f"{operation} has no route in the bundle")
        built.append(_command(entry, route))
    _check_words(built)
    return built


def _command(entry: dict[str, Any], route: dict[str, str]) -> Command:
    operation = entry["operation"]
    method, path = route["method"].upper(), route["path"]
    if not path.startswith(PREFIX + "/"):
        raise ValueError(f"{operation}: its route {path!r} is not an agent route")
    schema = entry["input_schema"]
    definitions = schema.get("$defs", {})
    required = set(schema.get("required", ()))
    in_path = _path_fields(path)
    positional: list[Field] = []
    flags: list[Field] = []
    input_only: list[str] = []
    for name, prop in schema.get("properties", {}).items():
        if name in RESERVED:
            raise ValueError(f"{operation}: input field {name!r} is named like a client option")
        field = _field(name, prop, definitions, required=name in required)
        if name in in_path:
            if field is None or field.is_list:
                raise ValueError(f"{operation}: path field {name!r} is not one plain value")
            positional.append(field)
        elif field is not None:
            flags.append(field)
        elif name in required:
            input_only.append(name)
    if missing := [name for name in in_path if name not in {field.name for field in positional}]:
        raise ValueError(f"{operation}: its path names {missing}, which its input does not")
    positional.sort(key=lambda field: in_path.index(field.name))
    return Command(
        operation=operation,
        words=words_of(operation),
        summary=entry["summary"],
        access=entry["access"],
        keyed=entry["idempotency"] == "required_key",
        method=method,
        path=path,
        positional=tuple(positional),
        flags=tuple(flags),
        input_only=tuple(input_only),
    )


def _path_fields(path: str) -> list[str]:
    names = []
    for part in path.split("/"):
        if part.startswith("{") and part.endswith("}"):
            names.append(part[1:-1].split(":", 1)[0])
    return names


def _resolve(prop: dict[str, Any], definitions: dict[str, Any]) -> dict[str, Any]:
    reference = prop.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        return {**definitions.get(reference.removeprefix("#/$defs/"), {}), **{k: v for k, v in prop.items() if k != "$ref"}}
    return prop


def _scalar(prop: dict[str, Any]) -> tuple[str, tuple[str, ...] | None] | None:
    """The flag type of a scalar schema: its JSON type and, for an enum, its choices."""
    if "enum" in prop and all(isinstance(value, str) for value in prop["enum"]):
        return "string", tuple(prop["enum"])
    if "const" in prop and isinstance(prop["const"], str):
        return "string", (prop["const"],)
    kind = prop.get("type")
    if kind in ("string", "integer", "number", "boolean"):
        return kind, None
    return None


def _field(name: str, prop: dict[str, Any], definitions: dict[str, Any], *, required: bool) -> Field | None:
    """The flag for one input field, or None when only `--input` can give it."""
    every = [_resolve(option, definitions) for option in prop.get("anyOf", [prop])]
    options = [option for option in every if option.get("type") != "null"]
    null_default = len(options) < len(every) and "default" in prop and prop["default"] is None
    if len(options) != 1:
        return None
    resolved = {**options[0], **{k: v for k, v in prop.items() if k not in ("anyOf", "$ref")}}
    is_list = resolved.get("type") == "array"
    scalar = _scalar(_resolve(resolved.get("items", {}), definitions) if is_list else resolved)
    if scalar is None:
        return None
    kind, choices = scalar
    if is_list and kind == "boolean":
        return None
    return Field(
        name=name, kind=kind, is_list=is_list, choices=choices, required=required,
        default=prop.get("default"), help=prop.get("description"), null_default=null_default,
    )


def _check_words(commands: list[Command]) -> None:
    leaves = {command.words: command.operation for command in commands}
    if len(leaves) != len(commands):
        raise ValueError("two operations map to the same command")
    for words, operation in leaves.items():
        if words[0] in HANDSHAKE | {"connect"}:
            raise ValueError(f"{operation}: {words[0]!r} is already a command of its own")
        for cut in range(1, len(words)):
            if words[:cut] in leaves:
                raise ValueError(f"{operation}: {' '.join(words[:cut])!r} is both a command and a group")


# --- the parser -------------------------------------------------------------- #

_TYPES: dict[str, Callable[[str], Any]] = {"string": str, "integer": int, "number": float}


def register(
    subparsers: Any,
    commands: Iterable[Command],
    *,
    parser_class: type[argparse.ArgumentParser],
    add_globals: Callable[[argparse.ArgumentParser, str], None],
) -> None:
    """Add every command to `subparsers`, nesting one group per word."""
    groups: dict[tuple[str, ...], Any] = {(): subparsers}
    for command in sorted(commands, key=lambda command: command.words):
        for depth in range(1, len(command.words)):
            prefix = command.words[:depth]
            if prefix not in groups:
                group = groups[prefix[:-1]].add_parser(
                    prefix[-1], help=f"{' '.join(prefix)} commands", description=f"Commands on {' '.join(prefix)}.",
                    allow_abbrev=False,
                )
                group.set_defaults(group=prefix)
                add_globals(group, f"group{depth}_")
                groups[prefix] = group.add_subparsers(metavar="COMMAND", parser_class=parser_class)
        leaf = groups[command.words[:-1]].add_parser(
            command.words[-1], help=command.summary, description=command.summary, epilog=_epilog(command),
            allow_abbrev=False,
        )
        _arguments(leaf, command)
        add_globals(leaf, "leaf_")
        leaf.set_defaults(generated=command)


def _epilog(command: Command) -> str:
    access = (
        "Changes your data: it needs agent access and changes allowed in Settings. "
        "A retry under the same --idempotency-key never writes twice."
        if command.access == "write"
        else "Reads only: it needs agent access in Settings."
    )
    only = f" Give {', '.join(command.input_only)} with --input." if command.input_only else ""
    return f"Operation {command.operation}. {access}{only}"


def _arguments(parser: argparse.ArgumentParser, command: Command) -> None:
    for field in command.positional:
        # Optional to the parser so `--input` alone can give it; `payload` requires it once.
        parser.add_argument(
            f"pos_{field.name}", metavar=field.name.upper(), type=_TYPES.get(field.kind, str),
            choices=field.choices, nargs="?", default=None, help=field.help,
        )
    for field in command.flags:
        help_text = field.help or ""
        if field.is_list and "repeat" not in help_text.lower():
            help_text += " Repeat for more."
        if field.default not in (None, [], False):
            help_text += f" Default {field.default}."
        dest = f"in_{field.name}"
        if field.kind == "boolean":
            parser.add_argument(field.option, dest=dest, action=argparse.BooleanOptionalAction,
                                default=None, help=help_text.strip() or None)
            continue
        parser.add_argument(
            field.option, dest=dest, type=_TYPES[field.kind], choices=field.choices,
            action="append" if field.is_list else "store", default=None,
            metavar=None if field.choices else field.name.upper(), help=help_text.strip() or None,
        )
    parser.add_argument("--input", dest="input_source", metavar="@FILE|-", default=None,
                        help="the input as one JSON object, from a file or stdin; arguments and flags add "
                             "the fields it leaves out, and a field given both ways is refused")
    if command.keyed:
        parser.add_argument("--idempotency-key", dest="idempotency_key", metavar="KEY", default=None,
                            help="send under this key; a retry under it never writes twice (default: a new one)")


# --- a call ------------------------------------------------------------------ #


def payload(command: Command, args: argparse.Namespace, *, stdin: Any = None) -> dict[str, Any]:
    """The operation's input: `--input`'s object, with the positional arguments
    and flags adding the fields it does not carry. A field given both ways is
    refused, whatever the two values: neither silently wins."""
    given = {
        field.option: (field.name, getattr(args, f"in_{field.name}"))
        for field in command.flags
        if getattr(args, f"in_{field.name}", None) is not None
    }
    data: dict[str, Any] = {}
    if args.input_source is not None:
        data = read_input(args.input_source, stdin=stdin)
        if overlap := [(option, name) for option, (name, _) in given.items() if name in data]:
            names = ", ".join(name for _, name in overlap)
            raise ClientError(
                "invalid_arguments",
                f"{', '.join(option for option, _ in overlap)} and --input both give {names}; give each field once.",
                details={"fields": [name for _, name in overlap]},
            )
    data.update(dict(given.values()))
    if missing := [field.option for field in command.flags if field.required and field.name not in data]:
        where = ", as a flag or in --input" if args.input_source is not None else ""
        raise ClientError("invalid_arguments", f"{', '.join(missing)} is required{where}.")
    for field in command.positional:
        value = getattr(args, f"pos_{field.name}", None)
        if value is None:
            if field.name not in data:
                raise ClientError("invalid_arguments", f"{field.name.upper()} is required.")
            continue
        if field.name in data:
            raise ClientError(
                "invalid_arguments", f"{field.name} is given both as an argument and in --input; give it once.",
                details={"fields": [field.name]},
            )
        data[field.name] = value
    if missing := [name for name in command.input_only if name not in data]:
        raise ClientError("invalid_arguments", f"{', '.join(missing)} can only be given with --input.")
    return data


#: How much of an unread standard input is looked at to tell data from blank lines.
_STDIN_PEEK_BYTES = 4096


def refuse_unread_input(stream: Any) -> None:
    """Refuse a call whose standard input holds data that no `--input -` reads.

    Without it, `echo '{"location": ["London"]}' | roleband opportunities
    search` runs with no filter and answers every role. Only input already
    there counts, read without waiting: a terminal, an empty or closed pipe,
    `/dev/null`, or a pipe nothing has written to yet runs as it would
    without input, since agent hosts start commands with each of these.
    Windows pipes cannot be polled this way, so there the call runs as given."""
    if sys.platform == "win32":
        return
    try:
        descriptor = stream.fileno()
        if os.isatty(descriptor):
            return
        held = False
        seen = 0
        # Leading whitespace can fill a whole read; keep reading what is already
        # there until a non-blank byte, the end, or a pause in the input. Blank
        # input past the input limit counts as held: the scan stops undecided.
        while select.select([descriptor], [], [], 0)[0]:
            chunk = os.read(descriptor, _STDIN_PEEK_BYTES)
            if not chunk:
                break
            seen += len(chunk)
            if chunk.strip() or seen > MAX_INPUT_BYTES:
                held = True
                break
    except (AttributeError, OSError, ValueError):
        return
    if held:
        raise ClientError(
            "invalid_arguments",
            "Standard input holds data, which this command reads only with --input -; add --input - to read it.",
        )


def read_input(source: str, *, stdin: Any = None) -> dict[str, Any]:
    if source == "-":
        stream = stdin if stdin is not None else sys.stdin
        raw = stream.buffer.read(MAX_INPUT_BYTES + 1) if hasattr(stream, "buffer") else stream.read().encode("utf-8")
    elif source.startswith("@") and len(source) > 1:
        try:
            with open(source[1:], "rb") as handle:
                raw = handle.read(MAX_INPUT_BYTES + 1)
        except OSError as error:
            raise ClientError(
                "invalid_arguments", f"--input cannot read {source[1:]!r}.", details={"reason": type(error).__name__}
            ) from None
    else:
        raise ClientError("invalid_arguments", "--input takes @FILE, or - for standard input.")
    if len(raw) > MAX_INPUT_BYTES:
        raise ClientError("invalid_arguments", "--input is larger than the engine accepts (1 MiB).")
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except (UnicodeDecodeError, ValueError):
        raise ClientError("invalid_arguments", "--input is not one JSON object with unique keys in UTF-8.") from None
    if not isinstance(document, dict):
        raise ClientError("invalid_arguments", "--input is not a JSON object.")
    return document


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("a key is repeated")
    return dict(pairs)


def request(command: Command, data: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """The path, with its query, and the body to send `data` to `command`'s route."""
    rest = dict(data)
    path = command.path
    for field in command.positional:
        path = path.replace("{" + field.name + "}", quote(_text(rest.pop(field.name)), safe=""), 1)
    if command.method in _BODY_METHODS:
        return path, rest
    pairs: list[tuple[str, str]] = []
    nullable = {field.name for field in command.flags if field.null_default}
    for name, value in rest.items():
        if value is None and name in nullable:
            # The address cannot say null; leaving out a field whose default is null asks for the same.
            continue
        if value is None:
            raise ClientError(
                "invalid_arguments",
                f"{name} cannot be null: it takes a value, or has a default other than null. "
                "Leave it out or give a value.",
            )
        for item in value if isinstance(value, list) else [value]:
            if item is None or isinstance(item, dict | list):
                raise ClientError(
                    "invalid_arguments",
                    f"{name}: this operation reads its input from the address, which carries no "
                    "object, nested list or null inside a list.",
                )
            pairs.append((name, _text(item)))
    return (f"{path}?{urlencode(pairs)}" if pairs else path), None


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
