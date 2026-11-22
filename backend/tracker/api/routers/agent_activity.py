"""The Activity screen's list: every agent read, change and refusal, newest first.

Pages of 50 by keyset (`cursor` is the previous page's `next_cursor`), so rows
an assistant adds while the person reads never shift a page. One entry is also
read by its id, for a link to an entry that is not on the loaded page. The rows are
written by the agent operations (`tracker/agents/activity.py`); this route
only reads them.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from pydantic import AwareDatetime

from tracker.agents.activity import (
    MAX_PAGE_SIZE,
    PAGE_SIZE,
    ActivityQuery,
    BadCursor,
    activity_page,
)
from tracker.agents.operations.descriptor import DataClass
from tracker.api.deps import SessionDep
from tracker.api.errors import ErrorCode, api_error
from tracker.api.schemas.agent_activity import (
    ActivityEntry,
    ActivityFieldChange,
    ActivityPageResponse,
)
from tracker.db.models import AgentActivity

router = APIRouter(tags=["agent-activity"])


def _entry(row: AgentActivity) -> ActivityEntry:
    return ActivityEntry(
        id=row.id,
        occurred_at=row.occurred_at,
        operation=row.operation,
        kind=row.kind,  # type: ignore[arg-type]
        categories=list(row.categories),
        action_group=row.action_group,
        refusal=row.refusal,
        summary=row.summary,
        subject=dict(row.subject),
        changes=[ActivityFieldChange.model_validate(change) for change in row.changes or ()],
        host=row.host,  # type: ignore[arg-type]
    )


@router.get("/api/agent-activity", response_model=ActivityPageResponse)
async def agent_activity(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    kind: Literal["all", "change", "read", "refused"] = "all",
    category: DataClass | None = None,
    host: Literal["claude-code", "codex", "other"] | None = None,
    since: AwareDatetime | None = None,
    until: AwareDatetime | None = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = PAGE_SIZE,
) -> ActivityPageResponse:
    query = ActivityQuery(
        q=q, kind=kind, category=category, host=host, since=since, until=until, cursor=cursor, limit=limit
    )
    try:
        page = await activity_page(session, query)
    except BadCursor:
        raise api_error(422, ErrorCode.INVALID_INPUT, "cursor is not one this list made", field="cursor") from None
    return ActivityPageResponse(items=[_entry(row) for row in page.rows], next_cursor=page.next_cursor)



@router.get("/api/agent-activity/{entry_id}", response_model=ActivityEntry)
async def agent_activity_entry(
    session: SessionDep,
    entry_id: Annotated[int, Path(ge=1, le=2**63 - 1)],
) -> ActivityEntry:
    row = await session.get(AgentActivity, entry_id)
    if row is None:
        raise api_error(404, ErrorCode.ACTIVITY_ENTRY_NOT_FOUND, "activity entry not found")
    return _entry(row)
