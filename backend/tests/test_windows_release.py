"""An installed Windows app accepts an update only as a newer release its owner signed for it."""

from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from tracker.platform.windows_release import (
    Identity,
    ReleaseError,
    manifest,
    names,
    prepare,
    read_identity,
    verify_offer,
    verify_package,
)

COMMIT = "a" * 40
PUBLISHER = "CN=RoleBand Windows Trial"


@pytest.fixture
def key():
    return ed25519.Ed25519PrivateKey.generate()


@pytest.fixture
def identity(key):
    return Identity("roleband/roleband-trials", key.public_key().public_bytes_raw(), "RoleBand.Windows.Trial", PUBLISHER)


@pytest.fixture
def release(tmp_path, key, identity):
    package = tmp_path / "built.msix"
    package.write_bytes(b"PK\x03\x04 synthetic package " * 64)
    return prepare(package, tmp_path / "release", identity, key, version="0.1.3", revision=0, commit=COMMIT)


def _parts(release):
    package, checksum, metadata, signature = release
    return package, checksum.read_bytes(), metadata.read_bytes(), signature.read_bytes()


def _resigned(key, checksum, record):
    metadata = (json.dumps(record, indent=2) + "\n").encode()
    return checksum, metadata, key.sign(checksum + metadata)


def test_a_prepared_release_verifies_and_names_its_package(release, identity):
    package, checksum, metadata, signature = _parts(release)
    assert [path.name for path in release] == list(names("0.1.3"))
    offer = verify_offer(identity, "0.1.2", checksum, metadata, signature)
    assert (offer.version, offer.package_version, offer.package, offer.commit) == (
        "0.1.3", "0.1.3.0", "RoleBand-0.1.3-Windows-x64.msix", COMMIT)
    verify_package(package, offer)


