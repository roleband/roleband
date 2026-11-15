"""Offset cursors for list operations whose order is not a keyset.

A cursor is opaque to the caller and short, since it travels in every page:
its format, the position to resume at, any count the operation needs to
resume, and a digest of the workspace and the request it continues. One read
with other filters, in another workspace, or of another format is refused as
`invalid_input`, never reinterpreted. A list read this way is live, not a
snapshot: a row that is added, removed or re-sorted between two pages can be
missed or repeated.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from tracker.agents.operations.envelope import OperationError

#: The cursor's own format; a cursor of another format is refused, never guessed at.
_FORMAT = "c1"
_CURSOR = re.compile(r"^c1\.(\d{1,9})\.(\d{1,9})\.([0-9a-f]{16})$")


def fingerprint(operation: str, workspace_id: str, request: dict[str, Any]) -> str:
    """A digest of where and what a page was asked for, paging fields left out by the caller."""
    canonical = json.dumps([operation, workspace_id, request], sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def encode(*, request: str, offset: int, carried: int = 0) -> str:
    return f"{_FORMAT}.{offset}.{carried}.{request}"


def decode(cursor: str, *, request: str) -> tuple[int, int]:
    """The position a cursor resumes at and the count it carries, or
    `invalid_input` when it is not a cursor for this same request."""
    match = _CURSOR.fullmatch(cursor)
    if match is None:
        raise _refused("malformed")
    if match.group(3) != request:
        raise _refused("other_request")
    return int(match.group(1)), int(match.group(2))


def _refused(reason: str) -> OperationError:
    return OperationError(
        "invalid_input",
        "This cursor does not continue this list. Read the first page again without it, with the same filters.",
        details={"field": "cursor", "reason": reason},
    )
