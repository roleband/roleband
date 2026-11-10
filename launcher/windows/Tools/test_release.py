import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from identity import FEED, PACKAGE_NAME, PUBLISHER

TOOL = Path(__file__).with_name("release.py")
WINDOWS = Path(__file__).resolve().parents[1]
ROOT = WINDOWS.parents[1]
COMMIT = "c" * 40
VERSION = json.loads((ROOT / "dashboard/package.json").read_text(encoding="utf-8"))["version"]
PASSPHRASE_ENV = "ROLEBAND_TEST_RELEASE_PASSPHRASE"


def package(path, name="RoleBand.Windows.Trial", publisher="CN=RoleBand Windows Trial", version=f"{VERSION}.1"):
    """A package whose manifest states its identity, as makeappx writes it."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AppxManifest.xml",
                         '<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">'
                         f'<Identity Name="{name}" Publisher="{publisher}" Version="{version}" '
                         'ProcessorArchitecture="x64" /></Package>')
        archive.writestr("payload.bin", b"synthetic package")


def release_package(path, display_name="RoleBand", start_name="RoleBand", kept=r"$(KnownFolder:LocalAppData)\RoleBand"):
    """The committed manifest with the release's identity, and its name and kept folder as given: a correct release
    stamp by default, or what a stamp that missed an element leaves."""
    manifest = (WINDOWS / "AppxManifest.xml").read_text(encoding="utf-8")
    manifest = re.sub(r"<Identity [^>]*/>", f'<Identity Name="{PACKAGE_NAME}" Publisher="{PUBLISHER}" '
                      f'Version="{VERSION}.0" ProcessorArchitecture="x64" />', manifest)
    manifest = re.sub(r"<DisplayName>[^<]*</DisplayName>", f"<DisplayName>{display_name}</DisplayName>", manifest)
    manifest = re.sub(r'(<uap:VisualElements DisplayName=")[^"]*', lambda found: found[1] + start_name, manifest)
    manifest = re.sub(r"(<virtualization:ExcludedDirectory>)[^<]*", lambda found: found[1] + kept, manifest)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AppxManifest.xml", manifest)
        archive.writestr("payload.bin", b"synthetic package")


class ReleaseToolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.key = ed25519.Ed25519PrivateKey.generate()
        (self.root / "release.pem").write_bytes(self.key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        self.identify("roleband/roleband-trials", "RoleBand.Windows.Trial", "CN=RoleBand Windows Trial")
        package(self.root / "built.msix")

    def tearDown(self):
        self.directory.cleanup()

    def identify(self, feed, name, publisher):
        (self.root / "identity.json").write_text(json.dumps({
            "format": 1, "feed": feed, "package_name": name, "publisher": publisher,
            "release_public_key": base64.b64encode(self.key.public_key().public_bytes_raw()).decode()}))

    def run_tool(self, *arguments, passphrase=None):
        environment = {name: value for name, value in os.environ.items() if name != PASSPHRASE_ENV}
        if passphrase is not None:
            environment[PASSPHRASE_ENV] = passphrase
        return subprocess.run([sys.executable, str(TOOL), *arguments], capture_output=True, text=True,
                              env=environment)

    def prepare(self, *arguments, passphrase=None, revision="1"):
        return self.run_tool("prepare", "--package", str(self.root / "built.msix"), "--destination",
                             str(self.root / "release"), "--identity", str(self.root / "identity.json"),
                             "--key", str(self.root / "release.pem"), "--revision", revision, "--commit", COMMIT,
                             *arguments, passphrase=passphrase)

    def verify(self, installed="0.0.1"):
        return self.run_tool("verify", "--directory", str(self.root / "release"), "--identity",
                             str(self.root / "identity.json"), "--installed", installed)

    def test_a_prepared_release_verifies(self):
        self.assertEqual(self.prepare().returncode, 0)
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        offer = json.loads(result.stdout)
        self.assertEqual(offer["commit"], COMMIT)
        self.assertTrue(offer["package_version"].endswith(".1"))

    def test_a_replaced_package_is_refused(self):
        self.assertEqual(self.prepare().returncode, 0)
        package = next((self.root / "release").glob("*.msix"))
        package.write_bytes(package.read_bytes() + b"\0")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match its signed checksum", result.stderr)

    def test_an_extra_file_in_the_release_is_refused(self):
        self.assertEqual(self.prepare().returncode, 0)
        (self.root / "release" / "install.ps1").write_text("Remove-Item")
        self.assertIn("unexpected files", self.verify().stderr)

    def test_a_package_stating_another_identity_or_version_is_not_released(self):
        for stated in ({"name": "RoleBand.Other"}, {"publisher": "CN=Someone Else"}, {"version": "9.9.9.1"},
                       {"version": f"{VERSION}.0"}):
            with self.subTest(stated=stated):
                package(self.root / "built.msix", **stated)
                result = self.prepare()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("The package states", result.stderr)
                self.assertFalse((self.root / "release").exists(), "nothing is written for it")
        (self.root / "built.msix").write_bytes(b"PK\x03\x04 not an archive")
        self.assertIn("no readable AppxManifest.xml", self.prepare().stderr)

    def test_an_installed_version_at_or_past_the_release_is_not_offered(self):
        self.assertEqual(self.prepare().returncode, 0)
        version = json.loads(next((self.root / "release").glob("*.json")).read_text())["version"]
        self.assertIn("not newer", self.verify(installed=version).stderr)

    def test_a_release_package_keeps_the_person_s_data_folder_and_says_roleband(self):
        """Windows deletes a package's LocalAppData folder on uninstall unless the manifest excludes it, so a release
        that kept the trial's folder would lose the person's data; its name would read as the trial's."""
        self.identify(FEED, PACKAGE_NAME, PUBLISHER)
        trial = r"$(KnownFolder:LocalAppData)\RoleBandTrials"
        for stamp in ({"display_name": "RoleBand Windows trial", "start_name": "RoleBand Windows trial", "kept": trial},
                      {"kept": trial}, {"display_name": "RoleBand Windows trial"},
                      {"start_name": "RoleBand Windows trial"}):
            with self.subTest(stamp=stamp):
                release_package(self.root / "built.msix", **stamp)
                result = self.prepare(revision="0")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("The package states", result.stderr)
                self.assertFalse((self.root / "release").exists(), "nothing is written for it")
        release_package(self.root / "built.msix")
        result = self.prepare(revision="0")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_encrypted_key_opens_only_with_its_passphrase_and_says_why_not(self):
        (self.root / "release.pem").write_bytes(self.key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(b"the release passphrase")))
        for passphrase, reason in ((None, f"{PASSPHRASE_ENV} holds no passphrase"),
                                   ("", f"{PASSPHRASE_ENV} holds no passphrase"),
                                   ("not the passphrase", "does not open with this passphrase")):
            with self.subTest(passphrase=passphrase):
                result = self.prepare("--passphrase-env", PASSPHRASE_ENV, passphrase=passphrase)
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertIn(reason, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
        result = self.prepare("--passphrase-env", PASSPHRASE_ENV, passphrase="the release passphrase")
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
