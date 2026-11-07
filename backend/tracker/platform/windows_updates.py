"""Ask the update feed for a newer Windows release, only as often as the person allowed.

No request is made before an explicit choice. Automatic checks stay off until enabled and run
at most once a day, failed attempts included; a manual check authorizes one request without
changing that choice. A rate limit delays manual checks too. The listing is not signed, so an
offer comes only from release files that verify with the installed package's key
(`windows_release`); a failed check keeps the last verified offer, and a verified offer is
never replaced by an older listing.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from tracker.platform.windows_release import (
    CHECKSUM_LIMIT,
    METADATA_LIMIT,
    Identity,
    Offer,
    ReleaseError,
    names,
    stable_version,
    verify_offer,
)

AUTOMATIC_INTERVAL = 24 * 60 * 60
RATE_LIMIT_FLOOR = 60
LISTING_LIMIT = 256 * 1024
REDIRECT_LIMIT = 5
USER_AGENT = "RoleBand-Launcher"
API_VERSION = "2026-03-10"
CONSENT = Path("launcher") / "update-consent.json"
CHECK = Path("launcher") / "update-check.json"
_TEXT_LIMIT = 4000


class RateLimited(Exception):
    def __init__(self, until: float) -> None:
        super().__init__(until)
        self.until = until


@dataclass(frozen=True)
class Result:
    #: not-allowed, throttled, rate-limited, up-to-date, offered, failed
    status: str
    offer: Offer | None = None
    until: float | None = None


def _load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if sys.platform == "win32":
        from tracker.platform.windows_storage import StorageCompatibilityError, read_json

        try:
            return read_json(path)
        except StorageCompatibilityError:
            return None
    try:
        record = json.loads(path.read_bytes())
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def _save(path: Path, record: dict[str, Any]) -> None:
    if sys.platform == "win32":
        from tracker.platform.windows_private import private_directory
        from tracker.platform.windows_storage import write_json

        private_directory(path.parent)
        write_json(path, record)
        return
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-")
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(json.dumps(record).encode())
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def record_consent(state: Path, *, automatic: bool, text: str, language: str, now: float | None = None) -> None:
    """Keep the choice with the exact words and language the person answered."""
    if type(automatic) is not bool or not isinstance(text, str) or not text.strip() or len(text) > _TEXT_LIMIT \
            or not isinstance(language, str) or not 2 <= len(language) <= 16:
        raise ValueError("A consent choice needs the shown text and its language")
    _save(state / CONSENT, {"format": 1, "automatic": automatic, "text": text, "language": language,
                            "chosen_at": time.time() if now is None else now})


def automatic_allowed(state: Path) -> bool:
    record = _load(state / CONSENT)
    return bool(record and record.get("format") == 1 and record.get("automatic") is True)


def _stored_offer(record: dict[str, Any], identity: Identity, installed: str) -> Offer | None:
    stored = record.get("offer")
    if not isinstance(stored, dict):
        return None
    try:
        parts = [base64.b64decode(stored[name], validate=True) for name in ("checksum", "metadata", "signature")]
        return verify_offer(identity, installed, *parts)
    except (KeyError, TypeError, ValueError):
        return None


def stored_offer(state: Path, identity: Identity, installed: str) -> tuple[Offer, tuple[bytes, bytes, bytes]] | None:
    """The verified offer a check kept, with the signed files it came from."""
    record = _load(state / CHECK) or {}
    offer = _stored_offer(record, identity, installed)
    if offer is None:
        return None
    stored = record["offer"]
    signed = tuple(base64.b64decode(stored[name], validate=True) for name in ("checksum", "metadata", "signature"))
    return offer, (signed[0], signed[1], signed[2])


def latest_url(feed: str) -> str:
    return f"https://api.github.com/repos/{feed}/releases/latest"


def asset_url(feed: str, version: str, name: str) -> str:
    return f"https://github.com/{feed}/releases/download/v{version}/{name}"


def permitted(url: str, feed: str, version: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.port not in (None, 443) or parts.username or parts.password or parts.fragment:
        return False
    return parts.hostname == "release-assets.githubusercontent.com" or (
        parts.hostname == "github.com" and parts.path.startswith(f"/{feed}/releases/download/v{version}/"))


def _rate_limit(response: httpx.Response, now: float) -> None:
    if response.status_code not in (403, 429):
        return
    retry = response.headers.get("Retry-After", "")
    delay = float(RATE_LIMIT_FLOOR)
    if retry.isdecimal():
        delay = max(delay, float(retry))
    elif retry:
        try:
            delay = max(delay, parsedate_to_datetime(retry).timestamp() - now)
        except (TypeError, ValueError):
            pass
    until = now + delay
    if response.headers.get("X-RateLimit-Remaining") == "0" and response.headers.get("X-RateLimit-Reset", "").isdecimal():
        until = max(until, float(response.headers["X-RateLimit-Reset"]))
    raise RateLimited(until)


def _read(response: httpx.Response, limit: int) -> bytes:
    declared = response.headers.get("Content-Length", "")
    if declared.isdecimal() and int(declared) > limit:
        raise ReleaseError("A release response exceeds its size limit")
    body = bytearray()
    for chunk in response.iter_bytes():
        body += chunk
        if len(body) > limit:
            raise ReleaseError("A release response exceeds its size limit")
    return bytes(body)


def _latest(client: httpx.Client, feed: str, now: float) -> str:
    with client.stream("GET", latest_url(feed), headers={"Accept": "application/vnd.github+json",
                                                         "X-GitHub-Api-Version": API_VERSION}) as response:
        _rate_limit(response, now)
        if response.status_code != 200:
            raise ReleaseError("The update feed did not answer with a release")
        listing = json.loads(_read(response, LISTING_LIMIT))
    tag = listing.get("tag_name") if isinstance(listing, dict) else None
    if (not isinstance(tag, str) or not tag.startswith("v") or listing.get("draft") is not False
            or listing.get("prerelease") is not False
            or listing.get("html_url") != f"https://github.com/{feed}/releases/tag/{tag}"):
        raise ReleaseError("The update feed's latest release is not a published stable release")
    stable_version(tag[1:])
    return tag[1:]


def _asset(client: httpx.Client, feed: str, version: str, name: str, limit: int, now: float) -> bytes:
    url = asset_url(feed, version, name)
    for _ in range(REDIRECT_LIMIT + 1):
        with client.stream("GET", url) as response:
            _rate_limit(response, now)
            if response.is_redirect:
                url = str(response.next_request.url) if response.next_request else ""
                if not permitted(url, feed, version):
                    raise ReleaseError("A release file redirected outside the update feed")
                continue
            if response.status_code != 200:
                raise ReleaseError("A release file is not published yet")
            return _read(response, limit)
    raise ReleaseError("A release file redirected too many times")


def check(state: Path, identity: Identity, installed: str, *, manual: bool, now: float | None = None,
          transport: httpx.BaseTransport | None = None) -> Result:
    now = time.time() if now is None else now
    record = _load(state / CHECK) or {}
    offer = _stored_offer(record, identity, installed)
    if offer is None and "offer" in record:
        record.pop("offer")
        _save(state / CHECK, record)
    if not manual:
        if not automatic_allowed(state):
            return Result("not-allowed", offer)
        attempted = record.get("attempted_at")
        if isinstance(attempted, (int, float)) and 0 <= now - attempted < AUTOMATIC_INTERVAL:
            return Result("throttled", offer)
    limited = record.get("rate_limited_until")
    if isinstance(limited, (int, float)) and limited > now:
        return Result("rate-limited", offer, float(limited))
    record["attempted_at"] = now
    _save(state / CHECK, record)
    timeout = httpx.Timeout(10.0, connect=10.0)
    try:
        with httpx.Client(transport=transport, follow_redirects=False, trust_env=False, timeout=timeout,
                          headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}) as client:
            version = _latest(client, identity.feed, now)
            if stable_version(version) <= stable_version(installed):
                return Result("up-to-date", offer)
            if offer is not None and stable_version(offer.version) >= stable_version(version):
                return Result("offered", offer)
            _package, checksum_name, metadata_name, signature_name = names(version)
            checksum = _asset(client, identity.feed, version, checksum_name, CHECKSUM_LIMIT, now)
            metadata = _asset(client, identity.feed, version, metadata_name, METADATA_LIMIT, now)
            signature = _asset(client, identity.feed, version, signature_name, 64, now)
            offer = verify_offer(identity, installed, checksum, metadata, signature)
    except RateLimited as limit:
        record["rate_limited_until"] = limit.until
        _save(state / CHECK, record)
        return Result("rate-limited", offer, limit.until)
    except (httpx.HTTPError, ReleaseError, ValueError):
        return Result("failed", offer)
    record["offer"] = {"checksum": base64.b64encode(checksum).decode(), "metadata": base64.b64encode(metadata).decode(),
                       "signature": base64.b64encode(signature).decode()}
    _save(state / CHECK, record)
    return Result("offered", offer)
