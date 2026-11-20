"""`receipts.get`: what a write sent under a key did, after its reply was lost.

A receipt is looked up by the write's operation and idempotency key, in this
workspace and for the principal the engine names: no input chooses another
workspace or principal. It returns the committed outcome under current
visibility, however the record has moved since.

A miss is not proof that the write failed: a request still running has not
committed its receipt yet. The way forward is to send the same write again
under the same key, which never writes twice.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import Field
from pydantic.config import JsonDict
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.agents.operations.descriptor import (
    OPERATION_ID,
    DataClass,
    EngineEffects,
    OperationDescriptor,
    Shape,
    ToolTier,
)
from tracker.agents.operations.envelope import NextAction, OperationError
from tracker.agents.operations.policy import category_disabled
from tracker.agents.receipts import ReceiptKey, find_receipt

_CODE: JsonDict = {"x-text": "code"}
_IDENTIFIER: JsonDict = {"x-text": "identifier"}
_EVERY_TIER: tuple[ToolTier, ...] = ("small", "standard", "full")
#: The form of a key the engine accepts on a write (`agent_operations._IDEMPOTENCY_KEY`).
KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$"


class ReceiptGetInput(Shape):
    operation: str = Field(
        max_length=128, pattern=OPERATION_ID, json_schema_extra=_CODE,
        description="The write's operation id, such as pursuits.patch.",
    )
    key: str = Field(
        pattern=KEY_PATTERN, json_schema_extra=_IDENTIFIER,
        description="The idempotency key the write was sent under: its meta.idempotency_key.",
    )


class Receipt(Shape):
    operation: str = Field(json_schema_extra=_CODE)
    key: str = Field(json_schema_extra=_IDENTIFIER)
    #: The contract version the write's input and result belong to.
    contract_version: str = Field(json_schema_extra=_CODE)
    recorded_at: datetime
    #: The visible part of the committed result, in the write's result shape.
    result: dict[str, Any]


RECEIPTS_GET = OperationDescriptor(
    id="receipts.get",
    summary=(
        "Read back what a write sent under an idempotency key did. A miss is not proof it failed: "
        "send the same write again with the same key, which never writes twice."
    ),
    input=ReceiptGetInput,
    result=Receipt,
    access="read",
    idempotency="read",
    engine_effects=EngineEffects(),
    tool_tiers=_EVERY_TIER,
    # A receipt holds its write's result: a recipe draft's, or a pursuit write's
    # with the posting it is about. Which of these a receipt may answer is
    # decided by its write's own categories (`receipt_of`).
    data_classes=("public_posting", "private_pursuit"),
    examples=({"operation": "pursuits.patch", "key": "followup-4821-v1"},),
)

OPERATIONS: tuple[OperationDescriptor, ...] = (RECEIPTS_GET,)


async def receipt_of(
    session: AsyncSession, params: ReceiptGetInput, *, workspace_id: str, principal_id: str, keyed: bool,
    withheld: Sequence[DataClass] = (),
) -> Receipt:
    """The receipt of one keyed write. `keyed` says whether the operation
    named is one this engine runs under a key; only those keep receipts.

    `withheld` is the named write's categories the person does not share, in
    the order it declares them. The lookup is refused when any of them is
    withheld, so it does not reveal whether a write committed under the key.
    """
    if withheld:
        raise category_disabled(withheld[0])
    if not keyed:
        raise OperationError(
            "invalid_input",
            "Only a write sent under an idempotency key keeps a receipt, and this operation is not one.",
            details={"field": "operation", "operation": params.operation},
            next_actions=[NextAction(operation="capabilities", arguments={})],
        )
    found = await find_receipt(session, ReceiptKey(workspace_id, principal_id, params.operation, params.key))
    if found is None:
        raise OperationError(
            "not_found",
            "No write under this key has committed here. A write still running has not yet: send the same "
            "write again with the same key, which never writes twice.",
            details={"operation": params.operation, "key": params.key},
        )
    return Receipt(
        operation=found.operation,
        key=found.idempotency_key,
        contract_version=found.contract_version,
        recorded_at=found.created_at,
        result=dict(found.result),
    )
