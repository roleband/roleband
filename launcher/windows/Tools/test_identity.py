import datetime
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID

from identity import PUBLISHER, SPARE_FILE, check, generate

ROOT = Path(__file__).resolve().parents[3]
PASSPHRASE, SPARE = b"signing passphrase one", b"spare passphrase two!"


class GenerateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.signing, self.spare = self.root / "signing", self.root / "offline" / "spare"
        self.identity = generate(self.signing, self.spare, PASSPHRASE, SPARE,
                                 now=datetime.datetime(2026, 11, 10, tzinfo=datetime.timezone.utc))
        self.cert = x509.load_der_x509_certificate((self.signing / "RoleBand.cer").read_bytes())

    def tearDown(self):
        self.directory.cleanup()

    def test_the_certificate_names_the_brand_and_its_domain_and_can_only_sign_code(self):
        self.assertEqual("CN=RoleBand,O=RoleBand,DC=roleband,DC=com", self.cert.subject.rfc4514_string())
        self.assertEqual(self.cert.subject, self.cert.issuer)
        self.assertFalse(self.cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        usage = self.cert.extensions.get_extension_for_class(x509.KeyUsage).value
        self.assertTrue(usage.digital_signature)
        self.assertFalse(usage.key_cert_sign)
        self.assertEqual([ExtendedKeyUsageOID.CODE_SIGNING],
                         list(self.cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value))
        self.assertEqual(2051, self.cert.not_valid_after_utc.year, "25 years, since nothing is timestamped")

    def test_the_identity_names_the_shared_feed_the_package_and_both_keys(self):
        sys.path.insert(0, str(ROOT / "backend"))
        from tracker.platform.windows_release import read_identity

        identity = read_identity(json.loads((self.signing / "release-identity.json").read_text(encoding="utf-8")))
        self.assertEqual(("roleband/roleband", "RoleBand.RoleBand", PUBLISHER),
                         (identity.feed, identity.package_name, identity.publisher))
        self.assertIsNotNone(identity.spare_key)
        self.assertEqual(identity.spare_key, serialization.load_pem_private_key(
            (self.spare / SPARE_FILE).read_bytes(), SPARE).public_key().public_bytes_raw())

    def test_the_spare_is_never_beside_the_signing_material_and_nothing_opens_without_its_passphrase(self):
        self.assertEqual({"RoleBand-signing.pfx", "RoleBand.cer", "release-key.pem", "release-identity.json"},
                         {path.name for path in self.signing.iterdir()})
        self.assertEqual({SPARE_FILE}, {path.name for path in self.spare.iterdir()})
        with self.assertRaises(ValueError):
            pkcs12.load_key_and_certificates((self.signing / "RoleBand-signing.pfx").read_bytes(), b"wrong")
        with self.assertRaises(TypeError):
            serialization.load_pem_private_key((self.signing / "release-key.pem").read_bytes(), None)

    def test_an_identity_is_written_once_and_never_into_one_folder(self):
        with self.assertRaisesRegex(ValueError, "new, empty folder"):
            generate(self.signing, self.root / "other", PASSPHRASE, SPARE)
        with self.assertRaisesRegex(ValueError, "apart"):
            generate(self.root / "a", self.root / "a" / "spare", PASSPHRASE, SPARE)
        with self.assertRaisesRegex(ValueError, "two different passphrases"):
            generate(self.root / "b", self.root / "c", PASSPHRASE, PASSPHRASE)
        with self.assertRaisesRegex(ValueError, "16 characters"):
            generate(self.root / "d", self.root / "e", b"short", SPARE)

    def test_check_accepts_only_the_material_the_committed_identity_names(self):
        pfx = (self.signing / "RoleBand-signing.pfx").read_bytes()
        key = (self.signing / "release-key.pem").read_bytes()
        self.assertEqual(64, len(check(pfx, key, PASSPHRASE, self.identity)))
        other = generate(self.root / "other-signing", self.root / "other-spare", PASSPHRASE, SPARE)
        with self.assertRaisesRegex(ValueError, "not the one the committed identity names"):
            check(pfx, key, PASSPHRASE, other)
        with self.assertRaisesRegex(ValueError, "does not open"):
            check(pfx, key, b"not the passphrase", self.identity)

    @unittest.skipUnless(sys.platform == "win32", "Windows renders the subject")
    def test_windows_renders_the_subject_as_the_package_publisher(self):
        shell = shutil.which("pwsh") or "powershell"
        rendered = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-Command",
             f"(New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 '{self.signing / 'RoleBand.cer'}').Subject"],
            check=True, capture_output=True, text=True).stdout.strip()
        self.assertEqual(PUBLISHER, rendered, "MSIX accepts a package only when its publisher is this string")


if __name__ == "__main__":
    unittest.main()
