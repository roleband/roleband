"""The embedded Postgres and pgvector are watched against their own upstream releases.

`tests/fixtures/postgres_versions.json` is an excerpt of postgresql.org's release list
(`scripts.check_embedded_postgres.VERSIONS_URL`). The pgvector tags and the wheel's
Makefile lines below are excerpts of what GitHub serves. The networked script reports
against the live lists; these tests pin the verdicts it draws from them.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import httpx
import pytest

from scripts.check_embedded_postgres import (
    EXIT_BEHIND,
    EXIT_OK,
    EXIT_UNKNOWN,
    MANIFEST,
    PGVECTOR_TAGS_URL,
    PYPI_URL,
    VERSIONS_URL,
    WHEEL_MAKEFILE_URL,
    WHEEL_PINS,
    Pins,
    newest_pgvector,
    pinned,
    postgres_release,
    report,
    wheel_postgres,
)

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = json.loads((Path(__file__).parent / "fixtures" / "postgres_versions.json").read_text())
TAGS = [{"name": f"v0.8.{patch}"} for patch in range(8)] + [{"name": "v0.7.4"}]
TODAY = date(2026, 11, 12)
# The release that put 16.15 and 18.6 in the wheel, and the older layout that named one
# version per build in pgbuild/Makefile.
MAKEFILE_0_7_2 = (
    "\tPOSTGRES_VERSION=16.15 PGSERVER_INSTALL_PACKAGE=pginstall $(MAKE) -d -C pgbuild all\n"
    "\tPOSTGRES_VERSION=18.6 PGSERVER_INSTALL_PACKAGE=pginstall18 $(MAKE) -d -C pgbuild all\n"
)
MAKEFILE_OLD = "SHELL := /bin/bash\nPOSTGRES_VERSION := 16.8\nPGVECTOR_TAG := v0.8.0\n"


def test_the_repository_pins_one_postgres_and_one_wheel_everywhere():
    from tracker.platform.embedded_db import DEFAULT_POSTGRES_VERSION, VERIFIED_UPSTREAM_VERSIONS

    pins = pinned(ROOT)
    assert pins.wheel in VERIFIED_UPSTREAM_VERSIONS
    assert pins.postgres[0] == DEFAULT_POSTGRES_VERSION
    assert pins.pgvector[:2] == (0, 8)


def _copy_pins(tmp_path: Path, edit_manifest=None, edit_pin=None) -> Path:
    for path in (MANIFEST, *WHEEL_PINS):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    if edit_manifest:
        target = tmp_path / MANIFEST
        manifest = json.loads(target.read_text())
        edit_manifest(manifest)
        target.write_text(json.dumps(manifest))
    if edit_pin:
        target = tmp_path / WHEEL_PINS[-1]
        target.write_text(edit_pin(target.read_text()))
    return tmp_path


def test_an_untouched_copy_of_the_pins_reads_the_same(tmp_path):
    assert pinned(_copy_pins(tmp_path)) == pinned(ROOT)


def _windows(manifest):
    return manifest["platforms"]["windows-amd64"]


@pytest.mark.parametrize("edit_manifest, edit_pin, message", [
    (lambda m: m.update(postgres="16.15"), None, "is not the 16.15 source"),
    (lambda m: m.update(postgres="16"), None, "not a Postgres version"),
    (lambda m: m.update(wheel_version="0.7.2"), None, "was built against"),
    (lambda m: _windows(m)["pgvector"].update(version="0.8.7"), None, "pgvector source is not 0.8.7"),
    (lambda m: _windows(m).pop("pgvector"), None, "one pgvector version"),
    (None, lambda text: text.replace("pixeltable-pgserver==0.6.0", "pixeltable-pgserver==0.7.2"), "pins pixeltable-pgserver"),
    (None, lambda text: "\n".join(line for line in text.splitlines() if "pixeltable-pgserver==" not in line), "nowhere"),
], ids=["source-url", "not-a-version", "platform-wheel", "pgvector-url", "no-pgvector", "lock-moved", "lock-missing"])
def test_pins_that_disagree_are_refused(tmp_path, edit_manifest, edit_pin, message):
    root = _copy_pins(tmp_path, edit_manifest, edit_pin)
    with pytest.raises(ValueError, match=message):
        pinned(root)


def test_the_newest_minor_and_end_of_life_of_the_pinned_major():
    release = postgres_release(VERSIONS, 16, TODAY)
    assert (release.latest, release.eol, release.supported) == ((16, 16), date(2028, 11, 9), True)


def test_a_major_past_its_end_of_life_date_is_unsupported_before_the_list_says_so():
    assert postgres_release(VERSIONS, 16, date(2028, 11, 9)).supported is False
    assert postgres_release(VERSIONS, 13, TODAY).supported is False


@pytest.mark.parametrize("versions, message", [
    ([v for v in VERSIONS if v["major"] != "16"], "holds no Postgres 16"),
    ({"16": "16"}, "without a list"),
    ([*VERSIONS, "16.16"], "without a list"),
    ([{**v, "latestMinor": "sixteen"} if v["major"] == "16" else v for v in VERSIONS], "malformed"),
    ([{k: x for k, x in v.items() if k != "supported"} if v["major"] == "16" else v for v in VERSIONS],
     "whether it is supported"),
    ([{**v, "supported": "true"} if v["major"] == "16" else v for v in VERSIONS], "whether it is supported"),
], ids=["absent", "object", "string-entry", "bad-minor", "no-support-status", "string-support-status"])
def test_a_list_that_says_nothing_about_the_major_gives_no_verdict(versions, message):
    with pytest.raises(ValueError, match=message):
        postgres_release(versions, 16, TODAY)


def test_only_a_final_release_of_the_pinned_pgvector_series_counts():
    assert newest_pgvector(TAGS, (0, 8)) == (0, 8, 7)
    noise = [{"name": "v0.9.0"}, {"name": "v0.8.9-rc1"}, {"name": "0.8.9"}, {"name": "v0.8.9.1"}]
    assert newest_pgvector([*TAGS, *noise], (0, 8)) == (0, 8, 7)
    with pytest.raises(ValueError, match="no 0.6"):
        newest_pgvector(TAGS, (0, 6))


@pytest.mark.parametrize("makefile, major, expected", [
    (MAKEFILE_0_7_2, 16, (16, 15)),
    (MAKEFILE_0_7_2, 18, (18, 6)),
    (MAKEFILE_OLD, 16, (16, 8)),
    (MAKEFILE_OLD, 18, None),
    ("all:\n\tmake -C pgbuild\n", 16, None),
])
def test_the_postgres_a_wheel_builds_is_read_from_its_makefile(makefile, major, expected):
    assert wheel_postgres(makefile, major) == expected


SHIPPED = Pins(wheel="0.6.0", postgres=(16, 14), pgvector=(0, 8, 5))


def _upstream(versions=VERSIONS, tags=TAGS, newest_wheel="0.7.2", makefile=MAKEFILE_0_7_2):
    """A transport serving each upstream list; an int or exception in place of a body
    is the status or failure every request to that URL gets."""
    asked: list[str] = []
    bodies = {
        VERSIONS_URL: versions,
        PGVECTOR_TAGS_URL: tags,
        PYPI_URL: {"info": {"version": newest_wheel}},
        WHEEL_MAKEFILE_URL.format(version=newest_wheel): makefile,
    }

    def handle(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        asked.append(url)
        if url not in bodies:
            return httpx.Response(404)
        body = bodies[url]
        if isinstance(body, Exception):
            raise body
        if isinstance(body, int):
            return httpx.Response(body)
        if isinstance(body, str):
            return httpx.Response(200, text=body)
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handle), asked


def _report(pins=SHIPPED, **upstream):
    transport, asked = _upstream(**upstream)
    code, lines = report(pins, transport=transport, sleep=lambda _: None, today=TODAY)
    return code, lines, asked


def test_a_wheel_behind_postgres_names_the_gap_and_how_far_the_newest_wheel_closes_it():
    code, lines, _ = _report()
    assert code == EXIT_BEHIND
    assert lines == [
        "BEHIND    Postgres 16.14 ships; 16.16 is out (Postgres 16 is supported until 2028-11-09)",
        "WHEEL     pixeltable-pgserver 0.7.2 builds Postgres 16.15, not 16.16: "
        "moving the wheel pin narrows the gap; the rest waits on upstream",
        "BEHIND    pgvector 0.8.5 ships; 0.8.7 is out",
    ]


def test_a_newer_wheel_with_the_newest_postgres_says_to_move_the_pin():
    makefile = MAKEFILE_0_7_2.replace("16.15", "16.16")
    _, lines, _ = _report(newest_wheel="0.7.3", makefile=makefile)
    assert "WHEEL     pixeltable-pgserver 0.7.3 builds Postgres 16.16: move the wheel pin" in lines


def test_no_newer_wheel_says_the_fix_waits_on_upstream():
    _, lines, asked = _report(newest_wheel="0.6.0")
    assert "WHEEL     no pixeltable-pgserver release after 0.6.0; the fix waits on upstream" in lines
    assert not any("githubusercontent" in url for url in asked)


def test_a_newer_wheel_on_the_same_postgres_is_no_fix():
    _, lines, _ = _report(makefile=MAKEFILE_0_7_2.replace("16.15", "16.14"))
    assert "WHEEL     pixeltable-pgserver 0.7.2 still builds Postgres 16.14; the fix waits on upstream" in lines


def test_current_pins_pass_without_asking_pypi():
    code, lines, asked = _report(pins=Pins(wheel="0.7.3", postgres=(16, 16), pgvector=(0, 8, 7)))
    assert code == EXIT_OK
    assert [line.split()[0] for line in lines] == ["OK", "OK"]
    assert PYPI_URL not in asked


def test_a_major_past_its_end_of_life_is_behind_even_on_its_last_minor():
    versions = [{**v, "supported": False} if v["major"] == "16" else v for v in VERSIONS]
    code, lines, _ = _report(pins=Pins(wheel="0.7.3", postgres=(16, 16), pgvector=(0, 8, 7)), versions=versions)
    assert code == EXIT_BEHIND
    assert lines[0].startswith("BEHIND    Postgres 16 reached its end of life on 2028-11-09")


def test_an_unreadable_release_list_gives_no_verdict():
    code, lines, asked = _report(pins=Pins(wheel="0.7.3", postgres=(16, 16), pgvector=(0, 8, 7)), versions=503)
    assert code == EXIT_UNKNOWN
    assert lines[0].startswith("UNKNOWN   Postgres: could not read postgresql.org")
    assert asked.count(VERSIONS_URL) == 3


def test_a_gap_one_list_shows_is_not_hidden_by_another_list_failing():
    code, lines, _ = _report(tags=httpx.ConnectError("refused"))
    assert code == EXIT_BEHIND
    assert lines[-1].startswith("UNKNOWN   pgvector: could not read its tags")


def test_an_unreadable_wheel_source_still_reports_the_gap():
    code, lines, _ = _report(makefile=404)
    assert code == EXIT_BEHIND
    assert lines[1].startswith("WHEEL     could not read the newest pixeltable-pgserver")


def test_the_github_token_reaches_only_the_github_api():
    seen: dict[str, str | None] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen[request.url.host] = request.headers.get("Authorization")
        if str(request.url) == VERSIONS_URL:
            return httpx.Response(200, json=VERSIONS)
        return httpx.Response(200, json=TAGS)

    report(Pins(wheel="0.7.3", postgres=(16, 16), pgvector=(0, 8, 7)), transport=httpx.MockTransport(handle),
           sleep=lambda _: None, today=TODAY, github_token="secret")
    assert seen == {"www.postgresql.org": None, "api.github.com": "Bearer secret"}
