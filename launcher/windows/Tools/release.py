"""Write or check the four files of a Windows release for one signed MSIX."""

import argparse
import getpass
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: E402

from tracker.platform.windows_release import (  # noqa: E402
    ReleaseError,
    names,
    prepare,
    read_identity,
    verify_offer,
    verify_package,
)


def signing_key(path):
    data = path.read_bytes()
    try:
        private = serialization.load_pem_private_key(data, None)
    except TypeError:
        private = serialization.load_pem_private_key(data, getpass.getpass("Release key passphrase: ").encode())
    if not isinstance(private, ed25519.Ed25519PrivateKey):
        raise ReleaseError("The release key must use Ed25519")
    return private


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
    verify = commands.add_parser("verify")
    verify.add_argument("--directory", type=Path, required=True)
    verify.add_argument("--identity", type=Path, required=True)
    verify.add_argument("--installed", required=True)
    args = parser.parse_args(argv)
    identity = read_identity(json.loads(args.identity.read_text(encoding="utf-8")))
    try:
        if args.action == "prepare":
            version = json.loads((ROOT / "dashboard/package.json").read_text(encoding="utf-8"))["version"]
            commit = args.commit or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
            for path in prepare(args.package, args.destination, identity, signing_key(args.key),
                                version=version, revision=args.revision, commit=commit):
                print(path)
        else:
            print(json.dumps(check(args.directory, identity, args.installed).__dict__))
    except ReleaseError as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
