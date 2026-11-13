"""Verify isolated Windows runtime imports, extensions and offline SDK wheels."""

import argparse
import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path


def snapshot(root):
    result = {}
    for path in root.rglob("*"):
        if path.is_file():
            with path.open("rb") as source:
                result[str(path.relative_to(root))] = hashlib.file_digest(source, "sha256").hexdigest()
    return result


def probe(resources, state):
    resources, state = resources.resolve(), state.resolve()
    if (sys.platform != "win32" or Path(sys.prefix).resolve() != resources / "runtime"
            or state.exists() or state.is_relative_to(resources) or resources.is_relative_to(state)):
        raise ValueError("Use the bundled Python and a new state directory outside its resources")
    if not (resources / "trial.json").is_file():
        raise ValueError("Only synthetic development bundles can be probed")
    for name in tuple(os.environ):
        if name.startswith("ROLEBAND_"):
            del os.environ[name]
    os.environ.update(ROLEBAND_PACKAGED="1", ROLEBAND_STATE_DIR=str(state),
                      ROLEBAND_PGDATA=str(state / "db"), ROLEBAND_CACHE_DIR=str(state / "cache"),
                      ROLEBAND_PLUGINS_DIR=str(state / "plugins"), ROLEBAND_SECRET_KEY_FILE=str(state / "secret.key"),
                      ROLEBAND_DATABASE_URL="", ROLEBAND_NO_USAGE_STATS="1", ROLEBAND_LOCAL_AUTH="1",
                      ROLEBAND_SEARCH_SEMANTIC_ENABLED="false", ROLEBAND_SEARCH_WARM_MODEL_ON_STARTUP="false",
                      PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONUTF8="1")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(resources / "engine"))
    from tracker.platform.windows_private import private_directory

    private_directory(state)
    before = snapshot(resources)
    names = ("numpy", "onnxruntime", "tokenizers", "cryptography.fernet", "asyncpg", "psycopg2",
             "curl_cffi", "selectolax.lexbor", "pydantic_core", "roleband_robots", "roleband_plugin_sdk",
             "tracker.api.app", "tracker.mcp.server")
    for name in names:
        module = importlib.import_module(name)
        if not Path(module.__file__).resolve().is_relative_to(resources):
            raise ValueError(f"{name} escaped bundled resources")
    from tracker.platform.embedded_db import ensure_server, run_psql, stop_server

    server = None
    try:
        server = ensure_server(state / "db", database="roleband_runtime_probe", required_extensions=("vector", "pg_trgm"))
        result = run_psql(server.dsn(), server.bin_dir,
                          "CREATE EXTENSION vector; CREATE EXTENSION pg_trgm; "
                          "SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector; SELECT similarity('radar','radar')")
        if result.splitlines()[-2:] != ["1", "1"]:
            raise ValueError("Bundled vector or trigram queries failed")
        venv = state / "sdk-venv"
        subprocess.run([sys.executable, "-I", "-B", "-m", "venv", "--without-pip", "--system-site-packages", str(venv)],
                       check=True, capture_output=True, timeout=120)
        python = venv / "Scripts/python.exe"
        wheels = sorted((resources / "plugin-wheels").glob("*.whl"))
        if len(wheels) != 2:
            raise ValueError("Expected two offline SDK wheels")
        subprocess.run([str(python), "-I", "-B", "-m", "pip", "--isolated", "install", "--no-index", "--no-deps",
                        "--ignore-installed", *map(str, wheels)], check=True, capture_output=True, timeout=120)
        subprocess.run([str(python), "-I", "-B", "-c",
                        ("import sys, roleband_plugin_sdk, roleband_robots; from pathlib import Path; "
                        "assert Path(roleband_plugin_sdk.__file__).is_relative_to(Path(sys.prefix)); "
                        "assert Path(roleband_robots.__file__).is_relative_to(Path(sys.prefix))")],
                       check=True, capture_output=True, timeout=30)
    finally:
        if server is not None:
            stop_server(server.pgdata)
    if snapshot(resources) != before:
        raise ValueError("Runtime verification changed immutable resources")
    return {"ok": True, "python": sys.version.split()[0], "imports": names,
            "extensions": ["vector", "pg_trgm"], "sdk_wheels": "installed offline", "resources_unchanged": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(probe(args.resources, args.state)))


if __name__ == "__main__":
    main()
