"""A test that reads past backend/ is marked to run on every pull request."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import repo_wide


@pytest.fixture
def module(tmp_path):
    def write(source: str) -> Path:
        path = tmp_path / f"test_demo_{len(list(tmp_path.iterdir()))}.py"
        path.write_text(source)
        return path

    return write


@pytest.mark.parametrize(
    "source",
    [
        'ROOT = Path(__file__).resolve().parents[2]\n',
        'ROOT = Path(__file__).resolve().parent.parent.parent\n',
        'from tracker.platform.paths import REPO_ROOT\n',
        'FIXTURE = HERE / "../launcher/contracts/status-cases.json"\n',
        'from tests.plugin_web import serve\n',
        'ROOT = HERE / ".." / ".."\n',
        'ROOT = os.path.join(HERE, os.pardir, os.pardir)\n',
        'LOCK = BACKEND.parent / "launcher" / "macos" / "runtime-lock.txt"\n',
        'REPO = TRACKER.parent.parent\n',
        'ROOT = Path(__file__).resolve().parents[1].parent\n',
    ],
)
def test_a_module_naming_a_path_above_backend_is_repo_wide(module, source):
    assert repo_wide.reaches_past_backend(module(source))


@pytest.mark.parametrize(
    "source",
    [
        'FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"\n',
        'URL = "https://jobs.example.test/../acme"\n',
        'from tests.skip_policy import ALLOWED\n',
        'FIXTURE = Path(__file__).parent / "fixtures" / "a.json"\n',
    ],
)
def test_a_module_reading_inside_backend_is_not(module, source):
    """The control: the marker is not on every module, so the split saves something."""
    assert not repo_wide.reaches_past_backend(module(source))


def test_helpers_that_import_each_other_are_read_once(tmp_path, monkeypatch):
    monkeypatch.setitem(repo_wide.PACKAGES, "tests", tmp_path)
    (tmp_path / "a.py").write_text("from tests.b import x\n")
    (tmp_path / "b.py").write_text("from tests.a import y\n")
    assert not repo_wide.reaches_past_backend(tmp_path / "a.py")
    (tmp_path / "c.py").write_text("from tests.d import x\n")
    (tmp_path / "d.py").write_text('from tests.c import y\nROOT = HERE / ".."\n')
    assert repo_wide.reaches_past_backend(tmp_path / "c.py")


@pytest.mark.parametrize(
    "name",
    [
        "test_gitleaks_config.py",
        "test_release_gate.py",
        "test_docs_closed_set.py",
        "test_ci_workflow_triggers.py",
        "test_check_dependency_audit.py",
        "test_no_compat_shims.py",
    ],
)
def test_the_whole_tree_scans_are_repo_wide(name):
    assert repo_wide.reaches_past_backend(repo_wide.TESTS / name)


def test_collection_marks_the_repo_wide_tests(request):
    # This module names paths above backend/ in its examples, so it is repo-wide itself.
    assert request.node.get_closest_marker("repo_wide") is not None


# A pull request that changes only documentation runs the repo-wide tests that read it.


@pytest.mark.parametrize(
    "source",
    [
        'GUIDE = ROOT / "docs" / "testing.md"\n',
        'AGENTS = ROOT / "AGENTS.md"\n',
        'PAGES = sorted(ROOT.glob("*.md"))\n',
        'IMAGES = ROOT / "docs/images"\n',
        'NAME = f"{stem}.md"\n',
    ],
)
def test_a_module_naming_documentation_reads_docs(source):
    assert repo_wide.names_docs(source)


def test_a_script_that_lists_the_tree_makes_its_test_read_docs(tmp_path, monkeypatch):
    """A tree scan inside the code under test names no path, yet reads every page."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    monkeypatch.setitem(repo_wide.PACKAGES, "scripts", scripts)
    monkeypatch.setitem(repo_wide.PACKAGES, "tests", tmp_path)
    (scripts / "scan.py").write_text('FILES = subprocess.run(["git", "ls-files"], cwd=ROOT)\n')
    (scripts / "lint.py").write_text('"""Runs over `git ls-files`."""\nRULES = ["a"]\n')
    (tmp_path / "test_scan.py").write_text("from scripts.scan import FILES\n")
    (tmp_path / "test_lint.py").write_text("from scripts.lint import RULES\n")
    assert repo_wide.lists_the_tree(tmp_path / "test_scan.py")
    assert repo_wide.reads_docs(tmp_path / "test_scan.py")
    assert not repo_wide.lists_the_tree(tmp_path / "test_lint.py")
    assert not repo_wide.reaches_past_backend(tmp_path / "test_lint.py")


