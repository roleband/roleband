"""Create signing material or import it into an isolated build keychain."""

import argparse
import base64
import contextlib
import getpass
import json
import os
import plistlib
import secrets
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[3]


def write_private(path, data):
    with path.open('xb') as output:
        path.chmod(0o600)
        output.write(data)


def generate(directory, name, *, spare_directory=None, passphrase=None, certificate_password=None):
    """Make a certificate and two release keys.

    The release identity passes all three secrets: the spare's private key goes to its own folder,
    the release keys are encrypted with `passphrase`, and the p12 with `certificate_password`, so no
    file here unlocks another. Without them (a throwaway identity for tests) the keys are unencrypted,
    their passwords sit beside them and the spare stays in `directory`, and `record` refuses them.
    """
    spare_directory = spare_directory or directory
    if spare_directory != directory and (spare_directory.resolve().is_relative_to(directory.resolve())
                                         or directory.resolve().is_relative_to(spare_directory.resolve())):
        raise ValueError('The spare key folder must be separate from the identity folder')
    directory.mkdir(mode=0o700, parents=True)
    if spare_directory != directory:
        spare_directory.mkdir(mode=0o700, parents=True)
    password = certificate_password or secrets.token_urlsafe(32).encode()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(UTC)
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
            encipher_only=None, decipher_only=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256()))
    encryption = (serialization.PrivateFormat.PKCS12.encryption_builder().kdf_rounds(50000)
        .key_cert_algorithm(pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC).hmac_hash(hashes.SHA1()).build(password))
    write_private(directory / 'signing.p12', pkcs12.serialize_key_and_certificates(
        name.encode(), key, certificate, None, encryption))
    (directory / 'certificate.pem').write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    if certificate_password is None:
        write_private(directory / 'p12-password', password)
        write_private(directory / 'keychain-password', secrets.token_urlsafe(32).encode())
    protection = serialization.BestAvailableEncryption(passphrase) if passphrase else serialization.NoEncryption()
    # The spare release key ships in every app beside the current one, so a lost or leaked key
    # can be replaced by an update.
    for prefix, private_folder in (('release', directory), ('release-spare', spare_directory)):
        release = ed25519.Ed25519PrivateKey.generate()
        write_private(private_folder / f'{prefix}-private.pem', release.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, protection))
        public = release.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        for folder in {directory, private_folder}:
            (folder / f'{prefix}-public.pem').write_bytes(public)
    (directory / 'identity').write_text(certificate.fingerprint(hashes.SHA1()).hex().upper())


def encrypted(path):
    try:
        serialization.load_pem_private_key(path.read_bytes(), None)
    except TypeError:
        return True
    return False


def load_certificate(directory):
    if (directory / 'certificate.pem').exists():
        return x509.load_pem_x509_certificate((directory / 'certificate.pem').read_bytes())
    return pkcs12.load_key_and_certificates(
        (directory / 'signing.p12').read_bytes(), (directory / 'p12-password').read_bytes())[1]


