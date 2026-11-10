"""The person's own job offer and the private-company valuations they enter.

Both live in `app_settings` on this computer and are never sent anywhere else:
no usage event counts them (`api/usage_counter.py` lists the routes as not
counted), and no other reader touches the keys. The API validates every value
before it reaches here and again when it reads one back, so a row from another
version of the shape reads as nothing rather than as wrong figures.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from tracker.platform.locks import advisory_xact_lock
from tracker.settings_store import delete_setting, get_setting_dict, set_setting_dict

OFFER_KEY = "stock_offer"
VALUATIONS_KEY = "private_valuations"
#: Valuations kept at most: one per private company the person has looked at.
MAX_VALUATIONS = 200
# The valuations are one JSON row edited per company: read, change, write.
VALUATIONS_LOCK_KEY = 91251


async def read_offer(session: AsyncSession) -> dict | None:
    return await get_setting_dict(session, OFFER_KEY)


async def save_offer(session: AsyncSession, offer: dict, now: datetime) -> dict:
    """Keep `offer` with the time it was saved; the dashboard says "Entered by
    you" with that date."""
    return await set_setting_dict(session, OFFER_KEY, {**offer, "saved_at": now.isoformat()})


async def clear_offer(session: AsyncSession) -> None:
    await delete_setting(session, OFFER_KEY)


async def read_valuations(session: AsyncSession) -> dict[str, object]:
    return await get_setting_dict(session, VALUATIONS_KEY) or {}


class TooManyValuations(ValueError):
    pass


async def save_valuation(session: AsyncSession, company: str, valuation: dict, now: datetime) -> None:
    """Keep one company's valuation. A company not yet kept is refused once
    `MAX_VALUATIONS` are kept; changing a kept one never is."""
    await advisory_xact_lock(session, VALUATIONS_LOCK_KEY)
    current = await read_valuations(session)
    if company not in current and len(current) >= MAX_VALUATIONS:
        raise TooManyValuations(f"at most {MAX_VALUATIONS} valuations are kept")
    await set_setting_dict(
        session, VALUATIONS_KEY, {**current, company: {**valuation, "saved_at": now.isoformat()}}
    )


async def clear_valuation(session: AsyncSession, company: str) -> None:
    await advisory_xact_lock(session, VALUATIONS_LOCK_KEY)
    current = await read_valuations(session)
    if company not in current:
        return
    rest = {k: v for k, v in current.items() if k != company}
    if rest:
        await set_setting_dict(session, VALUATIONS_KEY, rest)
    else:
        await delete_setting(session, VALUATIONS_KEY)
