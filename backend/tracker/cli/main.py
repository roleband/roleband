"""Parse, call one operation, print one envelope, exit with its status.

Global options may come before the command or after it; the same option given
twice with different values is an error. `ROLEBAND_AGENT=1` selects JSON and
non-interactive behaviour unless a flag says otherwise. Every failure, the
parser's included, is an envelope in the selected format with the exit status
of its code.
"""

from __future__ import annotations

import argparse
import errno
import io
import json
import os
import re
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NoReturn, TextIO, cast

from tracker.agents.operations.outcomes import CONTRACT_VERSION, EXIT_OK, outcome
from tracker.cli.errors import (
    PARSE_OPERATION,
    ClientError,
    error_envelope,
    new_request_id,
    success_envelope,
)
from tracker.cli.render import write_human, write_json

AGENT_ENV = "ROLEBAND_AGENT"
FORMATS = ("human", "json", "ndjson")
TIERS = ("small", "standard", "full")
DEFAULT_TIMEOUT = 15.0
MAX_TIMEOUT = 3600.0
BUNDLE = Path(__file__).with_name("operations.json")
_DURATION = re.compile(r"^(\d+(?:\.\d+)?)(ms|s|m)?$")
#: The engine's own rule for an operation id (`descriptor.OPERATION_ID`).
_OPERATION_ID = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
_GLOBALS = ("format", "non_interactive", "context", "timeout")

EPILOG = """\
Contexts: --context NAME selects an engine from the context file
(ROLEBAND_CLI_CONFIG, else ~/.config/roleband/cli.json). There is no default
engine. Exit status: 0 ok, 1 internal, 2 invalid input, 3 engine unavailable,
4 refused by settings, 5 not found, 6 conflict, 7 input required,
8 deadline, 9 partial, 10 incompatible, 130 interrupted.
"""


class UsageError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    """Raises instead of printing usage and exiting, so the selected format holds."""

    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


def _duration(text: str) -> float:
    match = _DURATION.fullmatch(text.strip())
    if not match:
        raise argparse.ArgumentTypeError(f"{text!r} is not a duration such as 15s, 500ms or 2m")
    value = float(match.group(1)) * {"ms": 0.001, "s": 1.0, "m": 60.0, None: 1.0}[match.group(2)]
    if not 0 < value <= MAX_TIMEOUT:
        raise argparse.ArgumentTypeError(f"a timeout is more than 0 and at most {MAX_TIMEOUT:g}s")
    return value


def _operation_id(text: str) -> str:
    if len(text) > 128 or not _OPERATION_ID.fullmatch(text):
        raise argparse.ArgumentTypeError(f"{text!r} is not an operation id such as opportunities.search")
    return text


class _Once(argparse.Action):
    """Stores a value; the same option again with another value is an error."""

    def __call__(self, parser: argparse.ArgumentParser, namespace: argparse.Namespace,
                 values: Any, option_string: str | None = None) -> None:
        value = self.const if self.nargs == 0 else values
        previous = getattr(namespace, self.dest, None)
        if previous is not None and previous != value:
            raise UsageError(f"{option_string} is given twice with different values")
        setattr(namespace, self.dest, value)


def _add_globals(parser: argparse.ArgumentParser, prefix: str) -> None:
    group = parser.add_argument_group("global options")
    group.add_argument("--format", dest=f"{prefix}format", choices=FORMATS, action=_Once, default=None,
                       help="human, json or ndjson (default: human on a terminal, else json)")
    group.add_argument("--json", dest=f"{prefix}format", action=_Once, nargs=0, const="json", default=None,
                       help="same as --format json")
    group.add_argument("--non-interactive", dest=f"{prefix}non_interactive", action=_Once, nargs=0, const=True,
                       default=None, help="never prompt or open anything")
    group.add_argument("--context", dest=f"{prefix}context", action=_Once, default=None, metavar="NAME",
                       help="the named engine to call")
    group.add_argument("--timeout", dest=f"{prefix}timeout", action=_Once, type=_duration, default=None,
                       metavar="DURATION", help="total deadline, such as 15s (default 15s)")


