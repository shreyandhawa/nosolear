"""Pure request-origin policy: who may talk to the local API.

Every check is an exact (case-insensitive for hosts) membership test. There is no prefix,
suffix or substring matching anywhere, so look-alike names such as `localhost:8000@evil.com`
or `http://localhost:5173.evil.com` never pass.
"""

import ipaddress
from collections.abc import Sequence
from functools import cache
from urllib.parse import urlsplit

_SAME_SITE_VALUES = frozenset({"same-origin", "same-site", "none"})


def peer_is_loopback(host: str | None) -> bool:
    """True only for a literal loopback IP (127.0.0.0/8, ::1, IPv4-mapped loopback)."""
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_loopback


def allowed_hosts(port: int, app_origins: Sequence[str]) -> frozenset[str]:
    """Host header values the API answers to: its own loopback names plus the app origins'."""
    own = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
    return frozenset(own | {urlsplit(origin).netloc.lower() for origin in app_origins})


@cache
def _allowed_hosts_cached(port: int, app_origins: tuple[str, ...]) -> frozenset[str]:
    return allowed_hosts(port, app_origins)


def host_is_allowed(header: str | None, allowed: frozenset[str]) -> bool:
    return header is not None and header.lower() in allowed


def origin_is_allowed(header: str | None, app_origins: Sequence[str]) -> bool:
    """No Origin header is fine (same-origin GETs, curl); `null` and anything else must match."""
    if header is None:
        return True
    if header == "null":
        return False
    return header in app_origins


def fetch_site_is_allowed(header: str | None) -> bool:
    """Allow-list: no header, or a value that says the request is not cross-site."""
    return header is None or header.strip().lower() in _SAME_SITE_VALUES


def check_request(
    *,
    peer: str | None,
    host: str | None,
    origin: str | None,
    fetch_site: str | None,
    port: int,
    app_origins: Sequence[str],
) -> str | None:
    """None when the request is allowed, else the first failing reason code."""
    if not peer_is_loopback(peer):
        return "peer"
    if not host_is_allowed(host, _allowed_hosts_cached(port, tuple(app_origins))):
        return "host"
    if not origin_is_allowed(origin, app_origins):
        return "origin"
    if not fetch_site_is_allowed(fetch_site):
        return "fetch_site"
    return None
