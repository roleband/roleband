"""Who the person is: the reading of their background, and the file it came from.

A reading is one JSON object (`Reading`) an assistant builds from a CV or from
what the person said. It is the person's own statement only once they confirm
it. Each save is a new version; the one before is kept and marked superseded.

The original file, when the person gave one, is stored beside the database in
the data folder's `documents` directory under a name the engine makes, and the
engine never parses it. The file is written before its row commits, so a
write that rolls back can leave a file no row names. Removal deletes the file
before its row, so a CV is never left on disk by a removal that then failed:
such a row names a file that is gone, and removing again clears it.

Nothing here commits: the caller owns the transaction.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.db.models import CandidateBackground, CandidateDocument
from tracker.picks.lock import lock_picks
from tracker.platform.paths import DATA_DIR

Source = Literal["document", "spoken", "minimal"]
#: The largest file the engine stores.
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
#: The kinds of file a CV comes as, by extension, with the media type recorded.
DOCUMENT_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".rtf": "application/rtf",
    ".txt": "text/plain",
    ".md": "text/markdown",
}

Words = Annotated[str, Field(min_length=1, max_length=300)]


class _Part(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CurrentRole(_Part):
    title: str | None = Field(default=None, max_length=200)
    employer: str | None = Field(default=None, max_length=200)
    since: str | None = Field(default=None, max_length=40)
    level: str | None = Field(default=None, max_length=80, description="As the person states it.")


class EarlierRole(_Part):
    title: Words
    employer: str | None = Field(default=None, max_length=200)
    years: str | None = Field(default=None, max_length=40)
    line: str | None = Field(default=None, max_length=300)


class Reading(_Part):
    """What an assistant read of the person's background."""

    current: CurrentRole | None = None
    history: list[EarlierRole] = Field(default_factory=list, max_length=6)
    years: float | None = Field(default=None, ge=0, le=70, description="Total years of experience.")
    strengths: list[Words] = Field(default_factory=list, max_length=8)
    scope: str | None = Field(default=None, max_length=600, description="People, budgets and scale, where stated.")
    places: list[Words] = Field(default_factory=list, max_length=12)
    education: list[Words] = Field(default_factory=list, max_length=8)
    languages: list[Words] = Field(default_factory=list, max_length=8)
    gaps: list[Words] = Field(default_factory=list, max_length=12, description="What could not be established.")


class DocumentError(Exception):
    """A file the engine does not store. `code` is `too_large`, `empty`,
    `unsupported_type` or `unknown_document`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def documents_dir() -> Path:
    return DATA_DIR / "documents"


async def newest(session: AsyncSession) -> CandidateBackground | None:
    """The reading that stands: the newest version."""
    return await session.scalar(
        select(CandidateBackground).order_by(CandidateBackground.version.desc()).limit(1)
    )


async def document(session: AsyncSession, document_id: int) -> CandidateDocument | None:
    row = await session.get(CandidateDocument, document_id)
    return row if row is not None and row.removed_at is None else None


async def save_reading(
    session: AsyncSession,
    reading: Reading,
    *,
    source: Source,
    document_id: int | None,
    confirmed: bool,
    host: str | None,
    now: datetime,
) -> CandidateBackground:
    """Save `reading` as the next version and supersede the one before."""
    await lock_picks(session)
    if document_id is not None and await document(session, document_id) is None:
        raise DocumentError("unknown_document", "There is no stored document by that id.")
    before = await session.scalar(
        select(CandidateBackground).where(CandidateBackground.superseded_at.is_(None)).with_for_update()
    )
    number = int(await session.scalar(select(func.coalesce(func.max(CandidateBackground.version), 0))) or 0) + 1
    if before is not None:
        before.superseded_at = now
    row = CandidateBackground(
        version=number, reading=reading.model_dump(mode="json", exclude_none=True), source=source,
        document_id=document_id, confirmed_at=now if confirmed else None, host=host, created_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def store_document(
    session: AsyncSession, *, filename: str, content: bytes, now: datetime, directory: Path | None = None,
) -> tuple[CandidateDocument, bool]:
    """Store one file and its row, and say whether anything was stored: the
    same bytes given again answer the row they already have, and write nothing."""
    name = Path(filename.replace("\\", "/")).name.strip()
    media_type = DOCUMENT_TYPES.get(Path(name).suffix.lower())
    if not name or media_type is None:
        raise DocumentError(
            "unsupported_type", f"A background document is one of {', '.join(sorted(DOCUMENT_TYPES))}."
        )
    if not content:
        raise DocumentError("empty", "The file is empty.")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise DocumentError("too_large", f"The file is larger than {MAX_DOCUMENT_BYTES // (1024 * 1024)} MiB.")
    await lock_picks(session)
    digest = hashlib.sha256(content).hexdigest()
    held = await session.scalar(
        select(CandidateDocument).where(CandidateDocument.sha256 == digest, CandidateDocument.removed_at.is_(None))
    )
    if held is not None:
        return held, False
    folder = directory or documents_dir()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    stored_name = f"{digest[:16]}-{secrets.token_hex(4)}{Path(name).suffix.lower()}"
    path = folder / stored_name
    # Created for this account only, and never over a file already there.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
    _unlink_unless_committed(session, path)
    row = CandidateDocument(
        filename=name[:255], media_type=media_type, size_bytes=len(content), sha256=digest,
        stored_name=stored_name, added_at=now,
    )
    session.add(row)
    try:
        await session.flush()
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return row, True


def _unlink_unless_committed(session: AsyncSession, path: Path) -> None:
    """Delete the file at `path` if the transaction that names it rolls back,
    so no document stays on disk without the row Remove reads."""
    committed = False

    def keep(_session: object) -> None:
        nonlocal committed
        committed = True

    def drop(_session: object) -> None:
        if not committed:
            path.unlink(missing_ok=True)

    event.listen(session.sync_session, "after_commit", keep, once=True)
    event.listen(session.sync_session, "after_rollback", drop, once=True)


async def remove_all(session: AsyncSession, *, directory: Path | None = None) -> tuple[int, int]:
    """Delete every reading and every stored document, files first, and say
    how many of each went. Only the person's own Remove calls this.

    Every file in the documents folder goes, not only those a row names: the
    folder is the engine's own, and a write that failed after its file was
    made leaves no row to find it by."""
    await lock_picks(session)
    folder = directory or documents_dir()
    if folder.is_dir():
        for entry in folder.iterdir():
            if entry.is_file() and not entry.is_symlink():
                entry.unlink(missing_ok=True)
    readings = await session.execute(delete(CandidateBackground))
    documents = await session.execute(delete(CandidateDocument))
    return readings.rowcount or 0, documents.rowcount or 0
