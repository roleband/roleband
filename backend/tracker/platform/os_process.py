"""This process in the operating system's own terms: the group a stop of its run signals, and how a command line
is quoted for this system's shell."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from collections.abc import Sequence


def current_run_group() -> int | None:
    """What a stop of this run signals: its process group on POSIX. Windows has no process groups; there it is the
    supervisor's run wrapper this process runs under, and None outside one."""
    if sys.platform == "win32":
        from tracker.platform.windows_process import run_wrapper

        return run_wrapper()
    return os.getpgrp()


def shell_join(arguments: Sequence[str]) -> str:
    """`arguments` as one command line for a person to paste into this system's terminal: Windows' quoting rules
    there, POSIX ones elsewhere."""
    return subprocess.list2cmdline(arguments) if sys.platform == "win32" else shlex.join(arguments)
