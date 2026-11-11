"""Publish discovery for the installed engine, without starting its database."""

from __future__ import annotations

import argparse
import logging
import webbrowser
from pathlib import Path

from tracker import __version__
from tracker.config import get_settings
from tracker.platform.launcher import (
    installation_identity,
    register_installation,
    unregister_installation,
)
from tracker.platform.local_http import Client
from tracker.platform.paths import DATA_DIR, REPO_ROOT

logger = logging.getLogger(__name__)


def refresh_registration() -> bool:
    settings = get_settings()
    try:
        identity = installation_identity(
            REPO_ROOT, api_host=settings.api_host, api_port=settings.api_port, version=__version__,
        )
        return register_installation(REPO_ROOT, identity, home=Path.home())
    except (OSError, ValueError):
        # Discovery is optional: a read-only home must not stop the engine.
        logger.warning("Could not publish launcher discovery", exc_info=True)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("register", "unregister", "open"))
    args = parser.parse_args()
    if args.action == "open":
        url = Client(DATA_DIR).browser_url()
        if not webbrowser.open(url):
            raise OSError("The browser did not open")
        return
    if args.action == "register":
        changed = refresh_registration()
    else:
        changed = unregister_installation(REPO_ROOT, home=Path.home())
    print("Launcher discovery updated" if changed else "Launcher discovery unchanged")


if __name__ == "__main__":
    main()
