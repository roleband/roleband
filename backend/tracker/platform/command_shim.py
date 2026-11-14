"""The `roleband` command on a Mac: a small script in `~/.local/bin` that runs the app's client.

The app writes it each time it starts its own engine, so a moved app is picked up at its next
start. It names the app bundle's own path, never a versioned or temporary one, and runs the
bundled interpreter with `-I -B`: no bytecode is written into the bundle and nothing from the
working directory, `PYTHONPATH` or a project `.env` is read. Once the app is gone from that path,
the script prints one line asking the person to open the app, and exits with the
engine-unavailable status.

Nothing here edits a shell profile or needs an administrator: a person whose PATH lacks
`~/.local/bin` is told so by `roleband connect`. A file at the shim's path that this module did not
write, or a link, is left alone. Standard library only.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

#: The second line of every shim this module writes. A file without it is the person's own.
MARKER = "# roleband command shim, format 1"
#: The client's exit status for an engine it cannot reach (`outcomes.EXIT_UNAVAILABLE`).
STALE_EXIT = 3
#: Where an app's engine entry point sits inside its bundle.
ENTRY = Path("Contents/Resources/engine/packaged.py")

WRITTEN = "written"
UNCHANGED = "unchanged"
#: Something else holds the shim's path, a link or a file without `MARKER`.
KEPT_FOREIGN = "kept_foreign"
#: The app runs from a disk image, a translocated copy or another folder: nothing is written.
NOT_INSTALLED = "not_installed"


def shim_path(home: Path) -> Path:
    return home / ".local" / "bin" / "roleband"


def installed_location(app: Path, home: Path) -> bool:
    """Whether `app` is a bundle directly inside `/Applications` or `~/Applications`, the only
    places the app starts an engine from (`AppLocation.isInstalled` in the launcher). A disk
    image's `/Volumes` and the system's translocation folder are neither."""
    resolved = Path(os.path.realpath(app))
    if resolved.suffix != ".app":
        return False
    folders = {os.path.realpath("/Applications"), os.path.realpath(home / "Applications")}
    return str(resolved.parent) in folders


def render(app: Path, python: Path) -> str:
    """The shim for the bundle at `app`, run by its interpreter at `python` (inside `app`)."""
    relative = python.relative_to(app)
    return "\n".join([
        "#!/bin/sh",
        MARKER,
        "# The RoleBand app rewrites this file each time it starts; an edit here does not last.",
        f"app={shlex.quote(str(app))}",
        f'python="$app/{relative.as_posix()}"',
        f'entry="$app/{ENTRY.as_posix()}"',
        'if [ ! -x "$python" ] || [ ! -f "$entry" ]; then',
        '  echo "roleband: RoleBand is no longer at $app. Open RoleBand once to set this command up again." >&2',
        f"  exit {STALE_EXIT}",
        "fi",
        'exec "$python" -I -B "$entry" client "$@"',
        "",
    ])


def is_ours(path: Path) -> bool:
    """Whether `path` is a regular file this module wrote."""
    if path.is_symlink() or not path.is_file():
        return False
    try:
        with path.open(encoding="utf-8") as handle:
            handle.readline()
            return handle.readline().rstrip("\n") == MARKER
    except (OSError, UnicodeDecodeError):
        return False


def install(app: Path, python: Path, home: Path) -> str:
    """Write the shim for the bundle at `app`; one of the outcome constants above.

    Raises `OSError` when the folder or file cannot be written; the caller decides whether that
    matters (an engine start goes on without it)."""
    app = Path(os.path.realpath(app))
    python = Path(os.path.realpath(python))
    if not installed_location(app, home) or not python.is_relative_to(app):
        return NOT_INSTALLED
    target = shim_path(home)
    text = render(app, python)
    if target.is_symlink() or (target.exists() and not is_ours(target)):
        return KEPT_FOREIGN
    try:
        if target.read_text(encoding="utf-8") == text and os.access(target, os.X_OK):
            return UNCHANGED
    except FileNotFoundError:
        pass
    except UnicodeDecodeError:
        return KEPT_FOREIGN
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    partial = target.with_name(f".roleband.{os.getpid()}.partial")
    try:
        with open(partial, "w", encoding="utf-8") as handle:
            handle.write(text)
        partial.chmod(0o755)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    return WRITTEN


def directory_on_path(directory: Path, search_path: str | None) -> bool:
    """Whether `directory` is one of the folders in `search_path` (a `PATH` value)."""
    wanted = os.path.realpath(directory)
    for entry in (search_path or "").split(os.pathsep):
        if entry and os.path.realpath(os.path.expanduser(entry)) == wanted:
            return True
    return False
