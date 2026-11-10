import contextlib
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from identity import (
    FEED,
    PACKAGE_NAME,
    PUBLISHER,
    REHEARSAL_FEED,
    SPARE_FILE,
    YEARS,
    certificate,
    check,
    generate,
    main,
    passphrase,
    validate,
)

ROOT = Path(__file__).resolve().parents[3]
PASSPHRASE, SPARE = b"signing passphrase one", b"spare passphrase two!"
SIGNING_FILES = {"RoleBand-signing.pfx", "RoleBand.cer", "release-key.pem", "release-identity.json"}


def sealed(key, cert, extra=None):
    return pkcs12.serialize_key_and_certificates(b"RoleBand", key, cert, extra,
                                                 serialization.BestAvailableEncryption(PASSPHRASE))


def files(folder):
    return sorted(path.name for path in folder.rglob("*") if path.is_file()) if folder.exists() else []


class GenerateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.signing, self.spare = self.root / "signing", self.root / "offline" / "spare"
        self.identity = generate(self.signing, self.spare, PASSPHRASE, SPARE,
                                 now=datetime.datetime(2026, 11, 10, tzinfo=datetime.timezone.utc))
        self.cert = x509.load_der_x509_certificate((self.signing / "RoleBand.cer").read_bytes())
        self.pfx = (self.signing / "RoleBand-signing.pfx").read_bytes()
        self.key = (self.signing / "release-key.pem").read_bytes()
        self.public = (self.signing / "RoleBand.cer").read_bytes()

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
        identity = validate(json.loads((self.signing / "release-identity.json").read_text(encoding="utf-8")))
        self.assertEqual((FEED, PACKAGE_NAME, PUBLISHER), (identity.feed, identity.package_name, identity.publisher))
        self.assertEqual(identity.spare_key, serialization.load_pem_private_key(
            (self.spare / SPARE_FILE).read_bytes(), SPARE).public_key().public_bytes_raw())

    def test_a_rehearsal_identity_names_the_rehearsal_feed_and_is_valid_only_as_one(self):
        record = generate(self.root / "rehearsal-signing", self.root / "rehearsal-spare", PASSPHRASE, SPARE,
                          rehearsal=True)
        self.assertEqual(REHEARSAL_FEED, validate(record, rehearsal=True).feed)
        with self.assertRaisesRegex(ValueError, f"A release updates from {FEED}, not {REHEARSAL_FEED}"):
            validate(record)
        with self.assertRaisesRegex(ValueError, f"A rehearsal updates from {REHEARSAL_FEED}, not {FEED}"):
            validate(self.identity, rehearsal=True)

    def test_a_release_identity_names_roleband_s_own_package_and_publisher_and_a_spare(self):
        for field, value, reason in (
                ("feed", "roleband/roleband-windows-trials", "updates from roleband/roleband"),
                ("feed", "RoleBand/RoleBand", "updates from roleband/roleband"),
                ("package_name", "RoleBand.Windows.Trial", "the package RoleBand.RoleBand"),
                ("publisher", "CN=RoleBand Windows Trial", "the package RoleBand.RoleBand"),
                ("spare_release_public_key", None, "names a spare release key")):
            with self.subTest(field=field, value=value):
                record = dict(self.identity)
                if value is None:
                    del record[field]
                else:
                    record[field] = value
                with self.assertRaisesRegex(ValueError, reason):
                    validate(record)
                with self.assertRaisesRegex(ValueError, reason):
                    check(self.pfx, self.key, PASSPHRASE, record, self.public)

    def test_the_spare_is_never_beside_the_signing_material_and_nothing_opens_without_its_passphrase(self):
        self.assertEqual(SIGNING_FILES, {path.name for path in self.signing.iterdir()})
        self.assertEqual({SPARE_FILE}, {path.name for path in self.spare.iterdir()})
        with self.assertRaises(ValueError):
            pkcs12.load_key_and_certificates(self.pfx, b"wrong")
        with self.assertRaises(TypeError):
            serialization.load_pem_private_key(self.key, None)

    def test_an_identity_is_written_once_and_never_into_one_folder(self):
        with self.assertRaisesRegex(ValueError, "new, empty folder"):
            generate(self.signing, self.root / "other", PASSPHRASE, SPARE)
        with self.assertRaisesRegex(ValueError, "apart"):
            generate(self.root / "a", self.root / "a" / "spare", PASSPHRASE, SPARE)
        with self.assertRaisesRegex(ValueError, "two different passphrases"):
            generate(self.root / "b", self.root / "c", PASSPHRASE, PASSPHRASE)
        with self.assertRaisesRegex(ValueError, "16 characters"):
            generate(self.root / "d", self.root / "e", b"short", SPARE)

    def test_a_write_that_fails_leaves_neither_folder_looking_complete(self):
        """A full disk or a removed drive part way through leaves both folders empty, so generate can run again;
        a signing folder whose identity names a spare that was never written would look ready to commit."""
        opened = Path.open
        for name in sorted(SIGNING_FILES | {SPARE_FILE}):
            with self.subTest(failing=name):
                signing, spare = self.root / f"signing-{name}", self.root / f"spare-{name}"

                def failing(path, mode="r", *arguments, failing=name, **options):
                    if path.name == failing and "w" in mode:
                        raise OSError(28, "No space left on device")
                    return opened(path, mode, *arguments, **options)

                with mock.patch.object(Path, "open", failing), self.assertRaises(OSError):
                    generate(signing, spare, PASSPHRASE, SPARE)
                self.assertEqual(([], []), (files(signing), files(spare)))
                generate(signing, spare, PASSPHRASE, SPARE)
                self.assertEqual((sorted(SIGNING_FILES), [SPARE_FILE]), (files(signing), files(spare)))

    def test_check_accepts_only_the_material_the_committed_identity_names(self):
        self.assertEqual(64, len(check(self.pfx, self.key, PASSPHRASE, self.identity, self.public)))
        other = generate(self.root / "other-signing", self.root / "other-spare", PASSPHRASE, SPARE)
        with self.assertRaisesRegex(ValueError, "not the one the committed identity names"):
            check(self.pfx, self.key, PASSPHRASE, other, self.public)
        with self.assertRaisesRegex(ValueError, "does not open"):
            check(self.pfx, self.key, b"not the passphrase", self.identity, self.public)
        with self.assertRaisesRegex(ValueError, "not the RoleBand.cer"):
            check(self.pfx, self.key, PASSPHRASE, self.identity,
                  (self.root / "other-signing" / "RoleBand.cer").read_bytes())

    def test_the_signing_file_must_hold_the_certificate_with_its_own_private_key(self):
        stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        for label, pfx in (("another key beside the certificate", sealed(stranger, None, [self.cert])),
                           ("the certificate alone", sealed(None, None, [self.cert]))):
            with self.subTest(label):
                with self.assertRaisesRegex(ValueError, "holds no certificate with its private key"):
                    check(pfx, self.key, PASSPHRASE, self.identity, self.public)

    def test_a_certificate_with_another_subject_is_refused(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RoleBand")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now)
                .not_valid_after(now + datetime.timedelta(days=3650)).sign(key, hashes.SHA256()))
        with self.assertRaisesRegex(ValueError, "not RoleBand's publisher"):
            check(sealed(key, cert), self.key, PASSPHRASE, self.identity,
                  cert.public_bytes(serialization.Encoding.DER))

    def test_a_certificate_that_expires_within_a_year_is_refused(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        issued = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=round(365.25 * YEARS))
                  + datetime.timedelta(days=180))
        cert = certificate(key, issued)
        with self.assertRaisesRegex(ValueError, "expires within a year"):
            check(sealed(key, cert), self.key, PASSPHRASE, self.identity,
                  cert.public_bytes(serialization.Encoding.DER))

    def test_check_from_the_command_line_needs_the_certificate_people_trust(self):
        arguments = ["check", "--signing", str(self.signing), "--identity", str(self.signing / "release-identity.json"),
                     "--passphrase-env", "ROLEBAND_TEST_SIGNING_PASSPHRASE"]
        with mock.patch.dict(os.environ, {"ROLEBAND_TEST_SIGNING_PASSPHRASE": PASSPHRASE.decode()}):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as refused:
                main(arguments)
            self.assertEqual(2, refused.exception.code)
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                main([*arguments, "--certificate", str(self.signing / "RoleBand.cer")])
        self.assertRegex(printed.getvalue().strip(), "^[0-9a-f]{64}$")

    @unittest.skipUnless(sys.platform == "win32", "Windows renders the subject")
    def test_windows_renders_the_subject_as_the_package_publisher(self):
        shell = shutil.which("pwsh") or "powershell"
        rendered = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-Command",
             f"(New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 '{self.signing / 'RoleBand.cer'}').Subject"],
            check=True, capture_output=True, text=True).stdout.strip()
        self.assertEqual(PUBLISHER, rendered, "MSIX accepts a package only when its publisher is this string")

    @unittest.skipUnless(sys.platform == "win32", "Windows opens the signing file as signtool does")
    def test_windows_opens_the_signing_file_with_its_private_key(self):
        shell = shutil.which("pwsh") or "powershell"
        opened = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-Command",
             "$c = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2("
             "$env:ROLEBAND_TEST_PFX, $env:ROLEBAND_TEST_PASSPHRASE, "
             "[System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::EphemeralKeySet); "
             "$c.HasPrivateKey; $c.Subject"],
            env={**os.environ, "ROLEBAND_TEST_PFX": str(self.signing / "RoleBand-signing.pfx"),
                 "ROLEBAND_TEST_PASSPHRASE": PASSPHRASE.decode()},
            check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(["True", PUBLISHER], opened, "signtool signs only with a certificate that has its key")


class PassphraseTests(unittest.TestCase):
    def test_a_passphrase_named_by_an_environment_variable_must_be_there(self):
        with mock.patch.dict(os.environ, {"ROLEBAND_TEST_PASSPHRASE": "a passphrase"}):
            self.assertEqual(b"a passphrase", passphrase("ROLEBAND_TEST_PASSPHRASE", "unused: "))
        for value in (None, ""):
            with self.subTest(value=value), mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("ROLEBAND_TEST_PASSPHRASE", None)
                if value is not None:
                    os.environ["ROLEBAND_TEST_PASSPHRASE"] = value
                with self.assertRaisesRegex(ValueError, "ROLEBAND_TEST_PASSPHRASE holds no passphrase"):
                    passphrase("ROLEBAND_TEST_PASSPHRASE", "unused: ")

    def test_without_a_variable_the_passphrase_is_typed(self):
        with mock.patch("getpass.getpass", return_value="typed passphrase") as typed:
            self.assertEqual(b"typed passphrase", passphrase(None, "Signing passphrase: "))
        typed.assert_called_once_with("Signing passphrase: ")


if __name__ == "__main__":
    unittest.main()
