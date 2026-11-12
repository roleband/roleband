"""Which test modules read past backend/, and so run on every pull request.

The backend workflow runs the whole suite only for a pull request that changes a path its
`changes` job watches. A test that reads a file above backend/ can be broken by a change to
any file, so it runs on every pull request: the workflow runs `-m repo_wide` when the
watched paths are untouched. A module is repo-wide when its source names a path above
backend/, or when it imports a `tests` helper that does, or when it runs `git ls-files`
itself, through a helper or through a `scripts` module it tests. Marking a module by mistake
costs only time; missing one lets a pull request skip a check it can break, which
`tests/test_ci_workflow_triggers.py` guards with the paths the code under test reads.

A pull request that changes only documentation (the workflow's `DOCS_PATHS`: Markdown files
and `docs/images/`) runs a narrower set, `-m reads_docs`: the repo-wide modules that list the
tracked tree, or whose code names a Markdown file, a `docs` path or a `*.md` glob, or import
a helper that does. Docstrings do not count. The source cannot show every read, so
`DocReads` watches the files each test opens and fails a test that opened documentation
without the mark.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import cache
from pathlib import Path

import pytest
import yaml

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parents[1]
#: The first-party packages a test imports by name, and where each lives.
PACKAGES = {"tests": TESTS, "scripts": TESTS.parent / "scripts"}

#: A path above backend/: the repository root by depth or by name, a parent of a parent, backend's
#: parent, or a relative `..`. Each also matches some paths inside backend/; marking those costs time only.
REACHES_PAST_BACKEND = re.compile(
    r"parents\[[2-9]\]|parents\[1\]\.parent|parent\.parent|\bREPO_ROOT\b|\bBACKEND(?:_DIR)?\.parent\b"
    r"|[\"']\.\./|/\s*[\"']\.\.[\"']|\bos\.pardir\b"
)

#: A string that names documentation: a Markdown file or glob, the docs folder or a path in it.
NAMES_DOCS = re.compile(r"\.md\b|^docs(?:/|$)")


def _helpers(source: str, packages: tuple[str, ...]) -> set[Path]:
    """The modules of `packages` a source imports, as files."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found |= {node.module, *(f"{node.module}.{alias.name}" for alias in node.names)}
    files = {
        PACKAGES[package] / f"{rest.replace('.', '/')}.py"
        for package, _, rest in (name.partition(".") for name in found)
        if package in packages and rest
    }
    # This module names paths to find the tests that read them, and reads none for them.
    return {path for path in files if path.is_file() and path != Path(__file__).resolve()}


def _reaches(module: Path, says: Callable[[str], bool], packages: tuple[str, ...] = ("tests",)) -> bool:
    """Whether the module, or a module of `packages` it imports, says so."""
    # Helpers may import each other, so the walk keeps the modules it has read.
    seen: set[Path] = set()
    pending = [module]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        source = current.read_text(encoding="utf-8")
        if says(source):
            return True
        pending.extend(_helpers(source, packages))
    return False


def _strings(source: str) -> list[str]:
    """The string constants of a source, without its docstrings."""
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


@cache
def lists_the_tree(module: Path) -> bool:
    """A module that runs `git ls-files`, itself or through what it imports, reads every tracked
    file. The `scripts` it tests count here: a tree scan names no path a tier could watch."""
    return _reaches(module, lambda source: "ls-files" in _strings(source), ("tests", "scripts"))


@cache
def reaches_past_backend(module: Path) -> bool:
    return _reaches(module, lambda source: bool(REACHES_PAST_BACKEND.search(source))) or lists_the_tree(module)


def names_docs(source: str) -> bool:
    """Whether code names documentation that can change alone; a path that runs the whole
    suite when it changes, such as `CHANGELOG.md`, cannot."""
    _, whole = _tiers()
    return any(NAMES_DOCS.search(value) and not whole.fullmatch(value) for value in _strings(source))


@cache
def reads_docs(module: Path) -> bool:
    """A repo-wide module that a documentation-only change can break."""
    return reaches_past_backend(module) and (lists_the_tree(module) or _reaches(module, names_docs))


def _glob_regex(pattern: str) -> str:
    """GitHub's filter glob, as `launcher/macos/Tools/ci_changes.py` reads it."""
    parts = re.split(r"(\*\*|\*|\?)", pattern)
    return "".join({"**": ".*", "*": "[^/]*", "?": "[^/]"}.get(part, re.escape(part)) for part in parts)


@cache
def _tiers() -> tuple[re.Pattern[str], re.Pattern[str]]:
    """The backend workflow's documentation paths, and the paths that run its whole suite."""
    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "backend.yml").read_text(encoding="utf-8"))
    env = next(step for step in workflow["jobs"]["changes"]["steps"] if step.get("id") == "decide")["env"]

    def union(text: str) -> re.Pattern[str]:
        return re.compile("|".join(_glob_regex(line.strip()) for line in text.splitlines() if line.strip()), re.DOTALL)

    return union(env["DOCS_PATHS"]), union(env["PATHS"])


def docs_only_path(path: str) -> bool:
    """A repository file a pull request can change while running only `-m reads_docs`."""
    docs, whole = _tiers()
    return bool(docs.fullmatch(path)) and not whole.fullmatch(path)


class DocReads:
    """A pytest plugin that fails a test which opened documentation without the `reads_docs` mark.

    An audit hook sees every `open`, so a read through a helper, a fixture, the module's import
    or the code under test counts as well as one the test names. A subprocess's reads are not
    seen; the marks come from the source, so a test that runs one names what it reads.
    """

    def __init__(self) -> None:
        self.opened: set[str] | None = None
        self._root = str(REPO) + os.sep
        self._imported: dict[Path, set[str]] = {}
        self._setup = pytest.StashKey[set[str]]()
        _tiers()
        sys.addaudithook(self._audit)

    def _audit(self, event: str, args: tuple) -> None:
        if event != "open" or self.opened is None or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        path = os.fsdecode(args[0])
        if not path.endswith(".md") and "images" not in path:
            return
        path = os.path.abspath(path)
        if path.startswith(self._root) and docs_only_path(relative := path[len(self._root):].replace(os.sep, "/")):
            self.opened.add(relative)

    @contextmanager
    def watching(self) -> Iterator[set[str]]:
        outer, self.opened = self.opened, set()
        opened = self.opened
        try:
            yield opened
        finally:
            if outer is not None:
                outer |= opened
            self.opened = outer

    @pytest.hookimpl(wrapper=True)
    def pytest_make_collect_report(self, collector):
        if not isinstance(collector, pytest.Module):
            return (yield)
        with self.watching() as opened:
            report = yield
        self._imported[collector.path] = opened
        return report

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_setup(self, item):
        with self.watching() as opened:
            result = yield
        item.stash[self._setup] = opened
        return result

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_call(self, item):
        with self.watching() as opened:
            result = yield
        opened |= item.stash.get(self._setup, set()) | self._imported.get(item.path, set())
        if why := unmarked_read(item.nodeid, item.get_closest_marker("reads_docs") is not None, opened):
            pytest.fail(why, pytrace=False)
        return result


def unmarked_read(nodeid: str, marked: bool, opened: set[str]) -> str | None:
    """Why a test fails: it opened documentation and is not marked to read it."""
    if marked or not opened:
        return None
    return (
        f"{nodeid} opened {sorted(opened)}, which a pull request can change alone, but "
        "tests/repo_wide.py does not mark it `reads_docs`: name the file in its module, "
        "so a documentation-only pull request runs it"
    )