def build_parser() -> Parser:
    parser = Parser(prog="roleband", description="Reach your local engine from scripts and agents.",
                    epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    parser.add_argument("--version", action="store_true", help="print the client version and exit")
    _add_globals(parser, "")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", parser_class=Parser)

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_text, description=help_text, allow_abbrev=False)
        _add_globals(sub, "leaf_")
        return sub

    command("status", "Name the workspace and engine this context reaches.")
    capabilities = command("capabilities", "List the operations the engine offers.")
    capabilities.add_argument("--offline", action="store_true", help="read the bundled index; ask no engine")
    capabilities.add_argument("--tier", choices=TIERS, help="only the operations in this tool tier")
    describe = command("describe", "Describe one operation's schemas and effects.")
    describe.add_argument("operation", metavar="OPERATION", type=_operation_id,
                          help="a dotted operation id, such as status")
    describe.add_argument("--offline", action="store_true", help="read the bundled index; ask no engine")
    return parser


def _usage(parser: argparse.ArgumentParser) -> str:
    return " ".join(parser.format_usage().split())


def _merge_globals(args: argparse.Namespace) -> None:
    for name in _GLOBALS:
        top, leaf = getattr(args, name, None), getattr(args, f"leaf_{name}", None)
        if top is not None and leaf is not None and top != leaf:
            raise UsageError(f"--{name.replace('_', '-')} is given twice with different values")
        setattr(args, name, leaf if leaf is not None else top)


def _format_hint(argv: Sequence[str], environ: dict[str, str], stdout: TextIO) -> str:
    """The format to answer a parse failure in, read without the parser."""
    for index, token in enumerate(argv):
        if token == "--json":
            return "json"
        if token == "--format" and index + 1 < len(argv) and argv[index + 1] in FORMATS:
            return argv[index + 1]
        if token.startswith("--format=") and token.split("=", 1)[1] in FORMATS:
            return token.split("=", 1)[1]
    return _default_format(environ, stdout)


def _default_format(environ: dict[str, str], stdout: TextIO) -> str:
    if environ.get(AGENT_ENV) == "1":
        return "json"
    return "human" if _isatty(stdout) else "json"


def _isatty(stream: TextIO) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def _attempted(argv: Sequence[str]) -> str:
    known = {"status", "capabilities", "describe"}
    for token in argv:
        if token in known:
            return token
    return PARSE_OPERATION


def _version() -> str:
    from tracker import __version__

    return __version__


