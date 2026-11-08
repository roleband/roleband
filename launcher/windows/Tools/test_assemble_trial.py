import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from assemble_trial import clean_revision

PACKAGE = Path(__file__).resolve().parents[1] / "Package-Trial.ps1"
#: PowerShell 7 where installed (CI runners), otherwise the Windows PowerShell every Windows has.
SHELL = shutil.which("pwsh") or "powershell"


def git(root, *arguments):
    subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)


class CleanRevisionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "trial@example.invalid")
        git(self.root, "config", "user.name", "Trial")
        (self.root / ".gitignore").write_text("__pycache__/\n*.pyc\n.env\n")
        engine = self.root / "backend/tracker"
        engine.mkdir(parents=True)
        (engine / "module.py").write_text("VALUE = 1\n")
        git(self.root, "add", ".")
        git(self.root, "commit", "-q", "-m", "fixture")

    def tearDown(self):
        self.directory.cleanup()

    def test_a_clean_commit_is_its_own_revision(self):
        cache = self.root / "backend/tracker/__pycache__"
        cache.mkdir()
        (cache / "module.cpython-312.pyc").write_bytes(b"\0")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()
        self.assertEqual(clean_revision(self.root), head)

    def test_a_tracked_edit_is_refused(self):
        (self.root / "backend/tracker/module.py").write_text("VALUE = 2\n")
        with self.assertRaisesRegex(ValueError, "Commit or remove local changes.*module.py"):
            clean_revision(self.root)

    def test_an_untracked_file_anywhere_is_refused(self):
        (self.root / "notes.txt").write_text("draft\n")
        with self.assertRaisesRegex(ValueError, "notes.txt"):
            clean_revision(self.root)

    def test_an_ignored_file_inside_the_engine_sources_is_refused(self):
        (self.root / "backend/tracker/.env").write_text("SECRET=1\n")
        with self.assertRaisesRegex(ValueError, "ignored files.*backend/tracker/.env"):
            clean_revision(self.root)

    def test_an_ignored_file_outside_the_engine_sources_is_allowed(self):
        (self.root / ".env").write_text("SECRET=1\n")
        clean_revision(self.root)


@unittest.skipUnless(sys.platform == "win32", "Package-Trial.ps1 runs on Windows")
class PackageProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.bundle = Path(self.directory.name) / "bundle"
        (self.bundle / "Resources/engine").mkdir(parents=True)
        (self.bundle / "Resources/engine/module.py").write_text("VALUE = 1\n")
        self.trial = {"trial_only": True, "trial_id": "a" * 32, "dirty_paths": []}
        self.record()

    def tearDown(self):
        self.directory.cleanup()

    def record(self):
        (self.bundle / "Resources/trial.json").write_text(json.dumps(self.trial))
        files = {str(path.relative_to(self.bundle)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in self.bundle.rglob("*") if path.is_file() and path.name != "trial-hashes.json"}
        (self.bundle / "trial-hashes.json").write_text(json.dumps(files))

    def package(self):
        result = subprocess.run(
            [SHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "RemoteSigned", "-File", str(PACKAGE),
             "-Bundle", str(self.bundle), "-Destination", str(Path(self.directory.name) / "out.msix")],
            check=False, capture_output=True, text=True)
        return result.stdout + result.stderr

    def test_an_unchanged_bundle_passes_the_provenance_check(self):
        self.assertNotIn("Assemble it again", self.package())

    def test_a_bundle_packaged_before_can_be_packaged_again(self):
        # A previous run left its manifest, assets and resource index, and recorded their hashes;
        # this run rebuilds all three, so their old contents are not provenance.
        (self.bundle / "Assets").mkdir()
        for name in ("AppxManifest.xml", "resources.pri", "Assets/StoreLogo.png"):
            (self.bundle / name).write_bytes(b"previous run")
        self.record()
        (self.bundle / "resources.pri").write_bytes(b"index of other assets")
        (self.bundle / "AppxManifest.xml").unlink()
        self.assertNotIn("Assemble it again", self.package())

    def test_an_edited_file_is_refused(self):
        (self.bundle / "Resources/engine/module.py").write_text("VALUE = 2\n")
        self.assertIn(r"Resources\engine\module.py was edited", self.package())

    def test_an_added_file_is_refused(self):
        (self.bundle / "Resources/engine/patch.py").write_text("PATCH = 1\n")
        self.assertIn(r"Resources\engine\patch.py was added", self.package())

    def test_a_removed_file_is_refused(self):
        (self.bundle / "Resources/engine/module.py").unlink()
        self.assertIn(r"Resources\engine\module.py was removed", self.package())

    def test_a_bundle_from_a_dirty_tree_is_refused(self):
        self.trial["dirty_paths"] = [" M backend/tracker/config.py"]
        self.record()
        self.assertIn("not assembled from a clean commit", self.package())


if __name__ == "__main__":
    unittest.main()
