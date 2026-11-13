"""The typed-boundary pilot: a narrow set that is honest, and stays that way.

What makes it look expensive is not the code: mypy follows imports by default,
so the entries in `[tool.mypy] files` drag in modules nobody put in the set and
report their errors. `follow_imports = silent` keeps the report to the set.

Five claims, because the first one alone can pass for the wrong reason:

1. the configured set type-checks clean;
2. it really checked something — a config that names nothing also "succeeds";
3. nothing in it was made green by muting rather than fixing;
4. the set may grow and may not shrink;
5. it is clean for every platform the app runs on, not only the one it runs on now.

Never add `ignore_errors` or widen a return to `Any` to get this green. Muting
is the one change that looks identical to fixing from outside.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_PYPROJECT = _BACKEND / "pyproject.toml"

#: The recorded set. A ratchet, compared as a SUBSET: adding a module needs no
#: edit here, removing one fails by name. The checked set is recorded and
#: expanded with each extraction, never quietly narrowed.
FROZEN: frozenset[str] = frozenset(
    {
        "tracker/schema.py",
        "tracker/pay_disclosure.py",
        "tracker/source_review.py",
        "tracker/vendored.py",
        "tracker/blueprint.py",
        "tracker/api/schemas",
        "tracker/platform/paging.py",
        "tracker/platform/ratelimit.py",
        "tracker/workflows/schedule_status.py",
        "tracker/workflows/tuning.py",
        "tracker/connectors/recipes/outcome.py",
        "tracker/db/ownership.py",
        "tracker/connectors/__init__.py",
        "tracker/connectors/listing",
        "tracker/connectors/runtime",
    }
)


#: Every platform the app runs on. mypy checks one at a time: the host's, unless
#: `--platform` names another. Code behind a gate for a platform it is not
#: checking is unreachable, which means read and not checked.
_PLATFORMS: tuple[str, ...] = ("win32", "darwin", "linux")

#: The platforms the run on this machine says nothing about.
_ELSEWHERE: tuple[str, ...] = tuple(p for p in _PLATFORMS if p != sys.platform)


def _config() -> dict:
    return tomllib.loads(_PYPROJECT.read_text())["tool"]["mypy"]


def _run_mypy(*args: str, cwd: Path = _BACKEND) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mypy", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _platform_cache(platform: str) -> Path:
    """A cache directory of its own, per platform.

    mypy keys a cache to the options that wrote it, so a host run and a platform
    run sharing one directory invalidate each other and both pay the cold cost
    every time. `.mypy_cache` is ignored, children included.
    """

    return _BACKEND / ".mypy_cache" / f"platform-{platform}"


# --------------------------------------------------------------------------- #
# 1-2. It passes, and it checked something
# --------------------------------------------------------------------------- #


def test_the_checked_set_type_checks_clean():
    run = _run_mypy()
    assert run.returncode == 0, (
        "the typed-boundary pilot does not pass:\n"
        + (run.stdout or run.stderr)[-3000:]
        + "\n\nFix the types. Do not add `ignore_errors` or return `Any` — a test below "
        "fails on both, because muting looks identical to fixing from outside."
    )


def test_it_actually_checked_the_files_it_names():
    """A config naming nothing reports success just as loudly.

    mypy prints the file count it checked, so the claim "clean" is only worth
    anything beside the claim "and there was something to check".
    """

    run = _run_mypy()
    assert "no issues found in" in run.stdout, run.stdout[-2000:]
    checked = int(run.stdout.split("no issues found in")[1].split()[0])
    assert checked >= len(FROZEN), (
        f"mypy checked {checked} files but the frozen set names {len(FROZEN)} entries. "
        "A path that stopped resolving makes the pilot pass by checking nothing."
    )


def test_mypy_reports_a_planted_error(tmp_path):
    """The control: the runner is wired up and would fail if there were a fault.

    Without this, every assertion above is satisfied by a mypy that cannot run —
    a missing plugin, a bad interpreter, an exit code nobody reads.
    """

    planted = tmp_path / "planted.py"
    planted.write_text("def f() -> int:\n    return 'not an int'\n")
    run = _run_mypy("--follow-imports=silent", "--no-incremental", str(planted), cwd=tmp_path)
    assert run.returncode != 0, f"mypy accepted a str returned from `-> int`: {run.stdout}"
    assert "return-value" in run.stdout or "Incompatible return" in run.stdout, run.stdout[-1000:]


# --------------------------------------------------------------------------- #
# 3. Green by fixing, not by muting
# --------------------------------------------------------------------------- #


def test_no_blanket_ignore_errors_on_our_own_modules():
    config = _config()
    assert "ignore_errors" not in config, (
        "`ignore_errors` at the top of [tool.mypy] mutes the whole pilot. Remove the "
        "module from `files` instead — a shrunken set is at least visible, and the "
        "ratchet below will say so."
    )
    muted = [
        module
        for override in config.get("overrides", [])
        if override.get("ignore_errors")
        for module in (
            override["module"] if isinstance(override["module"], list) else [override["module"]]
        )
        if module.startswith("tracker")
    ]
    assert not muted, (
        f"these of our own modules are muted with `ignore_errors`: {muted}. An override may "
        "silence a third-party package that ships no stubs; it may not silence us."
    )


def test_overrides_only_silence_third_party_imports():
    """`ignore_missing_imports` is for packages without stubs, not for our code."""

    stray = [
        module
        for override in _config().get("overrides", [])
        if override.get("ignore_missing_imports")
        for module in (
            override["module"] if isinstance(override["module"], list) else [override["module"]]
        )
        if module.startswith("tracker")
    ]
    assert not stray, f"`ignore_missing_imports` names our own modules: {stray}"


# --------------------------------------------------------------------------- #
# 4. The set may grow and may not shrink
# --------------------------------------------------------------------------- #


def test_the_checked_set_only_grows():
    configured = set(_config()["files"])
    dropped = sorted(FROZEN - configured)
    assert not dropped, (
        f"these modules left the typed set: {dropped}. It expands with each extraction and "
        "never narrows; if a module genuinely moved, update FROZEN in the same change and say "
        "where it went."
    )


def test_every_checked_path_exists():
    missing = sorted(p for p in _config()["files"] if not (_BACKEND / p).exists())
    assert not missing, f"[tool.mypy] files names paths that do not exist: {missing}"


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("follow_imports", "silent"),
        # Any version, as long as one is named.
        ("python_version", None),
        ("check_untyped_defs", True),
        ("disallow_incomplete_defs", True),
        ("warn_unused_ignores", True),
    ],
)
def test_the_settings_the_pilot_depends_on_are_pinned(setting, value):
    """`follow_imports = silent` is load-bearing, not tidiness.

    Dropping it does not fail loudly — it fails with errors in files nobody
    put in the set, which reads as "typing this codebase is impossible".

    The completeness flags fail quietly the other way: without them a
    parameter left unannotated is `Any`, and so is everything its body does
    with it, and a function with no annotations at all is not checked.
    """

    configured = _config().get(setting)
    if value is None:
        assert configured is not None, f"[tool.mypy] names no {setting}"
    else:
        assert configured == value, f"[tool.mypy] {setting} is {configured!r}, not {value!r}"


# --------------------------------------------------------------------------- #
# 5. Clean for every platform, not only the one this runs on
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("platform", _ELSEWHERE)
def test_the_checked_set_type_checks_clean_for_every_platform(platform):
    """A body gated to another platform is unreachable here, so nothing checks it.

    The Windows modules in the set open with `if sys.platform != "win32": raise
    ImportError(...)`. Off Windows mypy reads them, checks nothing inside, and
    still counts them among the files it checked, so every claim above holds
    while a half-annotated def sits in a body no run has looked at and the error
    waits for the Windows lane.

    An annotation is resolved even where the code around it is unreachable, so a
    name belonging to one platform cannot appear in one: `ctypes.WinDLL` is not a
    name off Windows, while its base class `ctypes.CDLL` is a name everywhere.
    """

    run = _run_mypy(f"--platform={platform}", f"--cache-dir={_platform_cache(platform)}")
    assert run.returncode == 0, (
        f"the typed-boundary pilot does not pass for {platform}:\n"
        + (run.stdout or run.stderr)[-3000:]
        + f"\n\nAnnotate the gated code for {platform} as well. An annotation that names a "
        "type only that platform has fails everywhere else, so name one every platform "
        "has: `ctypes.CDLL` where the value is a `ctypes.WinDLL`."
    )
    assert "no issues found in" in run.stdout, run.stdout[-2000:]
    checked = int(run.stdout.split("no issues found in")[1].split()[0])
    assert checked >= len(FROZEN), (
        f"mypy checked {checked} files for {platform} and the frozen set names "
        f"{len(FROZEN)} entries. A platform run that resolves nothing passes by "
        "checking nothing."
    )


def test_a_gate_hides_a_fault_the_platform_run_finds(tmp_path):
    """The control: the gate really does hide a fault, and `--platform` really finds it.

    Without this, the runs above are satisfied by a flag mypy ignores, or by a
    gate it stopped reading as a platform test, and they would pass on a set
    nothing had checked.
    """

    elsewhere = _ELSEWHERE[0]
    planted = tmp_path / "gated.py"
    planted.write_text(
        "import sys\n\n"
        f'if sys.platform != "{elsewhere}":\n'
        '    raise ImportError("another platform only")\n\n\n'
        "def gone(handle, timeout: int) -> bool:\n"
        "    return bool(handle) and timeout > 0\n"
    )
    flags = ("--follow-imports=silent", "--no-incremental", "--disallow-incomplete-defs")

    here = _run_mypy(*flags, str(planted), cwd=tmp_path)
    assert here.returncode == 0, (
        "mypy reported a fault in a body this platform cannot reach, so the gate hides "
        f"nothing and the runs above prove nothing: {here.stdout}"
    )

    there = _run_mypy(*flags, f"--platform={elsewhere}", str(planted), cwd=tmp_path)
    assert there.returncode != 0, (
        f"`--platform={elsewhere}` accepted a half-annotated def behind a {elsewhere} "
        f"gate, so a platform run finds nothing the host run misses: {there.stdout}"
    )
    assert "no-untyped-def" in there.stdout, there.stdout[-1000:]
