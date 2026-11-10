"""Assemble a Windows bundle, a development trial or a release, with isolated, hash-locked runtime files."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import uuid
from pathlib import Path

from pe_certificates import validate_tree

ROOT = Path(__file__).resolve().parents[3]
#: The feed every release build updates from; a trial carries its own.
RELEASE_FEED = "roleband/roleband"
#: The private feed a rehearsal of the release updates from: the release's build, identity shape and data, published
#: nowhere public.
REHEARSAL_FEED = "roleband/roleband-windows-trials"


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


#: What the bundle copies from the checkout besides the dashboard build.
ENGINE_SOURCES = ("backend/tracker", "backend/alembic", "backend/constraints", "backend/scripts",
                  "backend/desktop.py", "backend/alembic.ini")


def run(*arguments, cwd=ROOT, env=None):
    subprocess.run([str(value) for value in arguments], cwd=cwd, env=env, check=True)


def git(root, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=root, text=True)


def clean_revision(root):
    """The commit a trial is built from, refusing any file that commit does not hold.

    A bundle is traceable only if every copied byte is in the commit: tracked edits,
    untracked files and ignored files inside the copied sources would all ship unrecorded.
    """
    dirty = git(root, "status", "--porcelain", "--untracked-files=all").splitlines()
    if dirty:
        raise ValueError("Commit or remove local changes before assembling a trial: " + ", ".join(dirty[:5]))
    stray = [line for line in git(root, "status", "--porcelain", "--ignored=matching", "--untracked-files=all",
                                  "--", *ENGINE_SOURCES).splitlines()
             if not line.rstrip("/").endswith(("__pycache__", ".pyc"))]
    if stray:
        raise ValueError("Remove ignored files from the engine sources before assembling a trial: "
                         + ", ".join(stray[:5]))
    return git(root, "rev-parse", "HEAD").strip()


def release_identity(root, rehearsal=False):
    """The committed update identity a release build trusts, which also names its package and publisher."""
    if str(root / "backend") not in sys.path:
        sys.path.insert(0, str(root / "backend"))
    from tracker.platform.windows_release import read_identity

    path = root / "launcher/windows/release-identity.json"
    if not path.is_file():
        raise ValueError("A release needs launcher/windows/release-identity.json")
    identity = read_identity(json.loads(path.read_text(encoding="utf-8")))
    feed = REHEARSAL_FEED if rehearsal else RELEASE_FEED
    if identity.feed != feed:
        raise ValueError(f"A {'rehearsal' if rehearsal else 'release'} updates from {feed}, not {identity.feed}")
    return path


def assemble(destination, cache, trial_id=None, channel="trial", rehearsal=False):
    if sys.platform != "win32":
        raise ValueError("Build Windows bundles on Windows")
    if channel not in ("trial", "release"):
        raise ValueError("The channel is trial or release")
    if channel == "release" and trial_id is not None:
        raise ValueError("A release has no trial identity")
    if rehearsal and channel != "release":
        raise ValueError("Only a release is rehearsed")
    identity = (release_identity(ROOT, rehearsal) if channel == "release"
                else ROOT / "launcher/windows/release-identity.json")
    destination, cache = destination.resolve(), cache.resolve()
    if destination.exists() or destination.is_relative_to(ROOT) or ROOT.is_relative_to(destination):
        raise ValueError("Choose a new bundle destination outside the checkout")
    revision = clean_revision(ROOT)
    # Built here, from the clean commit, so the bundled dashboard is that commit's.
    run(shutil.which("npm") or "npm", "run", "build", cwd=ROOT / "dashboard")
    dashboard = ROOT / "dashboard/dist"
    pin = json.loads((ROOT / "launcher/windows/runtime.json").read_text())
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"cpython-{pin['python']}-windows-x64-{pin['sha256'][:16]}.tar.gz"
    if not archive.exists():
        urllib.request.urlretrieve(pin["url"], archive)
    if digest(archive) != pin["sha256"]:
        raise ValueError("Python runtime checksum mismatch")
    run("dotnet", "restore", ROOT / "launcher/windows/RoleBand.App", "--locked-mode", "-p:Platform=x64")
    run("dotnet", "publish", ROOT / "launcher/windows/RoleBand.App", "--no-restore", "-c", "Release",
        "-p:Platform=x64", "-o", destination)
    for required in ("RoleBand.App.exe", "RoleBand.App.pri", "App.xbf", "FlyoutWindow.xbf", "SettingsWindow.xbf",
                     "SetupWindow.xbf", "RoleBand.ico", "Images/AppMark.png"):
        if not (destination / required).is_file():
            raise ValueError(f"Published host is missing {required}")
    resources = destination / "Resources"
    resources.mkdir()
    with tarfile.open(archive, "r:gz") as package:
        package.extractall(resources, filter="data")
    (resources / "python").rename(resources / "runtime")
    python = resources / "runtime/python.exe"
    runtime_lock = ROOT / "launcher/windows/runtime-lock.txt"
    run(python, "-I", "-m", "pip", "--isolated", "install", "--disable-pip-version-check",
        "--only-binary=:all:", "--require-hashes", "--no-deps", "-r", runtime_lock)
    wheels = resources / "plugin-wheels"
    wheels.mkdir()
    for source in ("sdk/python", "robots/python"):
        run(python, "-I", "-m", "pip", "--isolated", "wheel", "--no-build-isolation", "--no-deps",
            "--wheel-dir", wheels, ROOT / source)
    run(python, "-I", "-m", "pip", "--isolated", "install", "--no-index", "--no-deps", *sorted(wheels.glob("*.whl")))
    run(python, "-I", "-m", "pip", "--isolated", "check")
    engine = resources / "engine"
    engine.mkdir()
    for name in ("tracker", "alembic", "constraints", "scripts"):
        shutil.copytree(ROOT / "backend" / name, engine / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("desktop.py", "alembic.ini"):
        shutil.copyfile(ROOT / "backend" / name, engine / name)
    version = json.loads((ROOT / "dashboard/package.json").read_text())["version"]
    (engine / "release.json").write_text(json.dumps({"version": version}) + "\n")
    shutil.copytree(dashboard, resources / "dashboard")
    shutil.copyfile(ROOT / "dashboard/csp-policy.json", resources / "dashboard/csp-policy.json")
    shutil.copyfile(ROOT / "CHANGELOG.md", resources / "CHANGELOG.md")
    shutil.copyfile(ROOT / "LICENSE", resources / "LICENSE")
    # The update identity this build trusts; without one, the build never offers an update.
    if identity.is_file():
        shutil.copyfile(identity, resources / "release-identity.json")
    env = dict(os.environ, PYTHONPATH=str(engine), PYTHONDONTWRITEBYTECODE="1", ROLEBAND_PACKAGED="1")
    for name in ("ROLEBAND_DATABASE_URL", "ROLEBAND_PGDATA", "ROLEBAND_STATE_DIR", "ROLEBAND_CACHE_DIR", "ROLEBAND_PLUGINS_DIR"):
        env.pop(name, None)
    # Installing a checked extension only writes immutable runtime resources.
    run(python, "-m", "scripts.install_pg_contrib", cwd=engine, env=env)
    if clean_revision(ROOT) != revision:
        raise ValueError("The checkout changed during assembly; assemble again from one commit")
    metadata = {**pin, "version": version, "source_revision": revision, "dirty_paths": [],
                "requirements_sha256": digest(ROOT / "backend/requirements.txt"),
                "runtime_lock_sha256": digest(runtime_lock)}
    # The marker decides whose data the app opens: a trial's synthetic folder, or the person's own for a release.
    if channel == "release":
        (resources / "build.json").write_text(json.dumps({"format": 1, "channel": "release", "rehearsal": rehearsal,
                                                          **metadata}, indent=2) + "\n", encoding="utf-8")
    else:
        metadata.update(trial_only=True, trial_id=(trial_id or uuid.uuid4()).hex)
        (resources / "trial.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    validate_tree(destination)
    files = {str(path.relative_to(destination)): digest(path) for path in destination.rglob("*") if path.is_file()}
    (destination / "trial-hashes.json").write_text(json.dumps(files, indent=2) + "\n", encoding="utf-8")
    print(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--trial-id", type=uuid.UUID)
    parser.add_argument("--channel", choices=("trial", "release"), default="trial")
    parser.add_argument("--rehearsal", action="store_true",
                        help=f"a release that updates from {REHEARSAL_FEED}, for trying the release on one machine")
    args = parser.parse_args()
    assemble(args.destination, args.cache, args.trial_id, args.channel, args.rehearsal)


if __name__ == "__main__":
    main()
