"""Assemble a Windows development trial with isolated, hash-locked runtime files."""

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


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def run(*arguments, cwd=ROOT, env=None):
    subprocess.run([str(value) for value in arguments], cwd=cwd, env=env, check=True)


def assemble(destination, cache, trial_id=None):
    if sys.platform != "win32":
        raise ValueError("Build Windows trials on Windows")
    destination, cache = destination.resolve(), cache.resolve()
    if destination.exists() or destination.is_relative_to(ROOT) or ROOT.is_relative_to(destination):
        raise ValueError("Choose a new trial destination outside the checkout")
    dashboard = ROOT / "dashboard/dist"
    if not (dashboard / "index.html").is_file():
        raise ValueError("Build the dashboard before assembling a trial")
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
    for required in ("RoleBand.App.exe", "RoleBand.App.pri", "App.xbf", "MainWindow.xbf"):
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
    env = dict(os.environ, PYTHONPATH=str(engine), PYTHONDONTWRITEBYTECODE="1", ROLEBAND_PACKAGED="1")
    for name in ("ROLEBAND_DATABASE_URL", "ROLEBAND_PGDATA", "ROLEBAND_STATE_DIR", "ROLEBAND_CACHE_DIR", "ROLEBAND_PLUGINS_DIR"):
        env.pop(name, None)
    # Installing a checked extension only writes immutable runtime resources.
    run(python, "-m", "scripts.install_pg_contrib", cwd=engine, env=env)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines()
    metadata = {**pin, "version": version, "source_revision": revision, "dirty_paths": dirty,
                "requirements_sha256": digest(ROOT / "backend/requirements.txt"),
                "runtime_lock_sha256": digest(runtime_lock), "trial_only": True, "trial_id": (trial_id or uuid.uuid4()).hex}
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
    args = parser.parse_args()
    assemble(args.destination, args.cache, args.trial_id)


if __name__ == "__main__":
    main()
