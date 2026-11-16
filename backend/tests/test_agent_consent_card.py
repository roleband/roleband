"""Every data category an agent operation reads has a line on the consent card.

The assistant card in Settings > Intelligence is where a person is told what a
connected app may read, fetch and change before they let it connect
(`dashboard/src/features/intelligence/AssistantsCard.tsx`, its words in
`dashboard/src/copy/en/ai.ftl`). Each data category an operation declares names
the card message that covers it, or says the card has no line for it. A new
category, or an operation that starts reading one, fails here until its row
says which line tells the person about it, and that line is on the card.
"""

from __future__ import annotations

import dataclasses
import re
import typing
from pathlib import Path

import pytest

from tracker.agents.operations.catalog import REGISTERED
from tracker.agents.operations.descriptor import DataClass, OperationDescriptor

DASHBOARD = Path(__file__).resolve().parents[2] / "dashboard"
MESSAGES = DASHBOARD / "src/copy/en/ai.ftl"
CARD = DASHBOARD / "src/features/intelligence/AssistantsCard.tsx"

ROLES = "ai-assistants-card-shares-role-titles-companies-locations-and-link"
AGE = "ai-assistants-card-shares-pay-level-and-how-long-the-role-has-been"
POSTING = "ai-assistants-card-shares-the-full-posting-when-they-open-one"
PROGRESS = "ai-assistants-card-shares-your-progress-on-roles-stage-priority-no"
PAGES = "ai-assistants-card-shares-public-pages-it-asks-roleband-to-open"
WRITES = "ai-assistants-card-stage-notes-next-action-audited"

#: Each data category, with the card lines that tell the person about it. A
#: category with no line is listed with an empty tuple: the card says nothing
#: of it yet, and this table is where that is visible.
LINES_FOR_CATEGORY: dict[DataClass, tuple[str, ...]] = {
    "public_posting": (ROLES, POSTING, PAGES),
    "market_statistic": (AGE,),
    "private_pursuit": (PROGRESS,),
    "offer": (),
    "candidate": (),
}

#: The line that tells the person an operation changes their data.
WRITE_LINE = WRITES


def _generated_name(message_id: str) -> str:
    """The function `gen:copy` exports for a message id."""
    head, *rest = message_id.split("-")
    return head + "".join(part.capitalize() for part in rest)


def uncovered(descriptors: tuple[OperationDescriptor, ...]) -> list[str]:
    """Operations that read a category the table does not list, or write
    without the writes line."""
    problems = []
    for descriptor in descriptors:
        for category in descriptor.data_classes:
            if category not in LINES_FOR_CATEGORY:
                problems.append(f"{descriptor.id}: category {category} has no row")
        if descriptor.access == "write" and not _line_on_card(WRITE_LINE):
            problems.append(f"{descriptor.id}: the writes line is not on the card")
    return problems


def _line_on_card(message_id: str) -> bool:
    in_catalog = re.search(rf"^{re.escape(message_id)} = ", MESSAGES.read_text(), re.M)
    return bool(in_catalog) and _generated_name(message_id) in CARD.read_text()


def test_the_table_names_every_data_category():
    assert set(LINES_FOR_CATEGORY) == set(typing.get_args(DataClass))


def test_every_operation_reads_only_categories_the_table_lists_and_writes_under_a_line():
    assert uncovered(REGISTERED) == []


@pytest.mark.parametrize(
    "message_id", sorted({line for lines in LINES_FOR_CATEGORY.values() for line in lines} | {WRITE_LINE})
)
def test_each_covering_line_is_in_the_catalog_and_on_the_card(message_id):
    assert _line_on_card(message_id), message_id


def test_a_category_without_a_row_fails():
    widened = dataclasses.replace(REGISTERED[-1], data_classes=("secret_diary",))  # type: ignore[arg-type]

    assert uncovered((widened,)) == [f"{widened.id}: category secret_diary has no row"]


def test_a_line_that_is_not_on_the_card_is_caught():
    assert not _line_on_card("ai-assistants-card-shares-a-thing-the-card-never-says")
