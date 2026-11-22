"""Every data category and action group an agent operation uses has a row in Customize.

The assistant card in Settings > Intelligence is the one consent: its switch
lets apps connect, and from then on they read every category and make every
kind of change (`docs/decisions/0017-agent-access-open-by-default.md`). What
they get is listed, one row each, in its Customize dialog
(`dashboard/src/features/intelligence/AgentAccessDialog.tsx`, its words in
`dashboard/src/copy/en/ai.ftl`), where the person can hold any of it back. A
new category or group, or an operation that starts using one, fails here until
its row names the message that lists it, and that message is in the dialog.
"""

from __future__ import annotations

import dataclasses
import re
import typing
from pathlib import Path

import pytest

from tracker.agents.operations.catalog import REGISTERED
from tracker.agents.operations.descriptor import ActionGroup, DataClass, OperationDescriptor

DASHBOARD = Path(__file__).resolve().parents[2] / "dashboard"
MESSAGES = DASHBOARD / "src/copy/en/ai.ftl"
DIALOG = DASHBOARD / "src/features/intelligence/AgentAccessDialog.tsx"

#: Each data category, with the Customize row that lists it.
CATEGORY_ROWS: dict[DataClass, str] = {
    "public_posting": "ai-access-dialog-postings",
    "market_statistic": "ai-access-dialog-market-statistics",
    "private_pursuit": "ai-access-dialog-progress-and-notes",
    "offer": "ai-access-dialog-offer",
    "candidate": "ai-access-dialog-profile",
}

#: Each action group, with the Customize row that lists it.
GROUP_ROWS: dict[ActionGroup, str] = {
    "tracking_progress": "ai-access-dialog-tracking-progress",
    "keeping_findings": "ai-access-dialog-keeping-findings",
    "tuning_radar": "ai-access-dialog-tuning-the-radar",
    "controlling_collection": "ai-access-dialog-controlling-collection",
}


def _generated_name(message_id: str) -> str:
    """The function `gen:copy` exports for a message id."""
    head, *rest = message_id.split("-")
    return head + "".join(part.capitalize() for part in rest)


def uncovered(descriptors: tuple[OperationDescriptor, ...]) -> list[str]:
    """Operations that read a category, or belong to a group, with no row."""
    problems = []
    for descriptor in descriptors:
        for category in descriptor.data_classes:
            if category not in CATEGORY_ROWS:
                problems.append(f"{descriptor.id}: category {category} has no row")
        group = descriptor.action_group
        if group is not None and group not in GROUP_ROWS:
            problems.append(f"{descriptor.id}: group {group} has no row")
    return problems


def _row_in_dialog(message_id: str) -> bool:
    in_catalog = re.search(rf"^{re.escape(message_id)} = ", MESSAGES.read_text(), re.M)
    return bool(in_catalog) and re.search(rf"\b{_generated_name(message_id)}\b", DIALOG.read_text()) is not None


def test_every_category_and_group_has_a_row():
    assert set(CATEGORY_ROWS) == set(typing.get_args(DataClass))
    assert set(GROUP_ROWS) == set(typing.get_args(ActionGroup))


def test_every_operation_uses_only_categories_and_groups_with_a_row():
    assert uncovered(REGISTERED) == []


@pytest.mark.parametrize("message_id", sorted({*CATEGORY_ROWS.values(), *GROUP_ROWS.values()}))
def test_each_row_is_in_the_catalog_and_in_the_dialog(message_id):
    assert _row_in_dialog(message_id), message_id


def test_a_category_or_group_without_a_row_fails():
    widened = dataclasses.replace(REGISTERED[-1], data_classes=("secret_diary",))  # type: ignore[arg-type]
    assert uncovered((widened,)) == [f"{widened.id}: category secret_diary has no row"]

    write = next(descriptor for descriptor in REGISTERED if descriptor.access == "write")
    regrouped = dataclasses.replace(write, action_group="sending_mail")  # type: ignore[arg-type]
    assert f"{write.id}: group sending_mail has no row" in uncovered((regrouped,))


def test_a_row_that_is_not_in_the_dialog_is_caught():
    assert not _row_in_dialog("ai-access-dialog-a-row-the-dialog-never-lists")
    # In the catalog but not in the dialog is caught too.
    assert not _row_in_dialog("ai-assistants-card-customize")