@pytest.mark.parametrize("part", ["checksum", "metadata", "signature"])
def test_any_changed_byte_breaks_the_signature(release, identity, part):
    _package, checksum, metadata, signature = _parts(release)
    values = {"checksum": checksum, "metadata": metadata, "signature": signature}
    changed = bytearray(values[part])
    changed[len(changed) // 2] ^= 1
    values[part] = bytes(changed)
    with pytest.raises(ReleaseError):
        verify_offer(identity, "0.1.2", values["checksum"], values["metadata"], values["signature"])


def test_another_key_is_not_the_owner(release, identity):
    _package, checksum, metadata, _signature = _parts(release)
    stranger = ed25519.Ed25519PrivateKey.generate()
    with pytest.raises(ReleaseError, match="signature"):
        verify_offer(identity, "0.1.2", checksum, metadata, stranger.sign(checksum + metadata))


@pytest.mark.parametrize("field, value", [
    ("platform", "macos"), ("architecture", "arm64"), ("publisher", "CN=Someone Else"),
    ("package_name", "RoleBand.Windows"), ("feed", "roleband/roleband"), ("release_key_sha256", "0" * 64),
    ("minimum_windows_build", 19045), ("format", 2), ("tag", "v9.9.9"),
    ("package", "RoleBand-0.1.3-Windows-arm64.msix"), ("package_version", "0.1.4.0"),
    ("package_version", "0.1.3.07"), ("package_version", "0.1.3.65536"), ("version", "0.1.3-beta.1"),
    ("bytes", 0), ("bytes", True), ("sha256", "A" * 64), ("commit", "abc"),
])
def test_owner_signed_metadata_for_another_release_shape_is_refused(release, identity, key, field, value):
    _package, checksum, metadata, _signature = _parts(release)
    record = json.loads(metadata)
    record[field] = value
    with pytest.raises(ReleaseError):
        verify_offer(identity, "0.1.2", *_resigned(key, checksum, record))


def test_an_unknown_field_is_refused_even_when_signed(release, identity, key):
    _package, checksum, metadata, _signature = _parts(release)
    record = json.loads(metadata) | {"install_script": "powershell -c ..."}
    with pytest.raises(ReleaseError, match="shape"):
        verify_offer(identity, "0.1.2", *_resigned(key, checksum, record))


def test_a_checksum_file_naming_another_digest_is_refused(release, identity, key):
    _package, _checksum, metadata, _signature = _parts(release)
    record = json.loads(metadata)
    forged = f"{'0' * 64}  {record['package']}\n".encode()
    with pytest.raises(ReleaseError, match="checksum"):
        verify_offer(identity, "0.1.2", *_resigned(key, forged, record))


@pytest.mark.parametrize("installed", ["0.1.3", "0.1.4", "1.0.0"])
def test_only_a_newer_version_is_offered(release, identity, installed):
    _package, checksum, metadata, signature = _parts(release)
    with pytest.raises(ReleaseError, match="not newer"):
        verify_offer(identity, installed, checksum, metadata, signature)


def test_versions_compare_as_numbers(tmp_path, identity, key):
    package = tmp_path / "built.msix"
    package.write_bytes(b"package")
    files = prepare(package, tmp_path / "r", identity, key, version="0.10.0", revision=3, commit=COMMIT)
    offer = verify_offer(identity, "0.9.9", *(path.read_bytes() for path in files[1:]))
    assert offer.package_version == "0.10.0.3"


def test_oversized_metadata_and_short_signatures_are_refused_before_parsing(release, identity):
    _package, checksum, metadata, signature = _parts(release)
    with pytest.raises(ReleaseError, match="size"):
        verify_offer(identity, "0.1.2", checksum, metadata + b" " * 4096, signature)
    with pytest.raises(ReleaseError, match="size"):
        verify_offer(identity, "0.1.2", checksum, metadata, signature[:63])


@pytest.mark.parametrize("damage", ["flip", "truncate", "extend"])
def test_a_package_that_differs_from_its_checksum_is_refused(release, identity, damage):
    package, checksum, metadata, signature = _parts(release)
    offer = verify_offer(identity, "0.1.2", checksum, metadata, signature)
    content = bytearray(package.read_bytes())
    if damage == "flip":
        content[10] ^= 1
    elif damage == "truncate":
        content = content[:-1]
    else:
        content += b"\0"
    package.write_bytes(bytes(content))
    with pytest.raises(ReleaseError, match="does not match"):
        verify_package(package, offer)


def test_prepare_signs_only_with_the_identitys_key_into_a_new_folder(tmp_path, identity, key):
    package = tmp_path / "built.msix"
    package.write_bytes(b"package")
    with pytest.raises(ReleaseError, match="release key"):
        prepare(package, tmp_path / "a", identity, ed25519.Ed25519PrivateKey.generate(), version="0.1.3",
                revision=0, commit=COMMIT)
    (tmp_path / "b").mkdir()
    with pytest.raises(ReleaseError, match="new release folder"):
        prepare(package, tmp_path / "b", identity, key, version="0.1.3", revision=0, commit=COMMIT)


def test_the_stamped_identity_is_read_strictly(identity):
    record = {"format": 1, "feed": identity.feed, "package_name": identity.package_name, "publisher": PUBLISHER,
              "release_public_key": base64.b64encode(identity.release_key).decode()}
    assert read_identity(record) == identity
    for damaged in (record | {"format": 2}, record | {"extra": 1}, record | {"release_public_key": "not base64!"},
                    record | {"release_public_key": base64.b64encode(b"short").decode()},
                    record | {"publisher": "RoleBand"}, record | {"feed": "../../evil"}, [], None):
        with pytest.raises(ReleaseError):
            read_identity(damaged)


def test_the_offline_spare_signs_the_release_that_replaces_a_leaked_key(tmp_path, identity, key):
    """A release signed with the spare is accepted and names the spare as its signer; one signed by any other key
    is not, so a stolen release key alone cannot lock the owner out."""
    import dataclasses
    import hashlib

    spare = ed25519.Ed25519PrivateKey.generate()
    guarded = dataclasses.replace(identity, spare_key=spare.public_key().public_bytes_raw())
    package = tmp_path / "built.msix"
    package.write_bytes(b"PK replacement package " * 64)
    _, checksum, metadata, signature = (path.read_bytes() for path in
                                        prepare(package, tmp_path / "spare", guarded, spare, version="0.1.4",
                                                revision=0, commit=COMMIT))
    offer = verify_offer(guarded, "0.1.3", checksum, metadata, signature)
    assert offer.version == "0.1.4"
    assert json.loads(metadata)["release_key_sha256"] == hashlib.sha256(guarded.spare_key).hexdigest()
    with pytest.raises(ReleaseError, match="trusted key"):
        verify_offer(identity, "0.1.3", checksum, metadata, signature)
    stranger = ed25519.Ed25519PrivateKey.generate()
    with pytest.raises(ReleaseError, match="release key"):
        prepare(package, tmp_path / "stranger", guarded, stranger, version="0.1.4", revision=0, commit=COMMIT)


def test_an_identity_may_name_a_spare_that_is_not_the_release_key(identity):
    record = {"format": 1, "feed": identity.feed, "package_name": identity.package_name, "publisher": PUBLISHER,
              "release_public_key": base64.b64encode(identity.release_key).decode()}
    spare = ed25519.Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    assert read_identity(record | {"spare_release_public_key": base64.b64encode(spare).decode()}).spare_key == spare
    for damaged in (record | {"spare_release_public_key": record["release_public_key"]},
                    record | {"spare_release_public_key": base64.b64encode(b"short").decode()},
                    record | {"spare_release_public_key": "not base64!"}):
        with pytest.raises(ReleaseError):
            read_identity(damaged)


def test_the_metadata_names_every_identity_fact(identity):
    record = manifest(identity, version="0.1.3", revision=2, commit=COMMIT, sha256="b" * 64, size=10)
    assert (record["package_name"], record["publisher"], record["feed"], record["platform"]) == (
        identity.package_name, identity.publisher, identity.feed, "windows")
