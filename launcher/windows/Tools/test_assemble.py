import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from assemble import bundle_identity, clean_revision
from identity import FEED, PACKAGE_NAME, PUBLISHER, REHEARSAL_FEED

PACKAGE = Path(__file__).resolve().parents[1] / "Package.ps1"
TRIAL_FEED = "roleband/roleband-windows-trials"
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


def key(seed):
    return base64.b64encode(bytes([seed]) * 32).decode()


class BundleIdentityTests(unittest.TestCase):
    """A release trusts the committed release identity, and only one for RoleBand's own package on the shared feed;
    a trial trusts only its own trial identity, never the release's."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / "launcher/windows").mkdir(parents=True)
        shutil.copyfile(Path(__file__).resolve().parents[1] / "AppxManifest.xml",
                        self.root / "launcher/windows/AppxManifest.xml")

    def tearDown(self):
        self.directory.cleanup()

    def write(self, name="release-identity.json", **fields):
        record = {"format": 1, "feed": FEED, "release_public_key": key(1), "package_name": PACKAGE_NAME,
                  "publisher": PUBLISHER, "spare_release_public_key": key(2), **fields}
        path = self.root / "launcher/windows" / name
        path.write_text(json.dumps({field: value for field, value in record.items() if value is not None}))
        return path

    def trial(self, **fields):
        return self.write("trial-identity.json", **{"feed": TRIAL_FEED, "package_name": "RoleBand.Windows.Trial",
                                                    "publisher": "CN=RoleBand Windows Trial",
                                                    "spare_release_public_key": None, **fields})

    def test_a_release_without_an_update_identity_is_refused(self):
        with self.assertRaisesRegex(ValueError, "needs launcher/windows/release-identity.json"):
            bundle_identity(self.root, "release")

    def test_a_release_updates_only_from_the_shared_feed(self):
        self.write(feed=REHEARSAL_FEED)
        with self.assertRaisesRegex(ValueError, "updates from roleband/roleband"):
            bundle_identity(self.root, "release")
        path = self.write()
        self.assertEqual(path, bundle_identity(self.root, "release"))

    def test_a_release_is_roleband_s_own_package_and_publisher_and_names_a_spare(self):
        for fields, reason in (({"package_name": "RoleBand.Windows.Trial"}, "the package RoleBand.RoleBand"),
                               ({"publisher": "CN=RoleBand Windows Trial"}, "the package RoleBand.RoleBand"),
                               ({"spare_release_public_key": None}, "names a spare release key")):
            with self.subTest(fields=fields):
                self.write(**fields)
                with self.assertRaisesRegex(ValueError, reason):
                    bundle_identity(self.root, "release")

    def test_a_rehearsal_updates_only_from_the_trial_feed_and_never_from_the_public_one(self):
        path = self.write(feed=REHEARSAL_FEED)
        with self.assertRaisesRegex(ValueError, "A release updates from roleband/roleband"):
            bundle_identity(self.root, "release")
        self.assertEqual(path, bundle_identity(self.root, "release", rehearsal=True))
        self.write(feed=FEED)
        with self.assertRaisesRegex(ValueError, "A rehearsal updates from roleband/roleband-windows-trials"):
            bundle_identity(self.root, "release", rehearsal=True)

    def test_a_trial_never_carries_the_release_identity(self):
        self.write()
        self.assertIsNone(bundle_identity(self.root, "trial"), "a trial without its own identity offers no update")
        path = self.trial()
        self.assertEqual(path, bundle_identity(self.root, "trial"))

    def test_a_trial_identity_for_the_shared_feed_or_another_package_is_refused(self):
        for fields, reason in (({"feed": FEED}, "never updates from roleband/roleband"),
                               ({"feed": "RoleBand/RoleBand"}, "never updates from roleband/roleband"),
                               ({"package_name": PACKAGE_NAME}, "the trial package RoleBand.Windows.Trial"),
                               ({"publisher": PUBLISHER}, "the trial package RoleBand.Windows.Trial")):
            with self.subTest(fields=fields):
                self.trial(**fields)
                with self.assertRaisesRegex(ValueError, reason):
                    bundle_identity(self.root, "trial")
        (self.root / "launcher/windows/trial-identity.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "damaged"):
            bundle_identity(self.root, "trial")


@unittest.skipUnless(sys.platform == "win32", "Package.ps1 runs on Windows")
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
                 for path in self.bundle.rglob("*") if path.is_file() and path.name != "bundle-hashes.json"}
        (self.bundle / "bundle-hashes.json").write_text(json.dumps(files))

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

    def test_a_bundle_must_name_exactly_one_channel(self):
        (self.bundle / "Resources/build.json").write_text(json.dumps({"format": 1, "channel": "release", "dirty_paths": []}))
        self.record()
        self.assertIn("must name one channel", self.package())
        (self.bundle / "Resources/trial.json").unlink()
        (self.bundle / "Resources/build.json").unlink()
        self.assertIn("must name one channel", self.package())

    def test_a_release_bundle_needs_the_identity_that_names_its_publisher(self):
        (self.bundle / "Resources/trial.json").unlink()
        (self.bundle / "Resources/build.json").write_text(json.dumps({"format": 1, "channel": "release", "dirty_paths": []}))
        (self.bundle / "Resources/release-identity.json").write_text(json.dumps({"format": 1, "feed": FEED}))
        self.assertIn("names its package and publisher", self.package())

    def test_a_marker_naming_another_channel_is_refused(self):
        (self.bundle / "Resources/trial.json").unlink()
        (self.bundle / "Resources/build.json").write_text(json.dumps({"format": 1, "channel": "store", "dirty_paths": []}))
        self.assertIn("not one this script packages", self.package())

    def test_a_bundle_from_a_dirty_tree_is_refused(self):
        self.trial["dirty_paths"] = [" M backend/tracker/config.py"]
        self.record()
        self.assertIn("not assembled from a clean commit", self.package())


if __name__ == "__main__":
    unittest.main()
