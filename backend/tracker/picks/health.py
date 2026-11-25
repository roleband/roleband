"""Whether the routine is doing its job: a pure reading of stored facts.

| State | When |
|---|---|
| `off` | the mode is not on |
| `stopped_early` | the newest run ended `stopped` or `abandoned` |
| `never_ran` | the mode is on and no run has finished |
| `late` | postings have waited longer than `LATE_AFTER` and no run finished in that time |
| `healthy` | otherwise |
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

Health = Literal["off", "healthy", "never_ran", "late", "stopped_early"]

#: How long a posting may wait for a judgment before the routine is late.
LATE_AFTER = timedelta(hours=36)
#: A run left open this long is closed as abandoned.
ABANDONED_AFTER = timedelta(hours=2)


@dataclass(frozen=True)
class RunFact:
    """What health reads of one run of the routine (a trial is not one)."""

    outcome: str | None
    started_at: datetime
    finished_at: datetime | None
    note: str | None = None


def health(
    *,
    state: str,
    newest: RunFact | None,
    last_finished_at: datetime | None,
    oldest_waiting_since: datetime | None,
    now: datetime,
) -> Health:
    """`newest` is the newest closed run of the routine, `last_finished_at`
    when a run last ended `finished`, and `oldest_waiting_since` when the
    longest-waiting posting of the queue was first seen."""
    if state != "on":
        return "off"
    if newest is not None and newest.outcome in ("stopped", "abandoned"):
        return "stopped_early"
    if last_finished_at is None:
        return "never_ran"
    if (
        oldest_waiting_since is not None
        and now - oldest_waiting_since > LATE_AFTER
        and now - last_finished_at > LATE_AFTER
    ):
        return "late"
    return "healthy"
