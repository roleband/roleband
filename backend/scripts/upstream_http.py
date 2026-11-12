"""One GET for the freshness checks, tried again on a connection failure or a server error.

The checks run unattended once a month, so a passing network fault must not read as a
verdict. A refusal (any status below 500) is final at once: asking again cannot change it.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping

import httpx


def get(url: str, *, user_agent: str, headers: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None, attempts: int = 3, pause: float = 5.0,
        sleep: Callable[[float], None] = time.sleep) -> httpx.Response:
    """The answer to GET `url`, `attempts` tries in all. The last failure is raised, and so
    is any error status."""
    with httpx.Client(timeout=30.0, follow_redirects=True, transport=transport,
                      headers={"User-Agent": user_agent, **(headers or {})}) as client:
        for attempt in range(1, attempts + 1):
            try:
                response = client.get(url)
                if response.status_code < 500:
                    break
                response.raise_for_status()
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == attempts:
                    raise
            sleep(pause * attempt)
    response.raise_for_status()
    return response
