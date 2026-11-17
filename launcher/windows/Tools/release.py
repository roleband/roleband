"""Write or check the four files of a Windows release for one signed MSIX, or mark a published one important."""

import argparse
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# Importing identity first puts the checkout's backend on the import path, where tracker is.
from identity import FOUNDATION, PACKAGE_NAME, ROOT, passphrase
from tracker.platform.windows_release import (
    ReleaseError,
    is_important,
    mark_name,
    names,
    prepare,
    read_identity,
    sign_important,
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


def gh(*arguments):
    return subprocess.run(["gh", *arguments], check=True, capture_output=True, text=True).stdout


def important(tag, identity, private_key, run=gh):
    """Signs a published release's important mark and attaches it beside the release's files, once."""
    if not tag.startswith("v"):
        raise ReleaseError("Expected an exact release tag, such as v0.2.3")
    version = tag[1:]
    files, name = set(names(version)), mark_name(version)
    mark = sign_important(private_key, identity, version)
    listing = json.loads(run("release", "view", tag, "--repo", identity.feed, "--json",
                             "tagName,isDraft,isPrerelease,assets"))
    assets = [asset for asset in listing.get("assets") or [] if isinstance(asset, dict)]
    uploaded = {asset.get("name") for asset in assets if asset.get("state", "uploaded") == "uploaded"}
    # Apps offer only a published, non-prerelease release with all four files, so a mark anywhere else would never
    # be read. A mark already there stays: without --clobber the upload could not replace it.
    if listing.get("tagName") != tag or listing.get("isDraft") is not False or listing.get("isPrerelease") is not False:
        raise ReleaseError("The important mark attaches only to a published release")
    if not files <= uploaded:
        raise ReleaseError("Attach the release files before marking it important")
    if name in {asset.get("name") for asset in assets}:
        raise ReleaseError("The release is already marked important")
    if not is_important(identity, version, mark):
        raise ReleaseError("The mark does not verify with the release identity")
    with tempfile.TemporaryDirectory(prefix="roleband-important-") as directory:
        path = Path(directory) / name
        path.write_bytes(mark)
        run("release", "upload", tag, "--repo", identity.feed, str(path))
    return name


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
    mark = commands.add_parser("important", help="mark a published release important: its window returns daily")
    mark.add_argument("--tag", required=True)
    mark.add_argument("--identity", type=Path, required=True)
    mark.add_argument("--key", type=Path, required=True)
    mark.add_argument("--passphrase-env", help="read the key's passphrase from this environment variable")
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
        elif args.action == "important":
            print(important(args.tag, identity, signing_key(args.key, args.passphrase_env)))
        else:
            print(json.dumps(check(args.directory, identity, args.installed).__dict__))
    except ReleaseError as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
