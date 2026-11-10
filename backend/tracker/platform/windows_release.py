"""Windows release files and the owner authorization an installed app requires of an update.

A release is four files, as on the Mac: the MSIX package, its checksum, its metadata and an
Ed25519 signature over the checksum bytes followed by the metadata bytes. The app trusts only
the release key, feed and package identity stamped in its own signed package; a valid
Windows signature on an MSIX does not authorize it as a RoleBand release.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

FORMAT = 1
ARCHITECTURE = "x64"
#: Windows 11 21H2, the minimum the package manifest declares.
MINIMUM_BUILD = 22000
METADATA_LIMIT = 4096
CHECKSUM_LIMIT = 512
PACKAGE_LIMIT = 2 * 1024 ** 3
_STABLE = re.compile(r"(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})", re.ASCII)
_HEX = re.compile(r"[0-9a-f]{64}", re.ASCII)
_COMMIT = re.compile(r"[0-9a-f]{40}", re.ASCII)
_FEED = re.compile(r"[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}", re.ASCII)
_PACKAGE_NAME = re.compile(r"[A-Za-z0-9.-]{3,50}", re.ASCII)
_KEYS = {"format", "platform", "version", "package_version", "package_name", "publisher", "architecture",
         "minimum_windows_build", "commit", "tag", "feed", "package", "sha256", "bytes", "release_key_sha256"}


class ReleaseError(ValueError):
    """The files are not an authorized RoleBand release for this installation."""


@dataclass(frozen=True)
class Identity:
    """What an installed package trusts: one feed, one release key, one package identity. The spare key, kept
    offline, signs the release that replaces a lost or leaked release key; that release's package names new keys."""

    feed: str
    release_key: bytes
    package_name: str
    publisher: str
    spare_key: bytes | None = None


@dataclass(frozen=True)
class Offer:
    version: str
    package_version: str
    package: str
    sha256: str
    bytes: int
    commit: str


def stable_version(version: object) -> tuple[int, int, int]:
    if not isinstance(version, str) or not (match := _STABLE.fullmatch(version)):
        raise ReleaseError("A Windows release has a stable version, major.minor.patch")
    parts = tuple(int(part) for part in match.groups())
    if any(part > 65535 for part in parts):
        raise ReleaseError("Each version part must fit a Windows package version")
    return parts[0], parts[1], parts[2]


def names(version: str) -> tuple[str, str, str, str]:
    stable_version(version)
    prefix = f"RoleBand-{version}-Windows-{ARCHITECTURE}"
    return prefix + ".msix", prefix + ".sha256", prefix + ".json", prefix + ".sig"


def read_identity(record: Any) -> Identity:
    """The trust anchor stamped in a package, as JSON with the key in base64."""
    required = {"format", "feed", "release_public_key", "package_name", "publisher"}
    if (not isinstance(record, dict) or record.get("format") != 1
            or set(record) not in (required, required | {"spare_release_public_key"})):
        raise ReleaseError("The release identity is damaged")
    feed, name, publisher = record["feed"], record["package_name"], record["publisher"]
    try:
        key = base64.b64decode(record["release_public_key"], validate=True)
        spare = (base64.b64decode(record["spare_release_public_key"], validate=True)
                 if "spare_release_public_key" in record else None)
    except (TypeError, ValueError) as error:
        raise ReleaseError("The release identity is damaged") from error
    if (not isinstance(feed, str) or not _FEED.fullmatch(feed) or not isinstance(name, str)
            or not _PACKAGE_NAME.fullmatch(name) or not isinstance(publisher, str)
            or not publisher.startswith("CN=") or len(publisher) > 8192 or len(key) != 32
            or (spare is not None and (len(spare) != 32 or spare == key))):
        raise ReleaseError("The release identity is damaged")
    return Identity(feed, key, name, publisher, spare)


def manifest(identity: Identity, *, version: str, revision: int, commit: str, sha256: str,
             size: int, signer: bytes | None = None) -> dict[str, Any]:
    major, minor, patch = stable_version(version)
    if type(revision) is not int or not 0 <= revision <= 65535:
        raise ReleaseError("The package revision must fit a Windows package version")
    return {"format": FORMAT, "platform": "windows", "version": version,
            "package_version": f"{major}.{minor}.{patch}.{revision}", "package_name": identity.package_name,
            "publisher": identity.publisher, "architecture": ARCHITECTURE,
            "minimum_windows_build": MINIMUM_BUILD, "commit": commit, "tag": "v" + version,
            "feed": identity.feed, "package": names(version)[0], "sha256": sha256, "bytes": size,
            "release_key_sha256": hashlib.sha256(signer or identity.release_key).hexdigest()}


