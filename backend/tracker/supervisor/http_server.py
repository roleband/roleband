"""Serve an authenticated engine on an exclusively owned loopback socket."""

from __future__ import annotations

import argparse
import os
import socket
import sys

import uvicorn

from tracker.platform.local_http import origin


def exclusive_socket(host: str, port: int) -> socket.socket:
    origin(host, port)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if sys.platform == "win32":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind((host, port))
        return listener
    except BaseException:
        listener.close()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    os.environ["ROLEBAND_LOCAL_AUTH"] = "1"
    from tracker.config import get_settings

    settings = get_settings()
    if args.host != settings.api_host or args.port != settings.api_port:
        parser.error("HTTP endpoint must match the engine configuration")
    with exclusive_socket(args.host, args.port) as listener:
        os.environ["ROLEBAND_HTTP_EXCLUSIVE"] = "1"
        config = uvicorn.Config("tracker.api.app:app", host=args.host, port=args.port, access_log=False)
        uvicorn.Server(config).run(sockets=[listener])


if __name__ == "__main__":
    main()
