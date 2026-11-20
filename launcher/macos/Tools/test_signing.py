import base64
import contextlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

try:
    import signing
except ImportError:
    signing = None


def leaf(keys):
    return signing.load_certificate(keys)


def codesign(certificate):
    def run(command, **kwargs):
        for argument in command:
            if argument.startswith('--extract-certificates='):
                Path(argument.split('=', 1)[1] + '0').write_bytes(certificate.public_bytes(serialization.Encoding.DER))
        return subprocess.CompletedProcess(command, 0)
    return run


PASSPHRASE, CERTIFICATE_PASSWORD = b'release passphrase', b'certificate password'


def protected(keys, name='RoleBand'):
    """A release identity as the maintainer makes it: the spare apart, every key behind a password."""
    signing.generate(keys, name, spare_directory=keys.with_name(keys.name + '-spare'),
                     passphrase=PASSPHRASE, certificate_password=CERTIFICATE_PASSWORD)


IMPORT_STEPS = ['create-keychain', 'set-keychain-settings', 'unlock-keychain', 'import', 'import',
                'set-key-partition-list']


def exported_identity(folder, key=None, authorities=1):
    """A signing.p12 as another tool exports one: an EC key by default, the signing certificate,
    and one certificate per authority in the chain, the first listed twice."""
    def certificate(name, signer, *, authority):
        now = datetime.now(UTC)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(signer.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=authority, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=not authority, content_commitment=False,
                key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=authority,
                crl_sign=authority, encipher_only=None, decipher_only=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(signer.public_key()), critical=False))
        if not authority:
            builder = builder.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]), critical=True)
        return builder.sign(signer, None if isinstance(signer, ed25519.Ed25519PrivateKey) else hashes.SHA256())
    key = key or ec.generate_private_key(ec.SECP256R1())
    chain = [certificate(f'RoleBand Trial Authority {number}', ec.generate_private_key(ec.SECP256R1()), authority=True)
             for number in range(authorities)]
    folder.mkdir(mode=0o700)
    signing.write_private(folder / 'signing.p12', pkcs12.serialize_key_and_certificates(
        b'RoleBand Trial Signer', key, certificate('RoleBand Trial Signer', key, authority=False),
        [*chain, chain[0]], serialization.BestAvailableEncryption(CERTIFICATE_PASSWORD)))


def received(keywords):
    """What a step's stdin holds as the step starts: every byte, or None when a writer is still open
    or the bytes are only written once it runs."""
    stdin = keywords.get('stdin')
    if 'input' in keywords or not isinstance(stdin, int):
        return None
    os.set_blocking(stdin, False)
    chunks = []
    try:
        while chunk := os.read(stdin, 65536):
            chunks.append(chunk)
    except BlockingIOError:
        return None
    return b''.join(chunks)


