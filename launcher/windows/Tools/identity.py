"""RoleBand's Windows release identity: its own code-signing certificate, the release key and its offline spare.

`generate` writes, once, into two new folders:

- the signing folder, whose files become the protected GitHub environment's secrets: `RoleBand-signing.pfx` (the
  certificate and its private key, encrypted), `release-key.pem` (encrypted), and the public files
  `RoleBand.cer`, which a person trusts once before the first install, and `release-identity.json`, committed
  as `launcher/windows/release-identity.json`;
- the spare folder, kept offline and never beside the signing folder: `spare-release-key.pem` (encrypted).

`check` confirms that a certificate and key match the committed identity before anything is signed with them.
"""

import argparse
import base64
import datetime
import getpass
import hashlib
import json
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

FEED = "roleband/roleband"
PACKAGE_NAME = "RoleBand.RoleBand"
#: The package's publisher, as Windows renders the certificate subject; it never changes, and a new certificate keeps it.
PUBLISHER = "CN=RoleBand, O=RoleBand, DC=roleband, DC=com"
#: Windows renders a subject in reverse of its encoded order, so the domain is encoded first.
SUBJECT = x509.Name([
    x509.NameAttribute(NameOID.DOMAIN_COMPONENT, "com"),
    x509.NameAttribute(NameOID.DOMAIN_COMPONENT, "roleband"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "RoleBand"),
    x509.NameAttribute(NameOID.COMMON_NAME, "RoleBand"),
])
#: Signatures are not timestamped, so a package verifies only while the certificate is valid.
YEARS = 25
SIGNING_FILES = ("RoleBand-signing.pfx", "RoleBand.cer", "release-key.pem", "release-identity.json")
SPARE_FILE = "spare-release-key.pem"


def certificate(key: rsa.RSAPrivateKey, now: datetime.datetime) -> x509.Certificate:
    """A self-signed certificate that can sign code and nothing else, and cannot issue others."""
    return (x509.CertificateBuilder()
            .subject_name(SUBJECT).issuer_name(SUBJECT)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=round(365.25 * YEARS)))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))


def _raw(key: ed25519.Ed25519PrivateKey) -> str:
    return base64.b64encode(key.public_key().public_bytes_raw()).decode()


def _sealed(key: ed25519.Ed25519PrivateKey, passphrase: bytes) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.BestAvailableEncryption(passphrase))


def generate(signing: Path, spare: Path, passphrase: bytes, spare_passphrase: bytes,
             now: datetime.datetime | None = None, feed: str = FEED) -> dict:
    """Write a new identity; refuses to touch existing files or to put the spare beside the signing material."""
    signing, spare = signing.resolve(), spare.resolve()
    if signing == spare or signing.is_relative_to(spare) or spare.is_relative_to(signing):
        raise ValueError("Keep the spare folder apart from the signing folder")
    if passphrase == spare_passphrase or len(passphrase) < 16 or len(spare_passphrase) < 16:
        raise ValueError("Use two different passphrases of 16 characters or more")
    for folder in (signing, spare):
        if folder.exists() and any(folder.iterdir()):
            raise ValueError(f"Choose a new, empty folder: {folder}")
    now = now or datetime.datetime.now(datetime.timezone.utc)
    certificate_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    cert = certificate(certificate_key, now)
    release, spare_key = ed25519.Ed25519PrivateKey.generate(), ed25519.Ed25519PrivateKey.generate()
    identity = {"format": 1, "feed": feed, "release_public_key": _raw(release), "package_name": PACKAGE_NAME,
                "publisher": PUBLISHER, "spare_release_public_key": _raw(spare_key)}
    signing.mkdir(parents=True, exist_ok=True)
    spare.mkdir(parents=True, exist_ok=True)
    (signing / "RoleBand-signing.pfx").write_bytes(pkcs12.serialize_key_and_certificates(
        b"RoleBand", certificate_key, cert, None, serialization.BestAvailableEncryption(passphrase)))
    (signing / "RoleBand.cer").write_bytes(cert.public_bytes(serialization.Encoding.DER))
    (signing / "release-key.pem").write_bytes(_sealed(release, passphrase))
    (signing / "release-identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    (spare / SPARE_FILE).write_bytes(_sealed(spare_key, spare_passphrase))
    return identity


def check(pfx: bytes, release_key: bytes, passphrase: bytes, identity: dict, public: bytes | None = None) -> str:
    """The certificate's SHA-256, once the certificate and the release key are the ones the identity names, and the
    certificate is the public one people trust, when given."""
    try:
        _key, cert, _others = pkcs12.load_key_and_certificates(pfx, passphrase)
        release = serialization.load_pem_private_key(release_key, passphrase)
    except ValueError as error:
        raise ValueError("The signing material does not open with this passphrase") from error
    if cert is None or cert.subject != SUBJECT or identity.get("publisher") != PUBLISHER:
        raise ValueError("The certificate is not RoleBand's publisher")
    if public is not None and cert.public_bytes(serialization.Encoding.DER) != public:
        raise ValueError("The certificate is not the RoleBand.cer people trust")
    if not isinstance(release, ed25519.Ed25519PrivateKey) or _raw(release) != identity.get("release_public_key"):
        raise ValueError("The release key is not the one the committed identity names")
    if cert.not_valid_after_utc < datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365):
        raise ValueError("The certificate expires within a year: issue a new one with the same subject")
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def _ask(prompt: str) -> bytes:
    first = getpass.getpass(prompt)
    if first != getpass.getpass("Again: "):
        raise ValueError("The passphrases differ")
    return first.encode()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="action", required=True)
    make = commands.add_parser("generate")
    make.add_argument("--signing", type=Path, required=True)
    make.add_argument("--spare", type=Path, required=True)
    make.add_argument("--feed", default=FEED, help="another feed, only for a rehearsal of the release")
    verify = commands.add_parser("check")
    verify.add_argument("--signing", type=Path, required=True,
                        help="a folder holding RoleBand-signing.pfx and release-key.pem")
    verify.add_argument("--identity", type=Path, required=True)
    verify.add_argument("--certificate", type=Path, help="the public RoleBand.cer committed beside the identity")
    verify.add_argument("--passphrase-env", help="read the passphrase from this environment variable")
    args = parser.parse_args(argv)
    try:
        if args.action == "generate":
            record = generate(args.signing, args.spare, _ask("Signing passphrase: "), _ask("Spare passphrase: "),
                              feed=args.feed)
            print(json.dumps(record, indent=2))
        else:
            import os

            passphrase = (os.environ[args.passphrase_env] if args.passphrase_env
                          else getpass.getpass("Signing passphrase: ")).encode()
            print(check((args.signing / "RoleBand-signing.pfx").read_bytes(),
                        (args.signing / "release-key.pem").read_bytes(), passphrase,
                        json.loads(args.identity.read_text(encoding="utf-8")),
                        args.certificate.read_bytes() if args.certificate else None))
    except (OSError, KeyError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    sys.exit(main())