def digest(path: Path) -> tuple[str, int]:
    checksum, size = hashlib.sha256(), 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(block)
            size += len(block)
    return checksum.hexdigest(), size


def prepare(package: Path, destination: Path, identity: Identity, private_key: ed25519.Ed25519PrivateKey,
            *, version: str, revision: int, commit: str) -> list[Path]:
    """Write the four release files for one signed MSIX into a new folder."""
    if not _COMMIT.fullmatch(commit):
        raise ReleaseError("Expected the exact 40-character source commit")
    public = private_key.public_key().public_bytes_raw()
    if public not in (identity.release_key, identity.spare_key):
        raise ReleaseError("The signing key is not the release key the identity names")
    if destination.exists():
        raise ReleaseError("Choose a new release folder")
    sha, size = digest(package)
    if not 0 < size <= PACKAGE_LIMIT:
        raise ReleaseError("The package size is out of bounds")
    package_name, checksum_name, metadata_name, signature_name = names(version)
    checksum = f"{sha}  {package_name}\n".encode()
    metadata = (json.dumps(manifest(identity, version=version, revision=revision, commit=commit,
                                    sha256=sha, size=size, signer=public), indent=2) + "\n").encode()
    destination.mkdir(parents=True)
    (destination / package_name).write_bytes(package.read_bytes())
    (destination / checksum_name).write_bytes(checksum)
    (destination / metadata_name).write_bytes(metadata)
    (destination / signature_name).write_bytes(private_key.sign(checksum + metadata))
    return [destination / name for name in (package_name, checksum_name, metadata_name, signature_name)]


def _signed(key: bytes, signature: bytes, message: bytes) -> bool:
    try:
        ed25519.Ed25519PublicKey.from_public_bytes(key).verify(signature, message)
    except InvalidSignature:
        return False
    return True


def verify_offer(identity: Identity, installed: str, checksum: bytes, metadata: bytes,
                 signature: bytes) -> Offer:
    """Accept release metadata only when the owner signed it for this installation and it is newer."""
    if len(metadata) > METADATA_LIMIT or len(checksum) > CHECKSUM_LIMIT or len(signature) != 64:
        raise ReleaseError("Release metadata or its signature has the wrong size")
    signer = next((key for key in (identity.release_key, identity.spare_key) if key is not None
                   and _signed(key, signature, checksum + metadata)), None)
    if signer is None:
        raise ReleaseError("The release signature does not match the trusted key")
    try:
        record = json.loads(metadata)
    except (ValueError, UnicodeError) as error:
        raise ReleaseError("Release metadata is not JSON") from error
    if not isinstance(record, dict) or set(record) != _KEYS or record.get("format") != FORMAT:
        raise ReleaseError("Release metadata has an unsupported shape")
    version, commit, sha, size = record["version"], record["commit"], record["sha256"], record["bytes"]
    if (not isinstance(commit, str) or not _COMMIT.fullmatch(commit) or not isinstance(sha, str)
            or not _HEX.fullmatch(sha) or type(size) is not int or not 0 < size <= PACKAGE_LIMIT):
        raise ReleaseError("Release metadata names an invalid commit, checksum or size")
    revision = str(record["package_version"]).rpartition(".")[2]
    if not revision.isascii() or not revision.isdecimal():
        raise ReleaseError("Release metadata names an invalid package version")
    expected = manifest(identity, version=version, revision=int(revision), commit=commit, sha256=sha, size=size,
                        signer=signer)
    if record != expected:
        raise ReleaseError("The release is for another platform, package, publisher, feed or key")
    if checksum != f"{sha}  {expected['package']}\n".encode():
        raise ReleaseError("The checksum file does not match the release metadata")
    if stable_version(version) <= stable_version(installed):
        raise ReleaseError("The release is not newer than the installed version")
    return Offer(version, expected["package_version"], expected["package"], sha, size, commit)


def verify_package(path: Path, offer: Offer) -> None:
    if path.is_symlink() or not path.is_file():
        raise ReleaseError("The downloaded package is not a regular file")
    if path.stat().st_size != offer.bytes or digest(path) != (offer.sha256, offer.bytes):
        raise ReleaseError("The downloaded package does not match its signed checksum")
