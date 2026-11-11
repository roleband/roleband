"""Write or check the four files of a Windows release for one signed MSIX."""

import argparse
import json
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# Importing identity first puts the checkout's backend on the import path, where tracker is.
from identity import FOUNDATION, PACKAGE_NAME, ROOT, passphrase
from tracker.platform.windows_release import (
    ReleaseError,
    names,
    prepare,
    read_identity,
    verify_offer,
    verify_package,
)

UAP = "{http://schemas.microsoft.com/appx/manifest/uap/windows10}"
VIRTUALIZATION = "{http://schemas.microsoft.com/appx/manifest/virtualization/windows10}"
#: What RoleBand's own package states besides its identity. Windows removes a package's LocalAppData folder with
#: the package unless the manifest excludes it, so the excluded folder must be the one the person's data lives in.
RELEASE_STATES = {"DisplayName": "RoleBand", "VisualElements DisplayName": "RoleBand",
                  "ExcludedDirectory": [r"$(KnownFolder:LocalAppData)\RoleBand"]}


def signing_key(path, passphrase_env=None):
    """The release key; an encrypted one opens with the passphrase typed here, or, where no one can type it, one
    read from the named environment variable."""
    data = path.read_bytes()
    try:
        private = serialization.load_pem_private_key(data, None)
    except TypeError:
        try:
            secret = passphrase(passphrase_env, "Release key passphrase: ")
        except ValueError as error:
            raise ReleaseError(str(error)) from error
        try:
            private = serialization.load_pem_private_key(data, secret)
        except (TypeError, ValueError) as error:
            raise ReleaseError("The release key does not open with this passphrase") from error
    if not isinstance(private, ed25519.Ed25519PrivateKey):
        raise ReleaseError("The release key must use Ed25519")
    return private


def stamped(package, identity, version, revision):
    """Refuse a package whose own manifest is not the release being prepared: another name, publisher or version
    would be signed as this release and installed as something else, and RoleBand's own package must also carry
    its name and keep the person's data folder."""
    try:
        with zipfile.ZipFile(package) as archive:
            manifest = ElementTree.fromstring(archive.read("AppxManifest.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise ReleaseError("The package has no readable AppxManifest.xml") from error
    found = manifest.find(f"{FOUNDATION}Identity")
    expected = {"Name": identity.package_name, "Publisher": identity.publisher, "Version": f"{version}.{revision}"}
    if found is None or any(found.get(field) != value for field, value in expected.items()):
        stated = {field: found.get(field) for field in expected} if found is not None else None
        raise ReleaseError(f"The package states {stated}, not {expected}")
    if identity.package_name == PACKAGE_NAME:
        visual = manifest.find(f".//{UAP}VisualElements")
        stated = {"DisplayName": manifest.findtext(f"{FOUNDATION}Properties/{FOUNDATION}DisplayName"),
                  "VisualElements DisplayName": visual.get("DisplayName") if visual is not None else None,
                  "ExcludedDirectory": [folder.text for folder in manifest.iter(f"{VIRTUALIZATION}ExcludedDirectory")]}
        if stated != RELEASE_STATES:
            raise ReleaseError(f"The package states {stated}, not {RELEASE_STATES}")


def check(directory, identity, installed):
    version = json.loads(next(directory.glob("*.json")).read_text(encoding="utf-8"))["version"]
    expected = set(names(version))
    if {path.name for path in directory.iterdir()} != expected:
        raise ReleaseError("The release folder has missing or unexpected files")
    package, checksum, metadata, signature = (directory / name for name in names(version))
    offer = verify_offer(identity, installed, checksum.read_bytes(), metadata.read_bytes(), signature.read_bytes())
    verify_package(package, offer)
    return offer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    make = commands.add_parser("prepare")
    make.add_argument("--package", type=Path, required=True)
    make.add_argument("--destination", type=Path, required=True)
    make.add_argument("--identity", type=Path, required=True)
    make.add_argument("--key", type=Path, required=True)
    make.add_argument("--revision", type=int, default=0)
    make.add_argument("--commit")
    make.add_argument("--version", help="the version released; by default the checkout's dashboard/package.json")
    make.add_argument("--passphrase-env", help="read the key's passphrase from this environment variable")
    verify = commands.add_parser("verify")
    verify.add_argument("--directory", type=Path, required=True)
    verify.add_argument("--identity", type=Path, required=True)
    verify.add_argument("--installed", required=True)
    args = parser.parse_args(argv)
    try:
        identity = read_identity(json.loads(args.identity.read_text(encoding="utf-8")))
        if args.action == "prepare":
            version = args.version or json.loads((ROOT / "dashboard/package.json").read_text(encoding="utf-8"))["version"]
            commit = args.commit or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
            stamped(args.package, identity, version, args.revision)
            for path in prepare(args.package, args.destination, identity, signing_key(args.key, args.passphrase_env),
                                version=version, revision=args.revision, commit=commit):
                print(path)
        else:
            print(json.dumps(check(args.directory, identity, args.installed).__dict__))
    except ReleaseError as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
