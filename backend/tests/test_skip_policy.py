"""The CI skip policy: required skips fail, named optional skips stay skips.

Most of this runs a real, separate pytest over a throwaway test file, because a
hook that is not registered, or that edits the wrong report, passes every
in-process assertion about its helpers.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import skip_policy

BACKEND = Path(__file__).resolve().parents[1]

_SAMPLE = '''
import pytest

def test_passes():
    assert True

def test_database_missing():
    pytest.skip("database unavailable (ConnectionRefusedError: nothing listening)")

def test_model_missing():
    pytest.skip("embedding model not available offline")
'''

_COLLECTION_SKIP = '''
import pytest

pytest.importorskip("a_module_that_is_not_installed_anywhere", reason="embedded Postgres wheel not installed")

def test_never_collected():
    assert True
'''


def _run(tmp_path: Path, files: dict[str, str], *, enforced: bool) -> subprocess.CompletedProcess:
    for name, body in files.items():
        (tmp_path / name).write_text(body)
    # An empty ini of its own: the repo's workers and conftest stay out of it.
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    env = {**os.environ, "PYTHONPATH": str(BACKEND)}
    env.pop(skip_policy.ENV_FLAG, None)
    if enforced:
        env[skip_policy.ENV_FLAG] = "1"
    return subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "-p", "tests.skip_policy", "-c", str(tmp_path / "pytest.ini"),
            "--rootdir", str(tmp_path), *files,
        ],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )


class TestEndToEnd:
    def test_a_database_skip_fails_when_integration_is_required(self, tmp_path):
        proc = _run(tmp_path, {"test_sample.py": _SAMPLE}, enforced=True)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 1, out
        assert "1 failed, 1 passed, 1 skipped" in out, out
        assert "database unavailable" in out, "the failure names the refused reason"

    def test_the_same_file_is_green_when_integration_is_not_required(self, tmp_path):
        """The control: without it, the test above could pass on a runner that
        failed every file for some unrelated reason."""
        proc = _run(tmp_path, {"test_sample.py": _SAMPLE}, enforced=False)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, out
        assert "1 passed, 2 skipped" in out, out

    def test_a_skip_at_collection_is_refused_too(self, tmp_path):
        """`importorskip` at module level makes no runtest report at all."""
        proc = _run(tmp_path, {"test_collection.py": _COLLECTION_SKIP}, enforced=True)
        out = proc.stdout + proc.stderr
        assert proc.returncode != 0, out
        assert "embedded Postgres wheel not installed" in out, out


class TestClassification:
    @pytest.mark.parametrize(
        "reason",
        [
            "no database configured",
            "database unavailable (OSError: [Errno 61] Connect call failed)",
            "embedded Postgres wheel not installed",
            "repo venv not present",
            "a reason nobody has reviewed yet",
            # The Linux lane provisions the golden test's model, so a missing one is a failure there.
            "MiniLM ONNX artifacts not provisioned locally",
        ],
    )
    def test_required_reasons_are_not_optional(self, reason):
        assert not skip_policy.is_optional(reason, windows=False)

    @pytest.mark.parametrize(
        "reason",
        [
            "embedding model not available offline",
            "apple serves no robots file",
            "workday genuinely covers canada",
            "caffeinate is macOS's",
        ],
    )
    def test_named_optional_reasons_stay_skips(self, reason):
        assert skip_policy.is_optional(reason)

    @pytest.mark.parametrize("reason", ["macOS and POSIX tooling runs on the Mac", "gitleaks is not installed",
                                        "no zoneinfo file for Europe/Stockholm on this machine"])
    def test_a_windows_reason_stays_a_skip_on_windows_only(self, reason):
        """The Linux lane is where these run, so there the same reason is a failure."""
        assert skip_policy.is_optional(reason, windows=True)
        assert not skip_policy.is_optional(reason, windows=False)

    def test_an_optional_pattern_does_not_excuse_a_longer_reason(self):
        """Full match, not search: a prefix must not smuggle a new reason in."""
        assert not skip_policy.is_optional(
            "embedding model not available offline and the database is down"
        )


def _fires_off_windows(condition: ast.expr | None) -> bool:
    """`sys.platform != "win32"` or `os.name != "nt"`: true on every CI runner."""
    if not (isinstance(condition, ast.Compare) and len(condition.ops) == 1
            and isinstance(condition.ops[0], ast.NotEq) and isinstance(condition.left, ast.Attribute)
            and isinstance(condition.left.value, ast.Name)
            and isinstance(condition.comparators[0], ast.Constant)):
        return False
    subject = (condition.left.value.id, condition.left.attr, condition.comparators[0].value)
    return subject in {("sys", "platform", "win32"), ("os", "name", "nt")}


def _off_windows_skips(root: Path) -> list[tuple[str, object]]:
    """(file, reason) of every `skipif` that skips everywhere except Windows."""
    found = []
    for path in sorted(root.rglob("test_*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "skipif"
                    and node.args and _fires_off_windows(node.args[0])):
                reason = next((keyword.value for keyword in node.keywords if keyword.arg == "reason"), None)
                found.append((path.name, reason.value if isinstance(reason, ast.Constant) else ast.dump(reason or node)))
    return found


class TestWindowsOnlyFiles:
    """A Windows-only test skips on the Linux runner, where the policy turns an
    unnamed reason into a failure of every test that carries it."""

    def test_every_skip_that_fires_off_windows_is_a_named_reason(self):
        skips = _off_windows_skips(BACKEND / "tests")
        assert {"test_windows_restore.py", "test_windows_recovery.py", "test_windows_restart.py",
                "test_windows_state.py"} <= {name for name, _reason in skips}
        refused = [(name, reason) for name, reason in skips
                   if not isinstance(reason, str) or not skip_policy.is_optional(reason)]
        assert not refused, "add these reasons to OPTIONAL_SKIPS with why they stay skips"

    def test_a_new_windows_file_with_an_unnamed_reason_is_found_and_refused(self, tmp_path):
        (tmp_path / "test_widgets.py").write_text(
            "import sys\nimport pytest\n"
            "pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows widgets require Windows')\n",
            encoding="utf-8",
        )
        (tmp_path / "test_elsewhere.py").write_text(
            "import sys\nimport pytest\n"
            "pytestmark = pytest.mark.skipif(sys.platform == 'win32', reason='POSIX only')\n",
            encoding="utf-8",
        )
        assert _off_windows_skips(tmp_path) == [("test_widgets.py", "Windows widgets require Windows")]
        assert not skip_policy.is_optional("Windows widgets require Windows")


def test_this_suite_runs_with_the_policy_registered(request):
    """Removing the conftest import would silently let required skips pass."""
    impls = request.config.pluginmanager.hook.pytest_runtest_makereport.get_hookimpls()
    assert any(impl.function is skip_policy.pytest_runtest_makereport for impl in impls)
