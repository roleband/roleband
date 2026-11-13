"""The workspace's durable identity, owned by the engine.

The id is made once and never replaced: by the migration that adds the table,
or by `ensure_workspace_id` when the engine starts on a database built without
migrations. Readers only read; a request never creates it, because no GET
commits. The client never makes one.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.db.models import WorkspaceIdentity


def new_workspace_id() -> str:
    return f"ws_{uuid.uuid4().hex}"


async def get_workspace_id(session: AsyncSession) -> str | None:
    return (await session.execute(select(WorkspaceIdentity.workspace_id))).scalar_one_or_none()


async def ensure_workspace_id(session: AsyncSession) -> str:
    """The workspace id, written first if there is none. The caller commits.

    Two engines starting together on a new database both try the insert; the
    singleton key keeps the first and the second reads it back.
    """
    await session.execute(
        insert(WorkspaceIdentity)
        .values(singleton=True, workspace_id=new_workspace_id())
        .on_conflict_do_nothing(index_elements=[WorkspaceIdentity.singleton])
    )
    workspace_id = await get_workspace_id(session)
    if workspace_id is None:
        raise RuntimeError("the workspace identity row was not written")
    return workspace_id
