"""Download an offered Windows release and keep verified packages as the way back.

A download resumes where it stopped, from the feed's download path or its CDN only, and the
file becomes a retained package only after it matches the owner-signed digest and size. Each
retained package keeps its signed release files beside it, so it can be verified again before
it is registered, including as the previous version after a failed update.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path

import httpx

from tracker.platform.windows_release import (
    Identity,
    Offer,
    ReleaseError,
    names,
    stable_version,
    verify_offer,
    verify_package,
)
from tracker.platform.windows_updates import (
    REDIRECT_LIMIT,
    USER_AGENT,
    ReleaseMissing,
    asset_url,
    permitted,
)


class DownloadIncomplete(ReleaseError):
    """The package did not fully arrive. Nothing is known to be wrong with it, and the next attempt resumes."""


class DownloadInterrupted(DownloadIncomplete):
    """The connection ended before the last byte: the download waits for the network, not for a fix."""


PACKAGES = Path("packages")
#: Retained verified packages: the newest and the one before it, the executable way back.
KEEP = 2
_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+)", re.ASCII)


def folder(state: Path) -> Path:
    return state / PACKAGES


def _private(path: Path) -> None:
    if sys.platform == "win32":
        from tracker.platform.windows_private import private_directory

        private_directory(path)
    else:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)


def _get(client: httpx.Client, url: str, feed: str, version: str, headers: dict[str, str]) -> httpx.Response:
    for _ in range(REDIRECT_LIMIT + 1):
        response = client.send(client.build_request("GET", url, headers=headers), stream=True)
        if not response.is_redirect:
            return response
        response.close()
        url = str(response.next_request.url) if response.next_request else ""
        if not permitted(url, feed, version):
            raise ReleaseError("The package redirected outside the update feed")
    raise ReleaseError("The package redirected too many times")


#: Told the bytes of the package on disk so far and its signed size, as they arrive.
Progress = Callable[[int, int], None]


def download(state: Path, identity: Identity, offer: Offer, signed: tuple[bytes, bytes, bytes], installed: str, *,
             transport: httpx.BaseTransport | None = None, progress: Progress | None = None) -> Path:
    """Fetch, verify and retain the offered package; a partial file is resumed by the next call."""
    if verify_offer(identity, "0.0.0", *signed) != offer:
        raise ReleaseError("The signed release files do not describe this offer")
    packages = folder(state)
    _private(packages)
    final = packages / offer.package
    if final.exists():
        try:
            verify_package(final, offer)
            return final
        except ReleaseError:
            # A kept package that no longer matches its signed digest cannot become right: it is fetched again.
            final.with_name(final.name + ".release.json").unlink(missing_ok=True)
            final.unlink()
    partial = packages / f".{offer.package}.partial"
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > offer.bytes:
        partial.unlink()
        offset = 0
    # A stop between the last byte and the rename leaves a complete partial file; a range past its end would be
    # refused for ever, so it goes straight to verification.
    if offset < offer.bytes:
        headers = {"Accept-Encoding": "identity", **({"Range": f"bytes={offset}-"} if offset else {})}
        with httpx.Client(transport=transport, follow_redirects=False, trust_env=False,
                          timeout=httpx.Timeout(30.0, connect=10.0), headers={"User-Agent": USER_AGENT}) as client:
            response = _get(client, asset_url(identity.feed, offer.version, offer.package), identity.feed,
                            offer.version, headers)
            try:
                if offset and response.status_code == 206:
                    match = _RANGE.fullmatch(response.headers.get("Content-Range", ""))
                    if not match or (int(match[1]), int(match[2]), int(match[3])) != (offset, offer.bytes - 1, offer.bytes):
                        raise DownloadIncomplete("The server resumed the package at the wrong place")
                    mode = "ab"
                elif response.status_code == 200:
                    offset, mode = 0, "wb"
                elif response.status_code in (404, 410):
                    raise ReleaseMissing("The package is not published")
                else:
                    raise DownloadIncomplete("The package is not available")
                with partial.open(mode) as output:
                    written = offset
                    if progress is not None:
                        progress(written, offer.bytes)
                    for chunk in response.iter_bytes():
                        written += len(chunk)
                        if written > offer.bytes:
                            raise ReleaseError("The package is larger than its signed size")
                        output.write(chunk)
                        if progress is not None:
                            progress(written, offer.bytes)
                    output.flush()
                    os.fsync(output.fileno())
            finally:
                response.close()
    if partial.stat().st_size < offer.bytes:
        raise DownloadInterrupted("The package download was interrupted; it resumes on the next attempt")
    try:
        verify_package(partial, offer)
    except ReleaseError:
        # A complete file with the wrong digest cannot be resumed into the right one.
        partial.unlink()
        raise
    (packages / (offer.package + ".release.json")).write_text(json.dumps({
        "checksum": base64.b64encode(signed[0]).decode(), "metadata": base64.b64encode(signed[1]).decode(),
        "signature": base64.b64encode(signed[2]).decode()}), encoding="utf-8")
    partial.replace(final)
    prune(state, identity, installed)
    return final


def retain_running(state: Path, identity: Identity, installed: str, *,
                   transport: httpx.BaseTransport | None = None, progress: Progress | None = None,
                   room: Callable[[Offer], None] | None = None) -> Path:
    """Keep the running version's own release package: the only way back from its first update.

    Windows keeps no copy of an installed package, so the way back is the published release of
    the running version, verified like any update before it is kept. `room` sees the verified
    release, whose size is known only then, and may refuse it before anything is downloaded.
    """
    from tracker.platform.windows_updates import fetch_release

    for offer, path in retained(state, identity):
        if offer.version == installed:
            return path
    signed = fetch_release(identity, installed, transport=transport)
    offer = verify_offer(identity, "0.0.0", *signed)
    if offer.version != installed:
        raise ReleaseError("The feed's release files describe another version")
    if room is not None:
        room(offer)
    return download(state, identity, offer, signed, installed, transport=transport, progress=progress)


def retained(state: Path, identity: Identity) -> list[tuple[Offer, Path]]:
    """Verified retained packages, newest first. Anything that no longer verifies is not listed."""
    found = []
    packages = folder(state)
    if not packages.is_dir():
        return []
    for record in packages.glob("*.msix.release.json"):
        package = record.with_name(record.name.removesuffix(".release.json"))
        try:
            stored = json.loads(record.read_text(encoding="utf-8"))
            offer = verify_offer(identity, "0.0.0", *(base64.b64decode(stored[name], validate=True)
                                                       for name in ("checksum", "metadata", "signature")))
            if package.name != offer.package or names(offer.version)[0] != package.name:
                continue
            verify_package(package, offer)
        except (OSError, KeyError, TypeError, ValueError):
            continue
        found.append((offer, package))
    return sorted(found, key=lambda item: stable_version(item[0].version), reverse=True)


def _undo_versions(state: Path) -> set[str] | None:
    """The version an unsettled update returns to, which Undo installs again; None when that cannot be known."""
    if sys.platform != "win32":
        return set()
    from tracker.platform import windows_update_journal as journal
    from tracker.platform.windows_recovery import RecoveryError

    try:
        record = journal.read(state)
    except RecoveryError:
        return None
    return {record["from_version"]} if record is not None and record["phase"] not in journal.RESOLVED else set()


def prune(state: Path, identity: Identity, installed: str) -> None:
    """Keep the newest verified packages, the running version's and the one an unfinished update returns to; older
    ones are re-downloadable releases. Nothing is removed while the update journal cannot be read."""
    undo = _undo_versions(state)
    if undo is None:
        return
    for offer, package in retained(state, identity)[KEEP:]:
        if offer.version == installed or offer.version in undo:
            continue
        package.with_name(package.name + ".release.json").unlink(missing_ok=True)
        package.unlink(missing_ok=True)