class SigningTests(unittest.TestCase):
    def test_local_sealing_copies_the_candidate_preserves_its_source_and_embeds_the_trusted_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            keys = root / 'keys'
            protected(keys, 'Local trial')
            (root / 'launcher/macos').mkdir(parents=True)
            (root / 'launcher/macos/release-identity.json').write_text('{"certificate_sha256": null, "release_public_key": null}')
            signing.record(keys, root)
            candidate = root / 'candidate/RoleBand.app'
            (candidate / 'Contents/Resources/engine').mkdir(parents=True)
            engine = candidate / 'Contents/Resources/engine/packaged.py'
            engine.write_text('immutable engine')
            # Code signatures ignore modes, so sealing must not carry these into a release.
            engine.chmod(0o666)
            helper = candidate / 'Contents/Resources/engine/helper'
            helper.write_text('setuid tool')
            helper.chmod(0o4755)
            (candidate / 'Contents/Resources').chmod(0o777)
            info_path = candidate / 'Contents/Info.plist'
            info_path.write_bytes(plistlib.dumps({'RoleBandReleaseCandidate': True,
                'RoleBandPackagedEngine': True, 'RoleBandSourceRevision': 'a' * 40,
                'RoleBandSourceDirty': False, 'RoleBandVersion': '1.2.3'}))
            original = info_path.read_bytes()
            target = root / 'signed/RoleBand.app'
            with patch.object(signing.subprocess, 'run', side_effect=codesign(leaf(keys))) as command, \
                    patch('bundle.sign_tree') as seal:
                signing.seal(candidate, target, (keys / 'identity').read_text(), None, keys / 'release-public.pem', root)
            self.assertIn(['codesign', '--verify', '--deep', '--strict', str(candidate)], [c.args[0] for c in command.call_args_list])
            self.assertEqual(seal.call_count, 1)
            self.assertEqual(seal.call_args.args[1:], ((keys / 'identity').read_text(), None))
            self.assertEqual(info_path.read_bytes(), original)
            info = plistlib.loads((target / 'Contents/Info.plist').read_bytes())
            self.assertNotIn('RoleBandReleaseCandidate', info)
            self.assertEqual(info['RoleBandUpdateRequirement'], f'certificate leaf = H"{(keys / "identity").read_text()}"')
            for path, mode in [('Contents/Resources/engine/packaged.py', 0o644), ('Contents/Resources/engine/helper', 0o755),
                               ('Contents/Resources', 0o755)]:
                self.assertEqual((target / path).stat().st_mode & 0o7777, mode, path)
            self.assertEqual(info['RoleBandUpdateFeed'], 'roleband/roleband')
            self.assertEqual(info['RoleBandSourceRevision'], 'a' * 40)
            public = serialization.load_pem_public_key((keys / 'release-public.pem').read_bytes())
            self.assertEqual(info['RoleBandUpdatePublicKey'], base64.b64encode(public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode())
            self.assertEqual((target / 'Contents/Resources/engine/packaged.py').read_bytes(), engine.read_bytes())
            with self.assertRaises(FileExistsError):
                signing.seal(candidate, target, (keys / 'identity').read_text(), None, keys / 'release-public.pem', root)
            info = plistlib.loads(original)
            info['RoleBandSourceDirty'] = True
            info_path.write_bytes(plistlib.dumps(info))
            with self.assertRaises(ValueError):
                signing.seal(candidate, root / 'bad.app', (keys / 'identity').read_text(), None, keys / 'release-public.pem', root)
            self.assertFalse((root / 'bad.app').exists())
            info_path.write_bytes(original)
            other = root / 'other'
            signing.generate(other, 'Another self-made identity')
            with self.assertRaises(ValueError):
                signing.seal(candidate, root / 'foreign.app', (other / 'identity').read_text(), None, other / 'release-public.pem', root)
            self.assertFalse((root / 'foreign.app').exists())

    def test_a_seal_stamps_the_one_update_feed_and_no_tool_offers_a_feed_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            keys = root / 'keys'
            protected(keys)
            (root / 'launcher/macos').mkdir(parents=True)
            (root / 'launcher/macos/release-identity.json').write_text('{"certificate_sha256": null, "release_public_key": null}')
            signing.record(keys, root)
            candidate = root / 'candidate/RoleBand.app'
            (candidate / 'Contents').mkdir(parents=True)
            (candidate / 'Contents/Info.plist').write_bytes(plistlib.dumps({'RoleBandReleaseCandidate': True,
                'RoleBandPackagedEngine': True, 'RoleBandSourceRevision': 'a' * 40,
                'RoleBandSourceDirty': False, 'RoleBandVersion': '1.2.3'}))
            arguments = (candidate, root / 'RoleBand.app', (keys / 'identity').read_text(), None, keys / 'release-public.pem', root)
            with patch.object(signing.subprocess, 'run', side_effect=codesign(leaf(keys))), patch('bundle.sign_tree'):
                with self.assertRaises(TypeError):
                    signing.seal(*arguments, feed='trial')
                with self.assertRaises(TypeError):
                    signing.record(keys, root, replace=True, feed='trial')
                self.assertFalse((root / 'RoleBand.app').exists())
                signing.seal(*arguments)
            info = plistlib.loads((root / 'RoleBand.app/Contents/Info.plist').read_bytes())
            recorded = json.loads((root / 'launcher/macos/release-identity.json').read_text())
            self.assertEqual(info['RoleBandUpdateFeed'], 'roleband/roleband')
            self.assertEqual(info['RoleBandUpdatePublicKey'], recorded['release_public_key'])
            self.assertEqual(info['RoleBandUpdateSpareKey'], recorded['spare_release_public_key'])
            # The command line takes no feed, and makes no identity without passphrases and a separate spare.
            script = Path(signing.__file__)
            for command in (['seal', str(candidate), str(root / 'trial.app'), '--identity', 'AB',
                             '--release-public-key', str(keys / 'release-public.pem'), '--feed', 'trial'],
                            ['record', str(keys), '--feed', 'trial'],
                            ['generate', str(root / 'unprotected'), '--name', 'RoleBand', '--unprotected']):
                with self.subTest(command[0]):
                    result = subprocess.run([sys.executable, str(script), *command], capture_output=True, text=True,
                                            stdin=subprocess.DEVNULL, check=False)
                    self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse((root / 'trial.app').exists() or (root / 'unprotected').exists())

    def test_sealing_refuses_a_second_identity_even_with_the_recorded_update_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            keys, other = root / 'keys', root / 'other'
            protected(keys)
            signing.generate(other, 'RoleBand')
            (root / 'launcher/macos').mkdir(parents=True)
            (root / 'launcher/macos/release-identity.json').write_text('{"certificate_sha256": null, "release_public_key": null}')
            signing.record(keys, root)
            candidate = root / 'candidate/RoleBand.app'
            (candidate / 'Contents').mkdir(parents=True)
            (candidate / 'Contents/Info.plist').write_bytes(plistlib.dumps({'RoleBandReleaseCandidate': True,
                'RoleBandPackagedEngine': True, 'RoleBandSourceRevision': 'a' * 40,
                'RoleBandSourceDirty': False, 'RoleBandVersion': '1.2.3'}))
            signed = root / 'signed'
            for name, identity, certificate in [('another certificate', other, leaf(other)),
                                                ('the recorded identity, another certificate', keys, leaf(other))]:
                with self.subTest(name), patch.object(signing.subprocess, 'run', side_effect=codesign(certificate)), \
                        patch('bundle.sign_tree') as sign:
                    with self.assertRaisesRegex(ValueError, 'recorded release certificate'):
                        signing.seal(candidate, signed / 'RoleBand.app', (identity / 'identity').read_text(), None,
                                     keys / 'release-public.pem', root)
                    self.assertEqual(sign.call_count, 1)
                    self.assertEqual(list(signed.iterdir()), [])
            with patch.object(signing.subprocess, 'run', side_effect=codesign(leaf(keys))), patch('bundle.sign_tree'):
                signing.seal(candidate, signed / 'RoleBand.app', (keys / 'identity').read_text(), None,
                             keys / 'release-public.pem', root)
            self.assertEqual([path.name for path in signed.iterdir()], ['RoleBand.app'])

    def test_the_release_identity_is_recorded_once_from_public_parts_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'launcher/macos').mkdir(parents=True)
            identity = root / 'launcher/macos/release-identity.json'
            identity.write_text('{"certificate_sha256": null, "release_public_key": null}')
            keys, other = root / 'keys', root / 'other'
            protected(keys)
            protected(other, 'Another self-made identity')
            signing.record(keys, root)
            recorded = identity.read_text()
            certificate = signing.load_certificate(keys)
            def raw(name):
                key = serialization.load_pem_public_key((keys / name).read_bytes())
                return base64.b64encode(key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
            self.assertEqual(json.loads(recorded), {'format': 1,
                'certificate_sha256': certificate.fingerprint(hashes.SHA256()).hex(),
                'release_public_key': raw('release-public.pem'),
                'spare_release_public_key': raw('release-spare-public.pem')})
            for secret in (PASSPHRASE, CERTIFICATE_PASSWORD):
                self.assertNotIn(secret.decode(), recorded)
            self.assertNotIn('PRIVATE', recorded)
            with self.assertRaises(ValueError):
                signing.record(other, root)
            self.assertEqual(identity.read_text(), recorded)
            signing.record(other, root, replace=True)
            self.assertNotEqual(identity.read_text(), recorded)
            # A key change keeps the signing rule that installed apps already hold.
            rule = 'certificate leaf = H"AB" or (anchor apple generic and certificate leaf[subject.OU] = "ABCDE12345")'
            identity.write_text(json.dumps({**json.loads(identity.read_text()), 'update_requirement': rule}))
            signing.record(keys, root, replace=True)
            self.assertEqual(json.loads(identity.read_text())['update_requirement'], rule)
            self.assertEqual(json.loads(identity.read_text())['release_public_key'], raw('release-public.pem'))

    def test_a_production_identity_needs_its_own_spare_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'launcher/macos').mkdir(parents=True)
            identity = root / 'launcher/macos/release-identity.json'
            identity.write_text('{"certificate_sha256": null, "release_public_key": null}')
            keys = root / 'keys'
            protected(keys)
            spare = (keys / 'release-spare-public.pem').read_bytes()
            (keys / 'release-spare-public.pem').unlink()
            with self.assertRaises(ValueError):
                signing.record(keys, root)
            (keys / 'release-spare-public.pem').write_bytes((keys / 'release-public.pem').read_bytes())
            with self.assertRaises(ValueError):
                signing.record(keys, root)
            self.assertIsNone(json.loads(identity.read_text())['release_public_key'])
            (keys / 'release-spare-public.pem').write_bytes(spare)
            signing.record(keys, root)
            self.assertEqual(json.loads(identity.read_text())['spare_release_public_key'], base64.b64encode(
                serialization.load_pem_public_key(spare).public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode())

    def test_a_copy_of_the_release_identity_folder_unlocks_nothing_and_unprotected_keys_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'launcher/macos').mkdir(parents=True)
            identity = root / 'launcher/macos/release-identity.json'
            identity.write_text('{"certificate_sha256": null, "release_public_key": null}')
            keys, spare = root / 'keys', root / 'keys-spare'
            protected(keys)
            self.assertEqual(sorted(path.name for path in spare.iterdir()), ['release-spare-private.pem', 'release-spare-public.pem'])
            self.assertFalse((keys / 'release-spare-private.pem').exists())
            for name in ('p12-password', 'keychain-password'):
                self.assertFalse((keys / name).exists())
            for path in (keys / 'release-private.pem', spare / 'release-spare-private.pem'):
                with self.assertRaises(TypeError):
                    serialization.load_pem_private_key(path.read_bytes(), None)
                serialization.load_pem_private_key(path.read_bytes(), PASSPHRASE)
            with self.assertRaises(ValueError):
                pkcs12.load_key_and_certificates((keys / 'signing.p12').read_bytes(), None)
            pkcs12.load_key_and_certificates((keys / 'signing.p12').read_bytes(), CERTIFICATE_PASSWORD)
            with self.assertRaises(ValueError):
                signing.generate(root / 'nested', 'RoleBand', spare_directory=root / 'nested/spare',
                                 passphrase=PASSPHRASE, certificate_password=CERTIFICATE_PASSWORD)
            # Each way a production identity could be left unprotected is refused at recording.
            # Each case differs from a protected identity in one way only.
            for name, options in [('unencrypted keys', {'passphrase': None}),
                                  ('password files beside', {'certificate_password': None}),
                                  ('spare beside', {'spare_directory': None})]:
                folder = root / name.replace(' ', '-')
                signing.generate(folder, 'RoleBand', **{'spare_directory': folder.with_name(folder.name + '-spare'),
                    'passphrase': PASSPHRASE, 'certificate_password': CERTIFICATE_PASSWORD, **options})
                with self.subTest(name), self.assertRaises(ValueError):
                    signing.record(folder, root)
            self.assertIsNone(json.loads(identity.read_text())['release_public_key'])
            signing.record(keys, root)

    def _import(self, keys, keychain, typed=None, fail=None):
        """Run the import with `security` replaced: every call as (argv, stdin, keywords), and what it raised."""
        calls = []
        def run(command, **kwargs):
            calls.append((command, received(kwargs), kwargs))
            if fail is not None:
                fail(len(calls) - 1, command)
            return subprocess.CompletedProcess(command, 0)
        raised = None
        before = os.listdir('/dev/fd')
        with patch.object(signing.subprocess, 'run', side_effect=run):
            try:
                signing.import_keychain(keys, keychain, typed)
            except BaseException as error:  # noqa: BLE001 - the test inspects whatever it was
                raised = error
        self.assertEqual(len(os.listdir('/dev/fd')), len(before), 'every pipe is closed')
        return calls, raised

    def test_key_import_puts_no_password_or_key_on_any_command_line(self):
        self.assertIsNotNone(signing)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            signing.generate(folder / 'throwaway', 'RoleBand CI Trial')
            protected(folder / 'production')
            exported_identity(folder / 'elliptic')
            cases = {'throwaway identity': (folder / 'throwaway', None, (folder / 'throwaway/p12-password').read_bytes()),
                     'production identity': (folder / 'production', CERTIFICATE_PASSWORD, CERTIFICATE_PASSWORD),
                     'EC key with a chain': (folder / 'elliptic', CERTIFICATE_PASSWORD, CERTIFICATE_PASSWORD)}
            for name, (keys, typed, certificate_password) in cases.items():
                with self.subTest(name):
                    calls, raised = self._import(keys, folder / f'{keys.name}.keychain-db', typed)
                    self.assertIsNone(raised)
                    arguments = [str(argument) for command, _, _ in calls for argument in command]
                    def assert_hidden(label, secret, arguments=arguments):
                        self.assertFalse(any(secret in argument for argument in arguments),
                                         f'the {label} is on a command line')
                    assert_hidden('certificate password', certificate_password.decode())
                    if (keys / 'keychain-password').exists():
                        assert_hidden('stored keychain password', (keys / 'keychain-password').read_text())
                    assert_hidden('private key', 'PRIVATE KEY')
                    self.assertEqual([command[1] for command, _, _ in calls], IMPORT_STEPS)
                    for command, data, _ in calls:
                        self.assertIsNotNone(data, f'security {command[1]} could start before its input is all there')
                    first, second, rest = calls[0][1].decode().split('\n')
                    self.assertTrue(first and first == second and rest == '', 'the new keychain gets one password, twice')
                    assert_hidden('keychain password', first)
                    if (keys / 'keychain-password').exists():
                        self.assertEqual(first, (keys / 'keychain-password').read_text())
                    for command, data, keywords in calls:
                        if (first + '\n').encode() in data:
                            self.assertTrue(keywords.get('start_new_session'),
                                            f'security {command[1]} would prompt on the terminal instead of reading stdin')
                    key, certificate, chain = pkcs12.load_key_and_certificates(
                        (keys / 'signing.p12').read_bytes(), certificate_password)
                    piped = {command[command.index('-t') + 1]: data for command, data, _ in calls if command[1] == 'import'}
                    self.assertEqual(serialization.load_pem_private_key(piped['priv'], None).private_numbers(),
                                     key.private_numbers())
                    expected = list({item.fingerprint(hashes.SHA256()): item for item in [certificate, *chain]}.values())
                    self.assertEqual(x509.load_pem_x509_certificates(piped['cert']), expected,
                                     'the certificate and its chain, each once')

    def test_a_failure_or_interruption_after_the_keychain_exists_deletes_only_that_keychain(self):
        self.assertIsNotNone(signing)
        with tempfile.TemporaryDirectory() as directory:
            keys, keychain = Path(directory) / 'keys', Path(directory) / 'trial.keychain-db'
            signing.generate(keys, 'RoleBand CI Trial')
            password = (keys / 'p12-password').read_text()
            failures = {'a refusal': subprocess.CalledProcessError(1, ['security']),
                        'a stalled prompt': subprocess.TimeoutExpired(['security'], 120),
                        'a missing tool': FileNotFoundError('security'),
                        'an interruption': KeyboardInterrupt()}
            for step, name in enumerate(IMPORT_STEPS):
                for label, failure in failures.items():
                    def fail(index, command, step=step, failure=failure):
                        if index == step:
                            raise failure
                    with self.subTest(step=name, failure=label):
                        calls, raised = self._import(keys, keychain, fail=fail)
                        argv = [command for command, _, _ in calls]
                        if step == 0:
                            self.assertEqual(len(argv), 1, 'nothing to delete before the keychain exists')
                        else:
                            self.assertEqual(argv[-1], ['security', 'delete-keychain', str(keychain)])
                            self.assertEqual(len(argv), step + 2)
                        if isinstance(failure, KeyboardInterrupt):
                            self.assertIs(raised, failure)
                        else:
                            self.assertIsInstance(raised, RuntimeError)
                            self.assertIn(f'security {name} failed', str(raised))
                            self.assertNotIn(password, str(raised))
                            self.assertIsNone(raised.__cause__)

    def test_a_p12_that_cannot_sign_fails_before_any_keychain_is_made(self):
        self.assertIsNotNone(signing)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            protected(folder / 'keys')
            exported_identity(folder / 'ed25519', ed25519.Ed25519PrivateKey.generate())
            exported_identity(folder / 'long-chain', authorities=200)
            failed = 'Could not import the signing identity into the scratch build keychain'
            cases = {'a mistyped password': (folder / 'keys', b'mistyped password', RuntimeError, failed, None),
                     'an encryption this library cannot read': (folder / 'keys', CERTIFICATE_PASSWORD, RuntimeError,
                                                               failed, UnsupportedAlgorithm('unsupported cipher')),
                     'a key codesign cannot use': (folder / 'ed25519', CERTIFICATE_PASSWORD, ValueError,
                                                   'codesign signs only with an RSA or EC key', None),
                     'a chain larger than a pipe holds': (folder / 'long-chain', CERTIFICATE_PASSWORD, ValueError,
                                                          'The signing identity is larger than a pipe to security holds',
                                                          None)}
            for name, (keys, typed, expected, message, unreadable) in cases.items():
                reading = (patch.object(signing.pkcs12, 'load_key_and_certificates', side_effect=unreadable)
                           if unreadable else contextlib.nullcontext())
                with self.subTest(name), patch.object(signing.subprocess, 'run') as command, reading:
                    before = os.listdir('/dev/fd')
                    with self.assertRaises(expected) as error:
                        signing.import_keychain(keys, folder / 'build.keychain-db', typed)
                    self.assertEqual(len(os.listdir('/dev/fd')), len(before), 'every pipe is closed')
                    command.assert_not_called()
                    self.assertEqual(str(error.exception), message)
                    self.assertNotIn(typed.decode(), str(error.exception))
                    self.assertFalse((folder / 'build.keychain-db').exists())

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('security') and shutil.which('codesign'),
                         'needs the macOS keychain and codesign')
    def test_on_a_mac_the_imported_identity_signs_and_its_keychain_opens_only_with_its_password(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            signing.generate(folder / 'throwaway', 'RoleBand Keychain Trial')
            exported_identity(folder / 'elliptic')
            def security(*arguments, data=b''):
                return subprocess.run(['security', *arguments], input=data, capture_output=True, text=False,
                                      start_new_session=True, timeout=60, check=False)
            for keys, typed in ((folder / 'throwaway', None), (folder / 'elliptic', CERTIFICATE_PASSWORD)):
                keychain = folder / f'{keys.name}.keychain-db'
                with self.subTest(keys.name):
                    try:
                        signing.import_keychain(keys, keychain, typed)
                        certificate = signing.load_certificate(keys) if typed is None else pkcs12.load_key_and_certificates(
                            (keys / 'signing.p12').read_bytes(), typed)[1]
                        identity = certificate.fingerprint(hashes.SHA1()).hex().upper()
                        self.assertIn(identity, security('find-identity', '-p', 'codesigning', str(keychain)).stdout.decode())
                        tool = folder / f'{keys.name}-tool'
                        shutil.copy('/usr/bin/true', tool)
                        subprocess.run(['codesign', '--remove-signature', str(tool)], check=True, timeout=60)
                        # The flags bundle.sign_tree signs with.
                        for command in (['codesign', '--force', '--timestamp=none', '--sign', identity,
                                         '--keychain', str(keychain), str(tool)], ['codesign', '--verify', str(tool)]):
                            done = subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL, timeout=60)
                            self.assertEqual(done.returncode, 0, done.stderr.decode())
                        held = security('find-certificate', '-a', '-Z', str(keychain)).stdout.decode()
                        self.assertEqual(held.count('SHA-1 hash:'), 1 if typed is None else 2, 'each certificate once')
                        if typed is None:
                            password = (keys / 'keychain-password').read_text()
                            self.assertEqual(security('lock-keychain', str(keychain)).returncode, 0)
                            self.assertNotEqual(security('unlock-keychain', str(keychain),
                                                         data=(password[:-1] + '\n').encode()).returncode, 0)
                            self.assertEqual(security('unlock-keychain', str(keychain),
                                                      data=(password + '\n').encode()).returncode, 0)
                    finally:
                        if keychain.exists():
                            security('delete-keychain', str(keychain))
                    self.assertFalse(keychain.exists())

    def test_throwaway_keys_have_code_signing_identity_private_permissions_and_cannot_be_overwritten(self):
        self.assertIsNotNone(signing, 'the signing-material generator is missing')
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'keys'
            signing.generate(target, 'RoleBand CI Trial')
            key, certificate, _ = pkcs12.load_key_and_certificates(
                (target / 'signing.p12').read_bytes(), (target / 'p12-password').read_bytes())
            self.assertIsNotNone(key)
            self.assertEqual(certificate.subject, certificate.issuer)
            self.assertIn(ExtendedKeyUsageOID.CODE_SIGNING, certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value)
            self.assertEqual(certificate.fingerprint(hashes.SHA1()).hex().upper(), (target / 'identity').read_text())
            private = serialization.load_pem_private_key((target / 'release-private.pem').read_bytes(), None)
            public = serialization.load_pem_public_key((target / 'release-public.pem').read_bytes())
            public.verify(private.sign(b'checksum'), b'checksum')
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            spare = serialization.load_pem_private_key((target / 'release-spare-private.pem').read_bytes(), None)
            serialization.load_pem_public_key((target / 'release-spare-public.pem').read_bytes()).verify(
                spare.sign(b'checksum'), b'checksum')
            self.assertNotEqual(spare.private_bytes_raw(), private.private_bytes_raw())
            for name in ('signing.p12', 'p12-password', 'release-private.pem', 'release-spare-private.pem', 'keychain-password'):
                self.assertEqual((target / name).stat().st_mode & 0o777, 0o600)
            original = (target / 'signing.p12').read_bytes()
            with self.assertRaises(FileExistsError):
                signing.generate(target, 'another identity')
            self.assertEqual((target / 'signing.p12').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
