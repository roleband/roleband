"""The person's background for an assistant: the reading, and the file behind it.

Setup begins by learning who the person is. The assistant reads their CV, or
listens, builds a reading (`tracker/picks/background.py`) and saves it with
`background.set`; `confirmed` is true only once the person agreed to it in the
chat. `background.add_document` keeps the original file the person gave: the
client reads it from disk (`--file`) and the engine stores its bytes without
parsing them.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic.config import JsonDict
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.activity import Changed, Said
from tracker.agents.operations.descriptor import (
    EngineEffects,
    NoInput,
    OperationDescriptor,
    Shape,
    ToolTier,
)
from tracker.agents.operations.envelope import NextAction, OperationError
from tracker.db.models import CandidateBackground, CandidateDocument
from tracker.picks import background as store
from tracker.picks.background import MAX_DOCUMENT_BYTES, DocumentError, Reading

_CODE: JsonDict = {"x-text": "code"}
_CONTENT: JsonDict = {"x-text": "content"}
_TIERS: tuple[ToolTier, ...] = ("standard", "full")
#: The most a document's request may weigh: its bytes in base64, and its name.
MAX_DOCUMENT_BODY_BYTES = MAX_DOCUMENT_BYTES * 4 // 3 + 64 * 1024


class StoredDocument(Shape):
    id: int
    filename: str = Field(json_schema_extra=_CONTENT)
    media_type: str = Field(json_schema_extra=_CODE)
    size_bytes: int = Field(ge=0)
    added_at: datetime


class BackgroundView(Shape):
    #: False when no reading was ever saved; every other field is then null.
    saved: bool
    version: int | None = None
    #: True once the person agreed to the reading.
    confirmed: bool = False
    source: Literal["document", "spoken", "minimal"] | None = Field(default=None, json_schema_extra=_CODE)
    document: StoredDocument | None = None
    #: The reading, as `background.set` takes it.
    reading: dict[str, Any] | None = None
    saved_at: datetime | None = None


class BackgroundSetInput(Shape):
    reading: Reading = Field(description="What you read of the person's background.")
    source: Literal["document", "spoken", "minimal"] = Field(
        description="document (read from a file), spoken (the person described it), minimal (three facts only).",
    )
    document_id: int | None = Field(default=None, ge=1, description="The stored file the reading came from.")
    confirmed: bool = Field(
        default=False, description="True only after the person agreed to this reading in the chat.",
    )


class AddDocumentInput(Shape):
    filename: str = Field(min_length=1, max_length=255, description="The file's name, with its extension.")
    content_base64: str = Field(
        min_length=1, max_length=MAX_DOCUMENT_BYTES * 4 // 3 + 8, description="The file's bytes, in base64.",
    )


class DocumentAdded(Shape):
    document: StoredDocument
    #: False when these bytes were already stored: the answer is that document.
    stored: bool


BACKGROUND_GET = OperationDescriptor(
    id="background.get",
    summary="Read the newest reading of the person's background, and whether they confirmed it.",
    input=NoInput,
    result=BackgroundView,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_TIERS,
    data_classes=("candidate",),
)

BACKGROUND_SET = OperationDescriptor(
    id="background.set",
    summary=(
        "Save a reading of the person's background as a new version. Set confirmed only after the person "
        "agreed to it."
    ),
    input=BackgroundSetInput,
    result=BackgroundView,
    access="write",
    action_group="tuning_radar",
    idempotency="required_key",
    engine_effects=EngineEffects(state_write=True),
    tool_tiers=_TIERS,
    data_classes=("candidate",),
    examples=(
        {"reading": {"current": {"title": "Senior Product Manager", "employer": "Acme"}, "years": 9,
                     "strengths": ["Platform products", "Pricing"]},
         "source": "spoken", "confirmed": True},
    ),
)

BACKGROUND_ADD_DOCUMENT = OperationDescriptor(
    id="background.add_document",
    summary=(
        "Store the file the person gave about themselves (a CV), as it is. The command reads it with "
        "--file; the engine never parses it."
    ),
    input=AddDocumentInput,
    result=DocumentAdded,
    access="write",
    action_group="tuning_radar",
    idempotency="required_key",
    engine_effects=EngineEffects(state_write=True),
    tool_tiers=_TIERS,
    data_classes=("candidate",),
    client_effects=("file_read",),
    max_body_bytes=MAX_DOCUMENT_BODY_BYTES,
)

OPERATIONS: tuple[OperationDescriptor, ...] = (BACKGROUND_GET, BACKGROUND_SET, BACKGROUND_ADD_DOCUMENT)


def _document(row: CandidateDocument) -> StoredDocument:
    return StoredDocument(
        id=row.id, filename=row.filename, media_type=row.media_type, size_bytes=row.size_bytes,
        added_at=row.added_at,
    )


async def _view(session: AsyncSession, row: CandidateBackground | None) -> BackgroundView:
    if row is None:
        return BackgroundView(saved=False)
    held = await store.document(session, row.document_id) if row.document_id is not None else None
    return BackgroundView(
        saved=True, version=row.version, confirmed=row.confirmed_at is not None,
        source=row.source,  # type: ignore[arg-type]
        document=_document(held) if held is not None else None, reading=dict(row.reading), saved_at=row.created_at,
    )


async def get(session: AsyncSession) -> BackgroundView:
    return await _view(session, await store.newest(session))


def _refused(error: DocumentError, field: str) -> OperationError:
    return OperationError(
        "not_found" if error.code == "unknown_document" else "invalid_input", error.message,
        details={"field": field, "reason": error.code},
        next_actions=[NextAction(operation=BACKGROUND_ADD_DOCUMENT.id, arguments={})]
        if error.code == "unknown_document" else None,
    )


async def set_reading(session: AsyncSession, params: BackgroundSetInput, *, host: str | None) -> BackgroundView:
    try:
        row = await store.save_reading(
            session, params.reading, source=params.source, document_id=params.document_id,
            confirmed=params.confirmed, host=host, now=datetime.now(UTC),
        )
    except DocumentError as error:
        raise _refused(error, "document_id") from None
    return await _view(session, row)


async def add_document(session: AsyncSession, params: AddDocumentInput) -> DocumentAdded:
    try:
        content = base64.b64decode(params.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise OperationError(
            "invalid_input", "content_base64 is not base64.", details={"field": "content_base64"},
        ) from None
    try:
        row, stored = await store.store_document(
            session, filename=params.filename, content=content, now=datetime.now(UTC),
        )
    except DocumentError as error:
        raise _refused(error, "filename" if error.code == "unsupported_type" else "content_base64") from None
    return DocumentAdded(document=_document(row), stored=stored)


@dataclass(frozen=True)
class BackgroundActivity:
    """What saving a reading, or storing a file, lists on the Activity screen."""

    async def before(self, session: AsyncSession) -> None:
        return None

    def entry(self, before: object, result: BaseModel) -> Changed:
        if isinstance(result, DocumentAdded):
            return Changed(Said(
                "background.document_added", "Stored a document about you", {"filename": result.document.filename},
            ))
        if not isinstance(result, BackgroundView):
            raise TypeError(f"a background write answers BackgroundView, not {type(result).__name__}")
        english = "Saved your background, confirmed by you" if result.confirmed else "Saved a reading of your background"
        return Changed(Said("background.saved", english, {"version": result.version, "confirmed": result.confirmed}))
