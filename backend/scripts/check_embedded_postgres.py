"""Is the embedded Postgres behind the newest release of its major?

Every install runs the PostgreSQL that the `pixeltable-pgserver` wheel bundles, with the
pgvector built into it and a `pg_trgm` built from the same source
(`tracker/platform/pgcontrib/manifest.json` pins both versions). The dependency audit
cannot see them: advisories name PostgreSQL, never the wheel. This reads the pinned
versions, reads postgresql.org's release list and pgvector's tags, and names each one
that is behind.

When Postgres is behind it also reads the newest wheel on PyPI and the Postgres version
its source builds, because that decides the fix: move the wheel pin, or wait for (or ask)
upstream to build the release.

The verdict logic is tested offline (`tests/test_embedded_postgres_check.py`); only this
script fetches. Exit codes:

    0  Postgres is the newest minor of a supported major, pgvector the newest patch of its series
    1  BEHIND: a newer Postgres minor or pgvector patch is out, or the major has reached its end of life
    2  PIN BROKEN: the manifest disagrees with the wheel pins or with its own source URLs
    3  UNKNOWN: an upstream list could not be read and nothing else is behind; no verdict

Usage (from `backend/`):

    .venv/bin/python -m scripts.check_embedded_postgres

Set `GITHUB_TOKEN` to lift the 60/hour unauthenticated GitHub API limit.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from scripts import upstream_http

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = "backend/tracker/platform/pgcontrib/manifest.json"
# Every file that pins the wheel: what setup installs and what each app bundles.
WHEEL_PINS = (
    "backend/requirements.txt",
    "backend/constraints/linux-aarch64.txt",
    "backend/constraints/linux-x86_64.txt",
    "backend/constraints/macos-arm64.txt",
    "backend/constraints/windows-x86_64.txt",
    "launcher/macos/runtime-lock.txt",
    "launcher/windows/runtime-lock.txt",
)
WHEEL = "pixeltable-pgserver"

VERSIONS_URL = "https://www.postgresql.org/versions.json"
PGVECTOR_TAGS_URL = "https://api.github.com/repos/pgvector/pgvector/tags?per_page=100"
PYPI_URL = f"https://pypi.org/pypi/{WHEEL}/json"
# The wheel's top-level Makefile names the Postgres version each bundled install builds.
WHEEL_MAKEFILE_URL = "https://raw.githubusercontent.com/pixeltable/pixeltable-pgserver/v{version}/Makefile"
USER_AGENT = "roleband-postgres-check"

EXIT_OK = 0
EXIT_BEHIND = 1
EXIT_PIN_BROKEN = 2
EXIT_UNKNOWN = 3

Minor = tuple[int, int]
Patch = tuple[int, int, int]
_POSTGRES = re.compile(r"(\d+)\.(\d+)")
_PGVECTOR_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
_MAKEFILE_POSTGRES = re.compile(r"POSTGRES_VERSION\s*:?=\s*(\d+)\.(\d+)\b")


def show(version: Sequence[int]) -> str:
    return ".".join(map(str, version))


@dataclass(frozen=True)
class Pins:
    wheel: str
    postgres: Minor
    pgvector: Patch


@dataclass(frozen=True)
class PostgresRelease:
    latest: Minor
    eol: date
    supported: bool


def pinned(root: Path = REPO_ROOT, wheel_pins: Iterable[str] = WHEEL_PINS) -> Pins:
    """The versions that ship. A manifest whose source URLs name another version, or a
    pin file that names another wheel than the manifest was built against, is refused:
    the version read here must be the one every install runs."""
    manifest = json.loads((root / MANIFEST).read_text())
    wheel = manifest["wheel_version"]
    postgres = manifest["postgres"]
    match = _POSTGRES.fullmatch(postgres)
    if not match:
        raise ValueError(f"{MANIFEST}: {postgres!r} is not a Postgres version such as 16.14")
    if not manifest["source_url"].endswith(f"/v{postgres}/postgresql-{postgres}.tar.gz"):
        raise ValueError(f"{MANIFEST}: {manifest['source_url']} is not the {postgres} source")
    pgvectors = set()
    for key, entry in manifest["platforms"].items():
        if not entry["wheel"].startswith(f"pixeltable_pgserver-{wheel}-"):
            raise ValueError(f"{MANIFEST}: {key} was built against {entry['wheel']}, not {wheel}")
        if "pgvector" in entry:
            version = entry["pgvector"]["version"]
            if not entry["pgvector"]["source_url"].endswith(f"/v{version}.tar.gz"):
                raise ValueError(f"{MANIFEST}: {key} pgvector source is not {version}")
            pgvectors.add(version)
    if len(pgvectors) != 1:
        raise ValueError(f"{MANIFEST}: expected one pgvector version, found {sorted(pgvectors) or 'none'}")
    pgvector = _PGVECTOR_TAG.fullmatch(f"v{pgvectors.pop()}")
    if not pgvector:
        raise ValueError(f"{MANIFEST}: pgvector version is not of the form 0.8.5")
    for path in wheel_pins:
        found = re.findall(rf"^{WHEEL}==(\S+)", (root / path).read_text(), flags=re.MULTILINE)
        if found != [wheel]:
            raise ValueError(f"{path} pins {WHEEL} {found or 'nowhere'}; the manifest was built against {wheel}")
    major, minor = (int(part) for part in match.groups())
    a, b, c = (int(part) for part in pgvector.groups())
    return Pins(wheel=wheel, postgres=(major, minor), pgvector=(a, b, c))


def postgres_release(versions: Any, major: int, today: date) -> PostgresRelease:
    """The newest minor of `major` and whether the major is still supported, from
    postgresql.org's release list. A list without the major gives no verdict."""
    if not isinstance(versions, list) or not all(isinstance(entry, dict) for entry in versions):
        raise ValueError("postgresql.org answered without a list of release records")
    for entry in versions:
        if entry.get("major") != str(major):
            continue
        try:
            latest = (major, int(entry["latestMinor"]))
            eol = date.fromisoformat(entry["eolDate"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"postgresql.org's record of {major} is malformed: {exc}") from exc
        supported = entry.get("supported")
        if not isinstance(supported, bool):
            raise ValueError(f"postgresql.org's record of {major} does not say whether it is supported")
        return PostgresRelease(latest=latest, eol=eol, supported=supported and today < eol)
    raise ValueError(f"postgresql.org's release list holds no Postgres {major}")


def newest_pgvector(tags: Any, series: tuple[int, int]) -> Patch:
    """The newest final pgvector release of `series` (0.8 for 0.8.5), from its tags.
    A newer series is a feature upgrade, not a fix, so it does not count."""
    if not isinstance(tags, list) or not all(isinstance(tag, dict) for tag in tags):
        raise ValueError("GitHub answered without a list of tags")
    found = []
    for tag in tags:
        match = _PGVECTOR_TAG.fullmatch(str(tag.get("name", "")))
        if match:
            a, b, c = (int(part) for part in match.groups())
            if (a, b) == series:
                found.append((a, b, c))
    if not found:
        raise ValueError(f"pgvector's tags hold no {show(series)} release")
    return max(found)


def wheel_postgres(makefile: str, major: int) -> Minor | None:
    """The `major` Postgres a wheel's source builds, or None when its Makefile does not say."""
    found = [(int(a), int(b)) for a, b in _MAKEFILE_POSTGRES.findall(makefile) if int(a) == major]
    return max(found, default=None)


def _wheel_line(pins: Pins, target: Minor, get: Callable[[str], httpx.Response]) -> str:
    try:
        newest = get(PYPI_URL).json()["info"]["version"]
        if newest == pins.wheel:
            return f"WHEEL     no {WHEEL} release after {pins.wheel}; the fix waits on upstream"
        carries = wheel_postgres(get(WHEEL_MAKEFILE_URL.format(version=newest)).text, pins.postgres[0])
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        return f"WHEEL     could not read the newest {WHEEL}: {exc}"
    if carries is None:
        return f"WHEEL     {WHEEL} {newest} is out; its source does not say which Postgres it builds"
    if carries >= target:
        return f"WHEEL     {WHEEL} {newest} builds Postgres {show(carries)}: move the wheel pin"
    if carries > pins.postgres:
        return (f"WHEEL     {WHEEL} {newest} builds Postgres {show(carries)}, not {show(target)}: "
                f"moving the wheel pin narrows the gap; the rest waits on upstream")
    return f"WHEEL     {WHEEL} {newest} still builds Postgres {show(carries)}; the fix waits on upstream"


def report(pins: Pins, *, transport: httpx.BaseTransport | None = None,
           sleep: Callable[[float], None] = time.sleep, today: date | None = None,
           github_token: str | None = None) -> tuple[int, list[str]]:
    """The verdict and its lines. BEHIND outranks UNKNOWN: one unreadable list does not
    hide a gap another list shows."""
    today = today or datetime.now(UTC).date()

    def get(url: str) -> httpx.Response:
        headers = {}
        if github_token and url.startswith("https://api.github.com/"):
            headers = {"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"}
        return upstream_http.get(url, user_agent=USER_AGENT, headers=headers, transport=transport, sleep=sleep)

    lines: list[str] = []
    behind = unknown = False
    major = pins.postgres[0]
    try:
        release = postgres_release(get(VERSIONS_URL).json(), major, today)
    except (httpx.HTTPError, ValueError) as exc:
        unknown = True
        lines.append(f"UNKNOWN   Postgres: could not read postgresql.org: {exc}")
    else:
        if not release.supported:
            behind = True
            lines.append(f"BEHIND    Postgres {major} reached its end of life on {release.eol}; "
                         "it takes no more security releases")
        elif pins.postgres < release.latest:
            behind = True
            lines.append(f"BEHIND    Postgres {show(pins.postgres)} ships; {show(release.latest)} is out "
                         f"(Postgres {major} is supported until {release.eol})")
            lines.append(_wheel_line(pins, release.latest, get))
        else:
            lines.append(f"OK        Postgres {show(pins.postgres)} ships, the newest release of {major} "
                         f"(supported until {release.eol})")
    try:
        latest_pgvector = newest_pgvector(get(PGVECTOR_TAGS_URL).json(), pins.pgvector[:2])
    except (httpx.HTTPError, ValueError) as exc:
        unknown = True
        lines.append(f"UNKNOWN   pgvector: could not read its tags: {exc}")
    else:
        if pins.pgvector < latest_pgvector:
            behind = True
            lines.append(f"BEHIND    pgvector {show(pins.pgvector)} ships; {show(latest_pgvector)} is out")
        else:
            lines.append(f"OK        pgvector {show(pins.pgvector)} ships, the newest release of "
                         f"{show(pins.pgvector[:2])}")
    code = EXIT_BEHIND if behind else EXIT_UNKNOWN if unknown else EXIT_OK
    return code, lines


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] = os.environ) -> int:
    argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0]).parse_args(argv)
    try:
        pins = pinned()
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"PIN BROKEN  {exc}")
        return EXIT_PIN_BROKEN
    code, lines = report(pins, github_token=environ.get("GITHUB_TOKEN"))
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