def record(directory, root=ROOT, *, replace=False):
    from release import FEED, identity_path

    path = identity_path(FEED, root)
    current = json.loads(path.read_text())
    if not replace and (current.get('certificate_sha256') or current.get('release_public_key')):
        raise ValueError('A release identity is already recorded; changing it breaks updates for installed apps')
    # A copy of this folder must not be enough to sign a release, or to make another.
    if (directory / 'release-spare-private.pem').exists():
        raise ValueError("The spare release key's private half must live apart from the identity")
    if (directory / 'p12-password').exists() or (directory / 'keychain-password').exists():
        raise ValueError('The production identity keeps no password files beside its keys')
    if not encrypted(directory / 'release-private.pem'):
        raise ValueError('The production release key must be passphrase-protected')
    certificate = load_certificate(directory)
    public = serialization.load_pem_public_key((directory / 'release-public.pem').read_bytes())
    if certificate is None or not isinstance(public, ed25519.Ed25519PublicKey):
        raise ValueError('Expected a signing certificate and an Ed25519 release key')
    pin = {'format': 1, 'certificate_sha256': certificate.fingerprint(hashes.SHA256()).hex(),
        'release_public_key': base64.b64encode(public.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode('ascii')}
    spare_path = directory / 'release-spare-public.pem'
    if spare_path.exists():
        spare = serialization.load_pem_public_key(spare_path.read_bytes())
        if not isinstance(spare, ed25519.Ed25519PublicKey):
            raise ValueError('The spare release key must use Ed25519')
        pin['spare_release_public_key'] = base64.b64encode(spare.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode('ascii')
        if pin['spare_release_public_key'] == pin['release_public_key']:
            raise ValueError('The spare release key must differ from the current one')
    else:
        raise ValueError('The production identity needs a spare release key')
    if 'update_requirement' in current:
        pin['update_requirement'] = current['update_requirement']
    path.write_text(json.dumps(pin, indent=2) + '\n')
    return path


@contextlib.contextmanager
def _filled(data):
    """A pipe that already holds all of `data` and has no writer left, for a program to read as stdin.

    `security import` reads as many bytes as its stdin holds when it opens it, so bytes written
    after it starts can be missed. A pipe filled and closed before the program starts reads the
    same every time.
    """
    read, write = os.pipe()
    try:
        try:
            os.set_blocking(write, False)
            written = os.write(write, data)
        except BlockingIOError:
            written = 0
        finally:
            os.close(write)
        if written < len(data):
            raise ValueError('The signing identity is larger than a pipe to security holds')
        yield read
    finally:
        os.close(read)


def import_keychain(directory, keychain, certificate_password=None):
    """Import the signing identity into a new scratch keychain that codesign may use.

    No password and no key goes on a command line, where every local user can list it. The p12
    opens here, the key and certificates reach `security` on stdin, and so does the keychain
    password: with no controlling terminal its prompts fall back to stdin. Each step's stdin is a
    pipe filled before the step starts. Everything that can fail on the p12 or its size fails
    before the keychain exists, and a failure or an interruption after that deletes the keychain,
    so a retry starts from nothing.
    """
    if keychain.exists():
        raise FileExistsError('The build keychain already exists')
    if certificate_password is None:
        certificate_password = (directory / 'p12-password').read_bytes()
    failure = 'Could not import the signing identity into the scratch build keychain'
    try:
        key, certificate, chain = pkcs12.load_key_and_certificates(
            (directory / 'signing.p12').read_bytes(), certificate_password)
    except (ValueError, UnsupportedAlgorithm):
        raise RuntimeError(failure) from None
    if key is None or certificate is None:
        raise RuntimeError(failure)
    if not isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)):
        raise ValueError('codesign signs only with an RSA or EC key')
    stored = directory / 'keychain-password'
    # A release keychain is scratch: made, used and deleted while the keys are mounted.
    password = stored.read_text() if stored.exists() else secrets.token_urlsafe(32)
    if not password or '\n' in password:
        raise ValueError('The keychain password must be one non-empty line')
    line = (password + '\n').encode()
    # `security` reads a key from a pipe only in the traditional OpenSSL format, not PKCS#8.
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                serialization.NoEncryption())
    # A certificate imported twice fails the whole import, so each goes in once.
    unique = {item.fingerprint(hashes.SHA256()): item for item in [certificate, *chain]}
    certificates = b''.join(item.public_bytes(serialization.Encoding.PEM) for item in unique.values())
    steps = [
        (['security', 'create-keychain', str(keychain)], line * 2),
        (['security', 'set-keychain-settings', '-lut', '21600', str(keychain)], b''),
        (['security', 'unlock-keychain', str(keychain)], line),
        (['security', 'import', '/dev/stdin', '-k', str(keychain), '-f', 'openssl', '-t', 'priv',
          '-T', '/usr/bin/codesign'], private),
        (['security', 'import', '/dev/stdin', '-k', str(keychain), '-f', 'pemseq', '-t', 'cert'], certificates),
        (['security', 'set-key-partition-list', '-S', 'apple-tool:,apple:', '-s', str(keychain)], line),
    ]
    created = False
    with contextlib.ExitStack() as pipes:
        filled = [(command, pipes.enter_context(_filled(data))) for command, data in steps]
        try:
            for command, stdin in filled:
                try:
                    # A new session has no terminal, so a password prompt reads the line given here.
                    subprocess.run(command, stdin=stdin, check=True, start_new_session=True, timeout=120,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                except (OSError, subprocess.SubprocessError):
                    raise RuntimeError(f'{failure}: security {command[1]} failed') from None
                created = True
        except BaseException:
            if created or keychain.exists():
                subprocess.run(['security', 'delete-keychain', str(keychain)], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            raise


def seal(candidate, destination, identity, keychain, public_key, root=ROOT):
    from bundle import sign_tree
    from release import (
        FEED,
        check_modes,
        check_signing_certificate,
        release_identity,
        release_spare_key,
        signing_rule,
    )

    if destination.exists():
        raise FileExistsError('The signed app destination already exists')
    info = plistlib.loads((candidate / 'Contents/Info.plist').read_bytes())
    if (not info.get('RoleBandReleaseCandidate') or not info.get('RoleBandPackagedEngine')
            or info.get('RoleBandSourceDirty') is not False or identity == '-'):
        raise ValueError('Local sealing requires a clean packaged candidate and a certificate')
    public = serialization.load_pem_public_key(public_key.read_bytes())
    if not isinstance(public, ed25519.Ed25519PublicKey):
        raise ValueError('The release key must use Ed25519')
    trusted_certificate, trusted_key = release_identity(root, FEED)
    if public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw) != trusted_key:
        raise ValueError('The public key is not the recorded release key')
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(candidate)], check=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.seal-', dir=destination.parent) as directory:
        app = Path(directory) / 'RoleBand.app'
        shutil.copytree(candidate, app, symlinks=True)
        for path in [app, *app.rglob('*')]:
            if not path.is_symlink():
                # Signatures do not cover modes: only the owner may write, and nothing runs as another user.
                path.chmod((path.stat().st_mode | 0o200) & ~0o6022)
        info.pop('RoleBandReleaseCandidate')
        info['RoleBandSigningIdentity'] = identity
        info['RoleBandUpdateFeed'] = FEED
        info['RoleBandUpdatePublicKey'] = base64.b64encode(public.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode('ascii')
        spare = release_spare_key(root, FEED)
        if spare is not None:
            info['RoleBandUpdateSpareKey'] = base64.b64encode(spare).decode('ascii')
        info['RoleBandUpdateRequirement'] = signing_rule(root, FEED, identity)
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        sign_tree(app, identity, keychain)
        check_signing_certificate(app, identity, trusted_certificate)
        check_modes(app)
        app.rename(destination)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('generate')
    create.add_argument('directory', type=Path)
    create.add_argument('--name', required=True)
    create.add_argument('--spare-directory', type=Path, required=True, help='a separate folder for the spare release key')
    pin = commands.add_parser('record')
    pin.add_argument('directory', type=Path)
    pin.add_argument('--replace', action='store_true')
    load = commands.add_parser('import')
    load.add_argument('directory', type=Path)
    load.add_argument('keychain', type=Path)
    sign = commands.add_parser('seal')
    sign.add_argument('candidate', type=Path)
    sign.add_argument('destination', type=Path)
    sign.add_argument('--identity', required=True)
    sign.add_argument('--keychain', type=Path)
    sign.add_argument('--release-public-key', type=Path, required=True)
    args = parser.parse_args()
    def secret(prompt):
        first = getpass.getpass(prompt + ': ').encode()
        if not first or first != getpass.getpass(prompt + ' again: ').encode():
            parser.exit(1, 'The two entries were empty or did not match\n')
        return first

    if args.command == 'generate':
        generate(args.directory, args.name, spare_directory=args.spare_directory,
                 passphrase=secret('Release key passphrase'), certificate_password=secret('Certificate password'))
    elif args.command == 'record':
        print(record(args.directory, replace=args.replace))
    elif args.command == 'import':
        import_keychain(args.directory, args.keychain, None if (args.directory / 'p12-password').exists()
                        else getpass.getpass('Certificate password: ').encode())
    else:
        print(seal(args.candidate.resolve(), args.destination.absolute(), args.identity,
                   args.keychain, args.release_public_key))