def _bundle() -> dict[str, Any]:
    try:
        document = json.loads(BUNDLE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ClientError("internal_error", "The client's bundled operation index is missing or damaged.") from None
    if document.get("format") != 1 or document.get("contract_version") != CONTRACT_VERSION:
        raise ClientError("internal_error", "The client's bundled operation index is from another contract.")
    operations: list[dict[str, Any]] = document["operations"]
    return {entry["operation"]: entry for entry in operations}


def _offline_capabilities(args: argparse.Namespace) -> dict[str, Any]:
    keys = ("operation", "summary", "access", "availability", "engine_effects", "client_effects",
            "data_classes", "tool_tiers", "idempotency")
    return {
        "contract_version": CONTRACT_VERSION,
        "supported_contract_versions": [CONTRACT_VERSION],
        "engine_version": None,
        "metadata_source": "bundled",
        "operations": [
            {key: entry[key] for key in keys}
            for entry in _bundle().values()
            if args.tier is None or args.tier in entry["tool_tiers"]
        ],
    }


def _offline_describe(args: argparse.Namespace) -> dict[str, Any]:
    entry = _bundle().get(args.operation)
    if entry is None:
        raise ClientError(
            "unknown_operation",
            "This client knows no operation by that name.",
            details={"operation": args.operation},
            next_actions=[{"operation": "capabilities", "arguments": {}}],
        )
    return entry


def _live(args: argparse.Namespace, request_id: str) -> dict[str, Any]:
    from tracker.cli import contexts, transport

    if args.command == "status":
        path = transport.path_for("status")
    elif args.command == "capabilities":
        path = transport.path_for("capabilities", query={"tier": args.tier} if args.tier else None)
    else:
        path = transport.path_for("operations", args.operation)
    context = contexts.resolve(args.context)
    deadline = time.monotonic() + (args.timeout or DEFAULT_TIMEOUT)
    envelope = transport.get(context, path, operation=args.command, deadline=deadline,
                             request_id=request_id, user_agent=f"roleband/{_version()}")
    answered = envelope.get("workspace_id")
    # A pinned context accepts a success only from its own workspace; an
    # engine that cannot name one yet may still answer with a failure.
    if context.workspace_id is not None and answered != context.workspace_id and (
        answered is not None or envelope["ok"] is True
    ):
        raise ClientError(
            "workspace_mismatch",
            f"Context {context.name!r} is pinned to another workspace than the one that answered.",
            details={"context": context.name, "expected": context.workspace_id,
                     "answered": answered},
        )
    meta = envelope.get("meta")
    if isinstance(meta, dict):
        meta["context"] = {"name": context.name, "url": context.url, "discovery": "configured"}
    return envelope


_OFFLINE: dict[str, Callable[[argparse.Namespace], dict[str, Any]]] = {
    "capabilities": _offline_capabilities,
    "describe": _offline_describe,
}


def run(argv: Sequence[str], *, stdout: TextIO, stderr: TextIO, environ: dict[str, str]) -> int:
    request_id = new_request_id()
    fmt = _format_hint(argv, environ, stdout)
    operation = _attempted(argv)
    try:
        parser = build_parser()
        try:
            args = parser.parse_args(list(argv))
            _merge_globals(args)
        except UsageError as error:
            raise ClientError("invalid_arguments", str(error), details={"usage": _usage(parser)}) from None
        if args.version:
            stdout.write(f"roleband {_version()} (contract {CONTRACT_VERSION})\n")
            return EXIT_OK
        if args.command is None:
            raise ClientError("invalid_arguments", "Name a command.", details={"usage": _usage(parser)})
        operation = args.command
        if args.format is None:
            args.format = _default_format(environ, stdout)
        fmt = args.format
        if fmt == "ndjson":
            raise ClientError("invalid_arguments", f"{operation} answers one object, not a stream; use --format json.")
        if getattr(args, "offline", False):
            envelope = success_envelope(operation, _OFFLINE[operation](args), request_id=request_id)
        else:
            envelope = _live(args, request_id)
    except ClientError as error:
        envelope = error_envelope(operation, error, request_id=request_id)
    except KeyboardInterrupt:
        envelope = error_envelope(
            operation, ClientError("interrupted", "Interrupted. Work the engine accepted continues."),
            request_id=request_id,
        )
    status = EXIT_OK if envelope["ok"] else outcome(envelope["error"]["code"]).exit_status
    if fmt == "human":
        write_human(envelope, stdout, stderr)
    else:
        write_json(envelope, stdout)
    return status


def _silence_stdout() -> None:
    # The reader went away. Point stdout at nothing so the interpreter's final
    # flush cannot raise again.
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError):
        pass


def main(argv: Sequence[str] | None = None) -> int:
    """Run `roleband`. A closed pipe ends it quietly with the outcome it had:
    closing the reader cancels nothing the engine accepted."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    real = sys.stdout
    guarded = _Guarded(real)
    # argparse prints --help to sys.stdout itself.
    sys.stdout = guarded
    try:
        status = run(arguments, stdout=cast(TextIO, guarded), stderr=sys.stderr, environ=dict(os.environ))
    except SystemExit as exit_:
        status = exit_.code if isinstance(exit_.code, int) else EXIT_OK
    finally:
        sys.stdout = real
    if guarded.broken:
        _silence_stdout()
    return status


def _reader_gone(error: OSError) -> bool:
    # Windows reports a write to a pipe whose reader closed as EINVAL, not EPIPE.
    if isinstance(error, BrokenPipeError):
        return True
    return sys.platform == "win32" and error.errno == errno.EINVAL


class _Guarded(io.TextIOBase):
    """stdout that records a closed pipe instead of raising it."""

    def __init__(self, stream: TextIO) -> None:
        super().__init__()
        self._stream = stream
        self.broken = False

    def write(self, text: str) -> int:
        if self.broken:
            return len(text)
        try:
            return self._stream.write(text)
        except OSError as error:
            if not _reader_gone(error):
                raise
            self.broken = True
            return len(text)

    def flush(self) -> None:
        if self.broken:
            return
        try:
            self._stream.flush()
        except OSError as error:
            if not _reader_gone(error):
                raise
            self.broken = True

    def isatty(self) -> bool:
        return _isatty(self._stream)
