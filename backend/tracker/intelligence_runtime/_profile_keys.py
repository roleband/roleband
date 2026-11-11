"""Saved model-profile keys: which server one is for, and key conversion for raw
rows without validating away stored data."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from tracker.platform.secrets import seal
from tracker.settings_store import get_setting_dict, set_setting_dict

_DEFAULT_PORTS = {"http": 80, "https": 443}


class ProfilesUnreadable(Exception):
    """The stored profiles no longer validate (a narrowed schema, a restored row).

    A write built on what could be read would replace every saved profile, and
    its sealed key, with nothing; the stores refuse it instead.
    """


class KeySavedForAnotherAddress(Exception):
    """An edit named no key and a server the saved key is not for."""


def _server(url: str) -> tuple[str, str | None, int | None] | None:
    """Scheme, host and port; None for an address whose port cannot be read."""
    parts = urlsplit(url)
    try:
        return parts.scheme, parts.hostname, parts.port or _DEFAULT_PORTS.get(parts.scheme)
    except ValueError:
        return None


def kept_key(saved_url: str, saved_key: str | None, url: str, key: str | None) -> str | None:
    """The key a connection holds after an edit that sent `key` for `url`.

    The key is write-only, so an edit that changes something else arrives with
    none and keeps the saved one. It keeps it only at the server the key was
    saved for (scheme, host and port): the key is a secret shared with that
    server, and an edit that kept the key while naming where it is sent would
    hand it to any server the edit's author chose. A path, a model or a
    provider leaves the server what it was.
    """
    if key is not None or saved_key is None:
        return key
    server = _server(url)
    if server is None or server != _server(saved_url):
        raise KeySavedForAnotherAddress
    return saved_key


def with_keys(value: dict, convert: Callable[[str | None], str | None]) -> dict:
    profiles = value.get("profiles")
    if not isinstance(profiles, list):
        return value
    return {
        **value,
        "profiles": [
            {**profile, "api_key": convert(profile.get("api_key"))}
            if isinstance(profile, dict) and isinstance(profile.get("api_key"), str) else profile
            for profile in profiles
        ],
    }


async def reseal_raw(session: AsyncSession, key: str) -> None:
    """The caller holds its store's write lock before reading this raw row.

    Typed validation can reject profiles with unsupported fields or values;
    resealing preserves those profiles and every unrelated field.
    """
    value = await get_setting_dict(session, key)
    if value is not None:
        await set_setting_dict(session, key, with_keys(value, seal))
