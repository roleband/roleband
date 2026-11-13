"""Membership in a long id list, sent as one bind parameter."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import ARRAY, ColumnElement, any_, literal


def among(column: Any, ids: Iterable[int]) -> ColumnElement[bool]:
    """`column = ANY(:ids)`: true where `column` is one of `ids`.

    The ids travel as ONE array parameter. `column.in_(ids)` spends a bind
    parameter per id, and the Postgres wire protocol refuses a statement with
    more than 32767 of them: a run, or a pass over the whole corpus, can hold
    more ids than that. Use this wherever the list's length is not bounded by
    the code that builds it.
    """
    return column == any_(literal(list(ids), ARRAY(column.type)))
