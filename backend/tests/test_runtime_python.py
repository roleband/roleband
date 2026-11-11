"""The apps' bundled Python is the newest release of its series.

`tests/fixtures/python_releases.json` is an excerpt of python.org's published release
list (`scripts.check_runtime_python.RELEASES_URL`). When a newer security release of
the pinned series comes out, add it there and move both runtime pins; the networked
script reports the same gap without a fixture.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.check_runtime_python import RUNTIME_PINS, behind, newest, pinned

ROOT = Path(__file__).resolve().parents[2]
RELEASES = json.loads((Path(__file__).parent / "fixtures" / "python_releases.json").read_text())


def test_both_apps_pin_the_newest_release_of_their_series():
    pins = pinned(ROOT)
    assert set(pins) == set(RUNTIME_PINS)
    assert behind(pins, RELEASES) == {}


def test_a_pin_behind_a_security_release_is_named_with_that_release():
    pins = {"launcher/macos/runtime.json": (3, 12, 13), "launcher/windows/runtime.json": (3, 12, 16)}
    assert behind(pins, RELEASES) == {"launcher/macos/runtime.json": ((3, 12, 13), (3, 12, 16))}


def test_a_release_added_to_the_list_puts_a_current_pin_behind():
    newer = [*RELEASES, {"name": "Python 3.12.17", "is_published": True, "pre_release": False}]
    assert behind({"pin": (3, 12, 16)}, newer) == {"pin": ((3, 12, 16), (3, 12, 17))}


@pytest.mark.parametrize("release", [
    {"name": "Python 3.12.17rc1", "is_published": True, "pre_release": True},
    {"name": "Python 3.12.17", "is_published": True, "pre_release": True},
    {"name": "Python 3.12.17", "is_published": False, "pre_release": False},
    {"name": "Python 3.13.19", "is_published": True, "pre_release": False},
    {"name": "Python 4.12.17", "is_published": True, "pre_release": False},
    {"name": "Python 3.12.17.1", "is_published": True, "pre_release": False},
])
def test_only_a_published_final_release_of_the_same_series_counts(release):
    assert newest([*RELEASES, release], (3, 12)) == (3, 12, 16)
    assert behind({"pin": (3, 12, 16)}, [*RELEASES, release]) == {}


def test_a_list_without_the_pinned_series_gives_no_verdict():
    only_313 = [release for release in RELEASES if release["name"].startswith("Python 3.13.")]
    with pytest.raises(ValueError, match="3.12"):
        behind({"pin": (3, 12, 16)}, only_313)


def _copy_pin(tmp_path: Path, edit) -> Path:
    target = tmp_path / "launcher/macos/runtime.json"
    target.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "launcher/macos/runtime.json", target)
    pin = json.loads(target.read_text())
    edit(pin)
    target.write_text(json.dumps(pin))
    return tmp_path


@pytest.mark.parametrize("edit", [
    lambda pin: pin.update(python="3.12.17"),
    lambda pin: pin.update(release="20991231"),
    lambda pin: pin["notices"].update(url=pin["notices"]["url"].replace(pin["python"], "3.12.0")),
], ids=["version", "build", "notices"])
def test_a_pin_whose_archives_name_another_build_is_refused(tmp_path, edit):
    root = _copy_pin(tmp_path, edit)
    with pytest.raises(ValueError, match="is not the"):
        pinned(root, ["launcher/macos/runtime.json"])
