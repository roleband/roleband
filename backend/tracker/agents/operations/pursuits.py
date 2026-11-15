"""`pursuits.list` and `pursuits.get`: the person's progress on the roles they pursue.

Both read through `tracker.agents.pursuits`, the store the dashboard and every
pursuit writer share, and answer its `public_pursuit` fields, notes included,
with the pursuit's `revision`, which a write passes back.
A pursuit is addressed by its opportunity's id, never the pursuit row's.

A pursuit is the person's own record, so neither read hides one because its
company was later hidden: the Board's visibility rules decide what is offered,
not what the person already chose to pursue.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from pydantic.config import JsonDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.operations.descriptor import EngineEffects, OperationDescriptor, Shape, ToolTier
from tracker.agents.operations.envelope import OperationError
from tracker.agents.pursuits import PursuitListKey, PursuitStage, list_pursuits, public_pursuit
from tracker.db.models import Job, Pursuit

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_CONTENT: JsonDict = {"x-text": "content"}
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")

#: The page size an omitted limit reads, and the most one page holds.
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
#: The cursor's own format; a cursor of another format is refused, never guessed at.
_CURSOR_FORMAT = 1


class PursuitState(Shape):
    """One pursuit's fields as every surface shows them."""

    id: int
    #: The opportunity this pursuit is about: the id every pursuit operation takes.
    job_id: int
    stage: PursuitStage = Field(json_schema_extra=_CODE)
    priority: int = Field(ge=1, le=5)
    #: The person's own notes. Text an agent wrote here earlier reads back too.
    notes: str | None = Field(json_schema_extra=_CONTENT)
    next_action: str | None = Field(json_schema_extra=_CONTENT)
    next_action_due: datetime | None
    created_at: datetime
    updated_at: datetime
    #: Advances with every change to the pursuit, the dashboard's included. A
    #: write passes back the revision it read and is refused if it moved.
    revision: int = Field(ge=1)


class PursuedOpportunity(Shape):
    title: str = Field(json_schema_extra=_CONTENT)
    company: str = Field(json_schema_extra=_IDENTIFIER)
    status: str = Field(json_schema_extra=_CODE)
    url: str = Field(json_schema_extra=_IDENTIFIER)


class PursuitItem(PursuitState):
    opportunity: PursuedOpportunity


class PursuitListInput(Shape):
    stage: PursuitStage | None = Field(default=None, description="Only pursuits at this stage.")
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Pursuits on one page.")
    cursor: str | None = Field(
        default=None, min_length=1, max_length=512,
        description=(
            "The next_cursor of the previous page, read with the same stage. It resumes after that "
            "page's last pursuit in the current order, with no snapshot: a pursuit re-prioritised "
            "during paging can be skipped or read twice, so read from the first page for a whole list."
        ),
    )


class PursuitList(Shape):
    #: Pursuits on this page; `meta.next_cursor` reads the next one.
    count: int = Field(ge=0)
    items: list[PursuitItem]


class PursuitGetInput(Shape):
    opportunity_id: int = Field(ge=1, description="The opportunity the pursuit is about.")


PURSUITS_LIST = OperationDescriptor(
    id="pursuits.list",
    summary="List the pursuits with their stage, priority, notes and next action, by priority.",
    input=PursuitListInput,
    result=PursuitList,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("private_pursuit", "public_posting"),
    examples=({"stage": "applied", "limit": 20},),
)

PURSUITS_GET = OperationDescriptor(
    id="pursuits.get",
    summary="Read one pursuit, notes included, by the opportunity it is about.",
    input=PursuitGetInput,
    result=PursuitItem,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    data_classes=("private_pursuit", "public_posting"),
    examples=({"opportunity_id": 4821},),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (PURSUITS_LIST, PURSUITS_GET)


class _CursorBody(BaseModel):
    """What a cursor binds: its workspace and stage, and the last row read."""

    f: int
    w: str
    s: str | None
    p: int
    u: datetime
    i: int


def encode_cursor(*, workspace_id: str, stage: str | None, last: dict[str, Any]) -> str:
    body = _CursorBody(
        f=_CURSOR_FORMAT, w=workspace_id, s=stage, p=last["priority"], u=last["updated_at"], i=last["id"]
    )
    return base64.urlsafe_b64encode(body.model_dump_json().encode()).decode().rstrip("=")


def decode_cursor(cursor: str, *, workspace_id: str, stage: str | None) -> PursuitListKey:
    """The row a cursor resumes after, or `invalid_input` when it is not one of
    this workspace's cursors for this stage."""
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        body = _CursorBody.model_validate_json(raw)
    except (binascii.Error, ValueError, ValidationError):
        raise _bad_cursor("malformed") from None
    if body.f != _CURSOR_FORMAT:
        raise _bad_cursor("malformed")
    if body.w != workspace_id:
        raise _bad_cursor("other_workspace")
    if body.s != stage:
        raise _bad_cursor("other_filters")
    return PursuitListKey(priority=body.p, updated_at=body.u, id=body.i)


def _bad_cursor(reason: str) -> OperationError:
    return OperationError(
        "invalid_input",
        "This cursor does not continue this list. Read the first page again without it.",
        details={"field": "cursor", "reason": reason},
    )


async def pursuit_page(
    session: AsyncSession, params: PursuitListInput, *, workspace_id: str
) -> tuple[PursuitList, str | None]:
    """One page, and the cursor of the next when there may be one."""
    after = (
        decode_cursor(params.cursor, workspace_id=workspace_id, stage=params.stage)
        if params.cursor is not None
        else None
    )
    # One row past the page says whether another page exists, so a last page
    # that is exactly full does not hand out a cursor to an empty one.
    rows = await list_pursuits(
        session, stage=params.stage, limit=params.limit + 1, after=after, with_revision=True
    )
    page, more = rows[: params.limit], len(rows) > params.limit
    next_cursor = (
        encode_cursor(workspace_id=workspace_id, stage=params.stage, last=page[-1]) if more and page else None
    )
    return PursuitList(count=len(page), items=[PursuitItem.model_validate(row) for row in page]), next_cursor


async def pursuit_of(session: AsyncSession, opportunity_id: int) -> PursuitItem:
    row = (
        await session.execute(
            select(Pursuit, Job).join(Job, Job.id == Pursuit.job_id).where(Pursuit.job_id == opportunity_id)
        )
    ).first()
    if row is None:
        raise OperationError(
            "not_found",
            "There is no pursuit for this opportunity.",
            details={"opportunity_id": opportunity_id},
        )
    pursuit, job = row
    return PursuitItem.model_validate(state_of(pursuit, job))


def state_of(pursuit: Pursuit, job: Job | None = None) -> dict[str, Any]:
    """A pursuit's public fields and its revision, from one read of its row."""
    return {**public_pursuit(pursuit, job), "revision": pursuit.revision}
