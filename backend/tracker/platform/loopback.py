"""Which addresses and names belong to this computer's loopback.

No mode serves the API beyond this computer: the Mac and Windows apps start it on
127.0.0.1, and authenticated local HTTP requires 127.0.0.1 (`local_http.origin`).
The API has no sign-in on Mac and source installs, so an address another machine can
reach would hand it the whole record, saved keys and agent switches included.
"""

from __future__ import annotations

import ipaddress

#: The one name that always resolves to this computer; any other name is a guess about DNS.
LOOPBACK_NAME = "localhost"


def is_loopback_address(value: str) -> bool:
    """True for an IP literal on this computer's loopback (127.0.0.0/8, ::1, ::ffff:127.x)."""
    try:
        address = ipaddress.ip_address(value.strip().strip("[]").split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped.is_loopback
    return address.is_loopback


def is_loopback_host(value: str) -> bool:
    """True for a host the API may bind: a loopback IP literal or `localhost`."""
    return value.strip().lower().rstrip(".") == LOOPBACK_NAME or is_loopback_address(value)
