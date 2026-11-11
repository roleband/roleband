"""Is the apps' bundled Python behind the newest release of its series?

The Mac and Windows apps ship the standalone CPython that `launcher/macos/runtime.json`
and `launcher/windows/runtime.json` pin. Its series takes only security releases, so a
patch level behind the newest one lacks published fixes, such as those to the Expat
parser that `xml.etree` uses on fetched sitemaps. This reads both pins, reads
python.org's published releases and names every pin that is behind.

The verdict logic is tested offline against a copy of the release list
(`tests/test_runtime_python.py`); only this script fetches. Exit codes:

    0  every pin is the newest release of its series
    1  BEHIND: move the pin to the python-build-standalone build of the newest release
    2  PIN BROKEN: a pin's archive URLs name another build than its own fields
    3  UNKNOWN: python.org could not be read; no verdict about the pins

Usage (from `backend/`):

    .venv/bin/python -m scripts.check_runtime_python
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PINS = ("launcher/macos/runtime.json", "launcher/windows/runtime.json")
RELEASES_URL = "https://www.python.org/api/v2/downloads/release/?is_published=true"

EXIT_OK = 0
EXIT_BEHIND = 1
EXIT_PIN_BROKEN = 2
EXIT_UNKNOWN = 3

Version = tuple[int, int, int]
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
# A final release only: "Python 3.12.0rc3" and "Python 3.12.0a1" do not match.
_FINAL_RELEASE = re.compile(r"Python (\d+)\.(\d+)\.(\d+)")


def parse(version: str) -> Version:
    match = _VERSION.fullmatch(version)
    if not match:
        raise ValueError(f"{version!r} is not a final CPython version such as 3.12.16")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def show(version: Version) -> str:
    return ".".join(map(str, version))


def pinned(root: Path = REPO_ROOT, paths: Iterable[str] = RUNTIME_PINS) -> dict[str, Version]:
    """Each pin's CPython version. A pin whose archive URLs name another version or build
    than its own fields is refused, so the version read here is the one that ships."""
    pins = {}
    for path in paths:
        pin = json.loads((root / path).read_text())
        version, build = pin["python"], pin["release"]
        expected = f"/{build}/cpython-{version}+{build}-"
        for entry in (pin, pin.get("notices") or {}):
            url = entry.get("url")
            if url is not None and expected not in urllib.parse.unquote(url):
                raise ValueError(f"{path}: {url} is not the {version}+{build} build the pin names")
        pins[path] = parse(version)
    return pins


def newest(releases: Iterable[Mapping[str, Any]], series: tuple[int, int]) -> Version | None:
    """The newest published final release of `series`, from python.org's release list."""
    found = []
    for release in releases:
        match = _FINAL_RELEASE.fullmatch(str(release.get("name", "")))
        if not match or release.get("pre_release") or release.get("is_published") is False:
            continue
        major, minor, patch = (int(part) for part in match.groups())
        if (major, minor) == series:
            found.append((major, minor, patch))
    return max(found, default=None)


def behind(pins: Mapping[str, Version], releases: Iterable[Mapping[str, Any]]) -> dict[str, tuple[Version, Version]]:
    """Every pin older than the newest release of its own series, with that release. A list
    holding no release of a pinned series is refused: it says nothing about the pin."""
    releases = list(releases)
    late = {}
    for path, version in pins.items():
        latest = newest(releases, version[:2])
        if latest is None:
            raise ValueError(f"The release list holds no {version[0]}.{version[1]} release")
        if version < latest:
            late[path] = (version, latest)
    return late


def fetch_releases(transport: httpx.BaseTransport | None = None, attempts: int = 3,
                   pause: float = 5.0, sleep: Callable[[float], None] = time.sleep) -> list[dict[str, Any]]:
    """python.org's release list. A connection failure or a server error is tried again,
    `attempts` times in all; the last failure is raised."""
    with httpx.Client(timeout=30.0, follow_redirects=True, transport=transport,
                      headers={"User-Agent": "roleband-runtime-check"}) as client:
        for attempt in range(1, attempts + 1):
            try:
                response = client.get(RELEASES_URL)
                if response.status_code < 500:
                    break
                response.raise_for_status()
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == attempts:
                    raise
            sleep(pause * attempt)
    response.raise_for_status()
    releases = response.json()
    if not isinstance(releases, list):
        raise ValueError("python.org answered without a release list")
    return releases


def main() -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    try:
        pins = pinned()
    except (OSError, KeyError, ValueError) as exc:
        print(f"PIN BROKEN  {exc}")
        return EXIT_PIN_BROKEN
    try:
        late = behind(pins, fetch_releases())
    except (httpx.HTTPError, ValueError) as exc:
        print(f"UNKNOWN   could not check: {exc}")
        return EXIT_UNKNOWN
    for path, version in pins.items():
        if path in late:
            print(f"BEHIND    {path} pins {show(version)}; {show(late[path][1])} is out")
        else:
            print(f"OK        {path} pins {show(version)}, the newest release of its series")
    return EXIT_BEHIND if late else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
