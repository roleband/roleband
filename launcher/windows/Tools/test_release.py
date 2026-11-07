import base64
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

TOOL = Path(__file__).with_name("release.py")
COMMIT = "c" * 40


class ReleaseToolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.key = ed25519.Ed25519PrivateKey.generate()
        (self.root / "release.pem").write_bytes(self.key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        (self.root / "identity.json").write_text(json.dumps({
            "format": 1, "feed": "roleband/roleband-trials", "package_name": "RoleBand.Windows.Trial",
            "publisher": "CN=RoleBand Windows Trial",
            "release_public_key": base64.b64encode(self.key.public_key().public_bytes_raw()).decode()}))
        (self.root / "built.msix").write_bytes(b"PK\x03\x04 synthetic package")

    def tearDown(self):
        self.directory.cleanup()

    def run_tool(self, *arguments):
        return subprocess.run([sys.executable, str(TOOL), *arguments], capture_output=True, text=True)

    def prepare(self):
        return self.run_tool("prepare", "--package", str(self.root / "built.msix"), "--destination",
                             str(self.root / "release"), "--identity", str(self.root / "identity.json"),
                             "--key", str(self.root / "release.pem"), "--revision", "1", "--commit", COMMIT)

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

    def test_an_installed_version_at_or_past_the_release_is_not_offered(self):
        self.assertEqual(self.prepare().returncode, 0)
        version = json.loads(next((self.root / "release").glob("*.json")).read_text())["version"]
        self.assertIn("not newer", self.verify(installed=version).stderr)


if __name__ == "__main__":
    unittest.main()
