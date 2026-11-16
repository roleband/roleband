"""`--output FILE`: an operation whose answer is a document writes it to a file.

Only an operation that declares the `file_write` client effect takes
`--output`, and only one this module knows how to lay out as a file
(`WRITERS`); the bundle is refused otherwise. The client reads every part of
the answer, checks it against the hash the engine gave, and only then writes
it: whole and at once, never over a file that is there unless `--overwrite`
says so. The envelope then names the file, its size and its hash in place of
the content, which stays out of the caller's context.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tracker.cli.errors import ClientError

#: Reads the next part of an answer from a `continue_with` call's arguments.
Follow = Callable[[dict[str, Any]], dict[str, Any]]
#: Lays one operation's answer out as the bytes of a file, reading any further
#: parts with `Follow`: the bytes and what the envelope says beside the file.
Writer = Callable[[dict[str, Any], Follow], tuple[bytes, dict[str, Any]]]


def _context_packet(data: dict[str, Any], follow: Follow) -> tuple[bytes, dict[str, Any]]:
    """The whole packet, joined from its parts and checked against its manifest."""
    manifest = data["manifest"]
    parts = [data["packet"]]
    read = data["packet_offset"] + len(data["packet"])
    while data["continue_with"]:
        [action] = data["continue_with"]
        envelope = follow(dict(action["arguments"]))
        if not envelope["ok"]:
            raise _Failed(envelope)
        data = envelope["data"]
        if data["packet_offset"] != read or data["manifest"]["packet_sha256"] != manifest["packet_sha256"]:
            raise _unverified()
        if not data["packet"] and data["continue_with"]:
            raise _unverified()
        parts.append(data["packet"])
        read += len(data["packet"])
    text = "".join(parts)
    content = text.encode("utf-8")
    if len(text) != manifest["packet_chars"] or hashlib.sha256(content).hexdigest() != manifest["packet_sha256"]:
        raise _unverified()
    return content, {"manifest": manifest}


#: The operations whose answer `--output` writes, and how.
WRITERS: dict[str, Writer] = {"context.export": _context_packet}
#: The input fields that ask for part of a document; `--output` writes it whole.
_PART_FIELDS: dict[str, tuple[str, ...]] = {"context.export": ("packet_from", "packet_sha256")}


class _Failed(Exception):
    """A later part was refused; its envelope is the answer."""

    def __init__(self, envelope: dict[str, Any]) -> None:
        super().__init__(envelope["error"]["message"])
        self.envelope = envelope


def _unverified() -> ClientError:
    return ClientError(
        "internal_error",
        "The parts the engine sent do not join into the document its manifest names; nothing was written.",
    )


def destination(path: str, *, operation: str, data: dict[str, Any], overwrite: bool) -> Path:
    """Where `--output` writes, checked before the engine is asked: a folder
    that exists, and no file there unless `--overwrite`."""
    if given := [name for name in _PART_FIELDS.get(operation, ()) if data.get(name) is not None]:
        raise ClientError(
            "invalid_arguments",
            f"--output writes the whole document; leave out {', '.join(given)}.",
            details={"fields": given},
        )
    target = Path(path).expanduser()
    if target.is_dir():
        raise ClientError("invalid_arguments", "--output names a folder; give a file name in it.",
                          details={"path": str(target)})
    if not target.parent.is_dir():
        raise ClientError("invalid_arguments", "--output names a file in a folder that does not exist.",
                          details={"path": str(target)})
    if not overwrite and os.path.lexists(target):
        raise _exists(target)
    return target


def _exists(target: Path) -> ClientError:
    return ClientError(
        "invalid_arguments", "--output names a file that is already there; add --overwrite to replace it.",
        details={"path": str(target), "reason": "exists"},
    )


def write(
    envelope: dict[str, Any], target: Path, *, overwrite: bool, follow: Follow,
) -> dict[str, Any]:
    """`envelope` written to `target`, and the envelope that says so. A
    failure on a later part is the answer, with nothing written."""
    try:
        content, beside = WRITERS[envelope["operation"]](envelope["data"], follow)
    except _Failed as failed:
        return failed.envelope
    except (KeyError, TypeError, ValueError):
        raise ClientError(
            "contract_incompatible", "The engine's answer is not the document this client writes; nothing was written.",
        ) from None
    write_atomically(target, content, overwrite=overwrite)
    data = {
        "path": str(target.resolve()),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        **beside,
    }
    return {**envelope, "data": data}


def write_atomically(target: Path, content: bytes, *, overwrite: bool) -> None:
    """Write `content` to `target` whole or not at all: a reader sees the old
    file or none, then the new one, never part of it. Without `overwrite` a
    file already there, even one that appeared while this one was written, is
    refused. The file is readable by its owner only, as it holds the person's
    own records."""
    try:
        descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".part")
    except OSError as error:
        raise _unwritable(target, error) from None
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            _place_new(temporary, target)
    except FileExistsError:
        raise _exists(target) from None
    except OSError as error:
        raise _unwritable(target, error) from None
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def _unwritable(target: Path, error: OSError) -> ClientError:
    return ClientError(
        "invalid_arguments", "--output cannot write that file.",
        details={"path": str(target), "reason": type(error).__name__},
    )


def _place_new(temporary: str, target: Path) -> None:
    """Move `temporary` to `target`, refusing a `target` that exists, in one
    step: Windows refuses to rename onto a file, and a hard link refuses an
    existing name. A file system with no hard links gets a name reserved
    first and then replaced, so the file may show empty for that moment."""
    if sys.platform == "win32":
        os.rename(temporary, target)
        return
    try:
        os.link(temporary, target)
    except FileExistsError:
        raise
    except OSError:
        os.close(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        try:
            os.replace(temporary, target)
        except OSError:
            os.unlink(target)
            raise