@pytest.mark.parametrize(
    "source",
    [
        '"""The README.md and docs/testing.md say so."""\n',
        'def f():\n    """See docs/ui.md."""\n',
        'CHANGELOG = ROOT / "CHANGELOG.md"\n',
        'SOURCES = ROOT / "docs/sources.md"\n',
        'PAGE = ROOT / "dashboard" / "README.mdx"\n',
        'URL = "https://example.test/docs/start"\n',
        '# docs/testing.md\nFIXTURE = HERE / "fixtures" / "a.json"\n',
    ],
)
def test_a_docstring_or_a_path_that_runs_the_whole_suite_does_not(source):
    """The control: a page cited in prose, or one the whole suite watches, is no reason to run."""
    assert not repo_wide.names_docs(source)


def test_a_helper_that_names_documentation_carries_it_to_its_importer(tmp_path, monkeypatch):
    monkeypatch.setitem(repo_wide.PACKAGES, "tests", tmp_path)
    (tmp_path / "pages.py").write_text('README = ROOT / "README.md"\n')
    (tmp_path / "test_a.py").write_text('from tests.pages import README\nROOT = HERE / ".."\n')
    (tmp_path / "test_b.py").write_text('ROOT = HERE / ".."\n')
    assert repo_wide._reaches(tmp_path / "test_a.py", repo_wide.names_docs)
    assert not repo_wide._reaches(tmp_path / "test_b.py", repo_wide.names_docs)


@pytest.mark.parametrize(
    "name",
    [
        "test_gitleaks_config.py",
        "test_release_gate.py",
        "test_docs_closed_set.py",
        "test_agents_doc.py",
        "test_usage_docs.py",
        "test_ci_workflow_pins.py",
        "test_comment_hygiene.py",
        "test_project_name.py",
    ],
)
def test_the_documentation_checks_and_whole_tree_scans_read_docs(name):
    assert repo_wide.reads_docs(repo_wide.TESTS / name)


@pytest.mark.parametrize("name", ["test_supervisor_runner.py", "test_windows_records.py", "test_packaged_engine.py"])
def test_a_repo_wide_module_that_reads_no_documentation_does_not(name):
    """The control: the docs set is narrower than the repo-wide set, so the split saves something."""
    module = repo_wide.TESTS / name
    assert repo_wide.reaches_past_backend(module)
    assert not repo_wide.reads_docs(module)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("README.md", True),
        ("docs/testing.md", True),
        ("docs/decisions/0000-template.md", True),
        ("docs/images/board-dark.webp", True),
        ("CHANGELOG.md", False),
        ("docs/sources.md", False),
        ("backend/tracker/levels/atlas/README.md", False),
        ("examples/plugin-template/README.md", False),
        ("docs/notes.txt", False),
    ],
)
def test_documentation_is_what_can_change_without_running_the_whole_suite(path, expected):
    assert repo_wide.docs_only_path(path) is expected


def test_the_guard_sees_a_documentation_file_this_test_opens(request, tmp_path):
    reads = request.config.pluginmanager.get_plugin("doc-reads")
    (repo_wide.REPO / "AGENTS.md").read_text()
    (repo_wide.REPO / "CHANGELOG.md").read_text()
    (repo_wide.REPO / "backend" / "pytest.ini").read_text()
    (tmp_path / "README.md").write_text("a page outside the repository\n")
    assert reads.opened == {"AGENTS.md"}
    assert request.node.get_closest_marker("reads_docs") is not None


def _item(marked: bool):
    return SimpleNamespace(
        nodeid="tests/test_demo.py::test_reads",
        path=repo_wide.TESTS / "test_demo.py",
        stash=pytest.Stash(),
        get_closest_marker=lambda name: object() if marked and name == "reads_docs" else None,
    )


def _call(reads: repo_wide.DocReads, item, read: Path | None) -> None:
    call = reads.pytest_runtest_call(item)
    next(call)
    if read is not None:
        read.read_text()
    with pytest.raises(StopIteration):
        call.send(None)


def test_an_unmarked_test_that_opens_documentation_fails():
    """The control: a test the docs tier would skip fails the run that reads a page."""
    reads = repo_wide.DocReads()
    with pytest.raises(pytest.fail.Exception, match=r"opened \['README.md'\].*reads_docs"):
        _call(reads, _item(marked=False), repo_wide.REPO / "README.md")
    _call(reads, _item(marked=True), repo_wide.REPO / "README.md")
    _call(reads, _item(marked=False), repo_wide.REPO / "CHANGELOG.md")
    _call(reads, _item(marked=False), None)
