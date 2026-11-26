"""The checkable hard rules, as conditions over a posting.

A checkable rule rules a posting out only on a field the posting states. A
posting that does not state the field (no pay band, no placed level, an
unknown work mode, no place) is never ruled out by that rule: it goes to the
judge. Every condition here is therefore false, never NULL, for such a
posting, so negating it keeps the row.

Pay rules read the employer's own stated band, never an estimate, and only a
band with an upper bound, stated per year in the rule's currency.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, and_, case, false, func, not_, or_

from tracker.db.models import Job
from tracker.db.queries.scope import unplaced_level_expr
from tracker.pay_numbers import USD_PER_UNIT
from tracker.pay_period import SIZE_CLASSES
from tracker.picks.brief import (
    AvoidCompanies,
    BriefBody,
    MinBase,
    MinLevel,
    MinTotal,
    Places,
    Rule,
    WorkModes,
    checkable_rules,
)
from tracker.schema import LEVEL_BAND_ORDER

#: The smallest amount a yearly band holds, in US dollars (`pay_period`).
_YEARLY_FLOOR = next(floor for period, floor, _ceiling in SIZE_CLASSES if period.value == "year")


def _stated_top(entity: Any, basis: str, currency: str) -> ColumnElement[Any]:
    """The top of the posting's stated yearly band on `basis`, or NULL when it
    states none in `currency`. A band with no top ("from $150,000", or a
    figure stored only as its minimum) rules nothing out: the judge reads it."""
    top = entity.disclosed_base_max
    # The floor is in US dollars; the band is in `currency`, sized as `size_classes` sizes it.
    yearly_floor = _YEARLY_FLOOR / USD_PER_UNIT.get(currency, 1.0)
    return case(
        (
            and_(
                entity.disclosed_pay_basis == basis,
                func.upper(entity.disclosed_currency) == currency,
                or_(
                    entity.disclosed_pay_period == "year",
                    # A band with no stored period reads yearly when only a year can hold it.
                    and_(entity.disclosed_pay_period.is_(None), top >= yearly_floor),
                ),
            ),
            top,
        ),
        else_=None,
    )


def _excludes(check: Any, entity: Any) -> ColumnElement[Any]:
    if isinstance(check, MinBase):
        return _stated_top(entity, "base", check.currency) < check.amount
    if isinstance(check, MinTotal):
        return _stated_top(entity, "total", check.currency) < check.amount
    if isinstance(check, Places):
        elsewhere = and_(
            func.cardinality(entity.location_groups) > 0,
            not_(entity.location_groups.op("&&")(list(check.places))),
        )
        # With remote allowed, only a posting that states it is not remote is out.
        stated_not_remote = entity.workplace_type.notin_(["remote", "unknown"])
        return and_(elsewhere, stated_not_remote) if check.remote_ok else elsewhere
    if isinstance(check, WorkModes):
        return and_(entity.workplace_type != "unknown", entity.workplace_type.notin_(list(check.modes)))
    if isinstance(check, MinLevel):
        order = case(LEVEL_BAND_ORDER, value=entity.level_band, else_=None)
        return and_(not_(unplaced_level_expr(entity)), order < LEVEL_BAND_ORDER[check.level])
    if isinstance(check, AvoidCompanies):
        return entity.company.in_(list(check.companies))
    raise TypeError(f"not a checkable form: {type(check).__name__}")


def excludes(rule: Rule, entity: Any = Job) -> ColumnElement[Any]:
    """Whether `rule` rules the posting out: true or false, never NULL."""
    if rule.check is None:
        raise ValueError(f"rule {rule.id} is judged, not checkable")
    return func.coalesce(_excludes(rule.check, entity), false())


def ruled_out(body: BriefBody, entity: Any = Job) -> ColumnElement[Any]:
    """Whether any checkable rule of `body` rules the posting out."""
    rules = checkable_rules(body)
    return or_(*(excludes(rule, entity) for rule in rules)) if rules else false()
