"""Build a pinned pg_trgm bundle in a disposable copy of the database wheel.

Run on the target platform with a compiler; users run install_pg_contrib instead.
Inputs and output hashes live in tracker/platform/pgcontrib/manifest.json.

    python -m scripts.package_pg_contrib --wheel WHEEL --source TARBALL
    python -m scripts.package_pg_contrib --download

On Windows the wheel's server is built by MinGW gcc against the UCRT, so the
bundle is built the same way: MSYS2's UCRT64 toolchain (`pacman -S
mingw-w64-ucrt-x86_64-gcc make`), found at `ROLEBAND_MSYS2` or `C:\\msys64`. A
DLL built against the older msvcrt would load, but would run a second C runtime
inside the server. The Windows bundle also carries a pgvector rebuilt without
`-march=native`: the wheel's own `vector.dll` was tuned to its build machine
and dies with an illegal instruction on CPUs without AVX-512. pgvector picks its
SIMD paths at run time, so the portable build gives up no fast path.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import platform
import shlex
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from scripts.build_pg_contrib import _ssl_context

BUNDLES = Path(__file__).resolve().parents[1] / "tracker/platform/pgcontrib"
WINDOWS = platform.system() == "Windows"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def platform_key() -> str:
    return f"{platform.system().lower()}-{platform.machine().lower()}"


def _make(args: list[str], env: dict[str, str]) -> None:
    if not WINDOWS:
        subprocess.run(["make", *args], check=True, env=env)
        return
    msys = Path(os.environ.get("ROLEBAND_MSYS2", r"C:\msys64"))
    bash = msys / "usr/bin/bash.exe"
    if not bash.is_file():
        raise SystemExit(f"MSYS2 not found at {msys}; install it and its UCRT64 gcc, or set ROLEBAND_MSYS2")
    # A login shell under MSYSTEM=UCRT64 puts the UCRT64 gcc first on PATH.
    command = shlex.join(["make", *args])
    subprocess.run([str(bash), "-lc", command], check=True, env={**env, "MSYSTEM": "UCRT64", "CHERE_INVOKING": "1"})


def package(wheel: Path, source: Path, pgvector_source: Path | None = None) -> Path:
    manifest = json.loads((BUNDLES / "manifest.json").read_text())
    entry = manifest["platforms"][platform_key()]
    if wheel.name != entry["wheel"] or digest(wheel) != entry["wheel_sha256"]:
        raise ValueError("database wheel does not match the pinned build input")
    if digest(source) != manifest["source_sha256"]:
        raise ValueError("PostgreSQL source does not match the pinned build input")
    pgvector = entry.get("pgvector")
    if pgvector and (pgvector_source is None or digest(pgvector_source) != pgvector["source_sha256"]):
        raise ValueError("pgvector source does not match the pinned build input")
    with tempfile.TemporaryDirectory(prefix="roleband-pgcontrib-") as temporary:
        work = Path(temporary)
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(work / "wheel")
            for info in archive.infolist():
                if info.external_attr >> 16:
                    (work / "wheel" / info.filename).chmod(info.external_attr >> 16)
        with tarfile.open(source) as archive:
            archive.extractall(work, filter="data")
        tree = work / "wheel/pixeltable_pgserver/pginstall"
        pg_config = tree / ("bin/pg_config.exe" if WINDOWS else "bin/pg_config")
        src = work / f"postgresql-{manifest['postgres']}"
        common = [f"PG_CONFIG={pg_config.as_posix()}", "enable_rpath=no"]
        if WINDOWS:
            # PGXS would build a version resource from a file only a full source
            # tree generates; the resource is optional metadata.
            common.append("WIN32RES=")
        if platform.system() == "Darwin":
            sdk = subprocess.check_output(["xcrun", "--show-sdk-path"], text=True).strip()
            common += [f"PG_SYSROOT={sdk}", "MACOSX_DEPLOYMENT_TARGET=14.0"]
        env = {**os.environ, "SOURCE_DATE_EPOCH": "0"}
        _make(["-C", (src / "contrib/pg_trgm").as_posix(), "USE_PGXS=1", *common, "install"], env)
        suffix = ".dll" if WINDOWS else ".dylib" if platform.system() == "Darwin" else ".so"
        files = [tree / "lib/postgresql" / f"pg_trgm{suffix}", *sorted((tree / "share/postgresql/extension").glob("pg_trgm*"))]
        if pgvector and pgvector_source is not None:
            with tarfile.open(pgvector_source) as archive:
                archive.extractall(work / "pgvector", filter="data")
            (vector_src,) = (work / "pgvector").iterdir()
            # The SQL scripts and control file are the wheel's own, same version.
            _make(["-C", vector_src.as_posix(), *common, "OPTFLAGS=", "install"], env)
            files.append(tree / "lib/postgresql" / f"vector{suffix}")
        notice = tree / "share/postgresql/extension/pg_trgm.COPYRIGHT"
        notice.write_bytes((src / "COPYRIGHT").read_bytes())
        files.append(notice)
        hashes = {}
        output = BUNDLES / entry["bundle"]
        with output.open("wb") as raw, gzip.GzipFile(fileobj=raw, filename="", mode="wb", mtime=0) as compressed, tarfile.open(fileobj=compressed, mode="w") as archive:
            for path in sorted(set(files)):
                relative = path.relative_to(tree).as_posix()
                data = path.read_bytes()
                hashes[relative] = hashlib.sha256(data).hexdigest()
                member = tarfile.TarInfo(relative)
                member.size = len(data)
                member.mode = 0o644
                archive.addfile(member, io.BytesIO(data))
        entry.update(sha256=digest(output), files=hashes)
        (BUNDLES / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--pgvector-source", type=Path, help="pgvector source tarball (Windows bundle)")
    parser.add_argument("--download", action="store_true", help="download the pinned build inputs")
    args = parser.parse_args()
    if args.download:
        if args.wheel or args.source or args.pgvector_source:
            parser.error("--download cannot be combined with --wheel, --source or --pgvector-source")
        manifest = json.loads((BUNDLES / "manifest.json").read_text())
        entry = manifest["platforms"][platform_key()]
        with tempfile.TemporaryDirectory(prefix="roleband-pgcontrib-inputs-") as temporary:
            wheel = Path(temporary) / entry["wheel"]
            source = Path(temporary) / "postgresql.tar.gz"
            downloads = [(entry["wheel_url"], wheel), (manifest["source_url"], source)]
            vector = None
            if "pgvector" in entry:
                vector = Path(temporary) / "pgvector.tar.gz"
                downloads.append((entry["pgvector"]["source_url"], vector))
            for url, path in downloads:
                with urllib.request.urlopen(url, context=_ssl_context(), timeout=60) as response:  # noqa: S310
                    path.write_bytes(response.read())
            print(package(wheel, source, vector))
    else:
        if not args.wheel or not args.source:
            parser.error("supply --wheel and --source, or --download")
        print(package(args.wheel, args.source, args.pgvector_source))


if __name__ == "__main__":
    main()
