"""An operation that carries a file: the client reads it from the person's disk.

`background add-document --file PATH` is the only way a file reaches the
engine. The client sends the file's name and its bytes as they are, reads no
more than the engine stores, and offers `--file` on no other command.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import threading

import pytest

from tracker.agents.operations.background import BACKGROUND_ADD_DOCUMENT, MAX_DOCUMENT_BODY_BYTES
from tracker.agents.operations.outcomes import EXIT_INVALID, outcome
from tracker.cli import commands
from tracker.cli.errors import ClientError
from tracker.cli.main import BUNDLE, UsageError, build_parser
from tracker.picks.background import MAX_DOCUMENT_BYTES

CV = b"%PDF-1.7\nDana Reyes, Senior Product Manager\n\x00\xff binary tail"


def _bundle() -> dict:
    return json.loads(BUNDLE.read_text(encoding="utf-8"))


def _command() -> commands.Command:
    return next(command for command in commands.build(_bundle()) if command.operation == BACKGROUND_ADD_DOCUMENT.id)


def _payload(*argv: str) -> dict:
    args = build_parser().parse_args(["background", "add-document", *argv])
    return commands.payload(args.generated, args)


def _refused(*argv: str) -> ClientError:
    with pytest.raises(ClientError) as refused:
        _payload(*argv)
    assert refused.value.code == "invalid_arguments" and outcome(refused.value.code).exit_status == EXIT_INVALID
    return refused.value


def test_the_file_is_sent_under_its_own_name_with_its_bytes_as_they_are(tmp_path):
    path = tmp_path / "Dana Reyes CV.pdf"
    path.write_bytes(CV)

    data = _payload("--file", str(path))

    assert data == {"filename": "Dana Reyes CV.pdf", "content_base64": base64.b64encode(CV).decode()}
    assert base64.b64decode(data["content_base64"]) == CV
    sent_to, body = commands.request(_command(), data)
    assert (sent_to, body) == ("/api/agent/v1/background/documents", data), "the file travels in the body, not the address"


def test_the_client_reads_no_more_than_the_engine_stores(tmp_path, monkeypatch):
    assert commands.MAX_FILE_BYTES == MAX_DOCUMENT_BYTES
    monkeypatch.setattr(commands, "MAX_FILE_BYTES", len(CV))
    fits, over = tmp_path / "cv.pdf", tmp_path / "long.pdf"
    fits.write_bytes(CV)
    over.write_bytes(CV + b"!")

    assert base64.b64decode(_payload("--file", str(fits))["content_base64"]) == CV
    assert "larger than" in _refused("--file", str(over)).message


def test_a_file_given_in_input_has_the_room_the_engine_gives_that_command(tmp_path, monkeypatch):
    assert commands.MAX_FILE_INPUT_BYTES == MAX_DOCUMENT_BODY_BYTES
    # A file well within what the engine stores, larger than any other command's input once in base64.
    cv = CV + b"\x00" * (900 * 1024)
    document = {"filename": "cv.pdf", "content_base64": base64.b64encode(cv).decode()}
    path = tmp_path / "input.json"
    path.write_text(json.dumps(document))
    assert path.stat().st_size > commands.MAX_INPUT_BYTES

    assert _payload("--input", f"@{path}") == document
    with pytest.raises(ClientError, match="larger than"):
        commands.read_input(f"@{path}")  # another command's bound
    monkeypatch.setattr(commands, "MAX_FILE_INPUT_BYTES", path.stat().st_size - 1)
    assert "larger than" in _refused("--input", f"@{path}").message


def test_a_file_that_is_missing_or_empty_is_refused_before_anything_is_sent(tmp_path):
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")

    assert "cannot read" in _refused("--file", str(tmp_path / "no-such.pdf")).message
    assert "is empty" in _refused("--file", str(empty)).message
    assert "cannot read" in _refused("--file", str(tmp_path)).message, "a folder is not a file"


def test_the_file_is_required_and_given_once(tmp_path):
    path, given = tmp_path / "cv.pdf", tmp_path / "input.json"
    path.write_bytes(CV)
    given.write_text(json.dumps({"filename": "other.pdf", "content_base64": base64.b64encode(b"other").decode()}))

    assert "--file is required" in _refused().message
    assert _refused("--file", str(path), "--input", f"@{given}").details == {"fields": ["filename", "content_base64"]}
    # `--input` alone still carries a whole request, as for any operation.
    assert _payload("--input", f"@{given}")["filename"] == "other.pdf"


def test_a_second_file_is_refused_rather_than_sent_in_place_of_the_first(tmp_path):
    first, second = tmp_path / "cv.pdf", tmp_path / "other.pdf"
    first.write_bytes(CV)
    second.write_bytes(b"%PDF-1.7 someone else")

    assert "more than once" in _refused("--file", str(first), "--file", str(second)).message


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes are POSIX")
def test_a_named_pipe_is_refused_at_once_rather_than_waited_on(tmp_path):
    pipe = tmp_path / "cv.pdf"
    os.mkfifo(pipe)
    refusals: list[ClientError] = []

    def read() -> None:
        with pytest.raises(ClientError) as refused:
            _payload("--file", str(pipe))
        refusals.append(refused.value)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    reader.join(timeout=5)
    if reader.is_alive():
        # Release the reader that waits for a writer, so the test ends.
        os.close(os.open(pipe, os.O_WRONLY | os.O_NONBLOCK))
        reader.join(timeout=5)
        pytest.fail("the command waited on a pipe with no writer")
    assert [error.message for error in refusals] == [f"--file: cannot read {pipe} (not a regular file)."]


def test_only_an_operation_that_reads_a_file_takes_one(tmp_path):
    reads_file = [command.operation for command in commands.build(_bundle()) if command.reads_file]
    assert reads_file == [BACKGROUND_ADD_DOCUMENT.id]
    assert not [field.name for field in _command().flags if field.name in commands.FILE_FIELDS], (
        "no flag takes the bytes"
    )

    with pytest.raises(UsageError, match="unrecognized arguments: --file"):
        build_parser().parse_args(["picks", "begin", "--file", str(tmp_path / "cv.pdf")])


def test_a_bundle_whose_file_operation_has_nowhere_to_put_the_file_is_refused():
    bundle = copy.deepcopy(_bundle())
    entry = next(entry for entry in bundle["operations"] if entry["operation"] == BACKGROUND_ADD_DOCUMENT.id)
    del entry["input_schema"]["properties"]["content_base64"]
    entry["input_schema"]["required"].remove("content_base64")

    with pytest.raises(ValueError, match="content_base64"):
        commands.build(bundle)
