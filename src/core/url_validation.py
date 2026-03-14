"""SSRF protection for invoke_endpoint URLs."""

import fnmatch
import ipaddress
from typing import List, Optional
from urllib.parse import urlparse

# Private and dangerous IP ranges
_PRIVATE_IPV4_RANGES = (
    ipaddress.IPv4Network("10.0.0.0/8"),       # RFC 1918
    ipaddress.IPv4Network("172.16.0.0/12"),   # RFC 1918
    ipaddress.IPv4Network("192.168.0.0/16"),  # RFC 1918
    ipaddress.IPv4Network("127.0.0.0/8"),     # Loopback
    ipaddress.IPv4Network("169.254.0.0/16"),  # Link-local
    ipaddress.IPv4Network("0.0.0.0/8"),       # Current network
)
_PRIVATE_IPV6_RANGES = (
    ipaddress.IPv6Network("::1/128"),         # Loopback
    ipaddress.IPv6Network("fe80::/10"),       # Link-local
    ipaddress.IPv6Network("fd00::/8"),        # Unique local
)


def _is_private_ip(ip_str: str) -> bool:
    """Return True if the IP is in a blocked (private/dangerous) range."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    if ip.version == 4:
        for net in _PRIVATE_IPV4_RANGES:
            if ip in net:
                return True
    else:
        for net in _PRIVATE_IPV6_RANGES:
            if ip in net:
                return True
    return False


def _host_matches_allowlist(host: str, patterns: List[str]) -> bool:
    """Return True if host matches any pattern (supports * wildcard)."""
    for p in patterns:
        if fnmatch.fnmatch(host.lower(), p.lower()):
            return True
    return False


def validate_invoke_endpoint(
    url: str,
    *,
    allowed_hosts: Optional[List[str]] = None,
    resolve_hostname: bool = True,
) -> None:
    """
    Validate an invoke endpoint URL for SSRF safety. Raises ValueError if invalid.

    :param url: The URL to validate (e.g. https://example.com/invoke)
    :param allowed_hosts: If non-empty, only these host patterns are allowed (e.g. ["*.example.com"]).
                         If None/empty, allow any host whose resolved IP is public.
    :param resolve_hostname: If True and host is a hostname, resolve to IP and check for private ranges.
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Invalid URL: {e}") from e

    if not parsed.scheme or parsed.scheme.lower() not in ("http", "https"):
        raise ValueError("invoke_endpoint must use http or https scheme")

    if not parsed.hostname:
        raise ValueError("invoke_endpoint must have a host")

    host = parsed.hostname

    # If it's an IP address, check directly
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False

    # If allowlist is set, check match first (allows localhost/127.0.0.1 in dev)
    if allowed_hosts and _host_matches_allowlist(host, allowed_hosts):
        return

    if is_ip:
        if _is_private_ip(host):
            raise ValueError("invoke_endpoint cannot target private or loopback IP addresses")
        return

    # Hostname
    if allowed_hosts:
        if not _host_matches_allowlist(host, allowed_hosts):
            raise ValueError(
                f"invoke_endpoint host '{host}' is not in allowed list: {allowed_hosts}"
            )
        return

    # No allowlist: resolve and reject if it resolves to private IP
    if resolve_hostname:
        import socket
        try:
            for info in socket.getaddrinfo(host, None):
                # info is (family, type, proto, canonname, sockaddr)
                sockaddr = info[4]
                ip = sockaddr[0] if isinstance(sockaddr, (list, tuple)) else sockaddr
                if _is_private_ip(ip):
                    raise ValueError(
                        f"invoke_endpoint host '{host}' resolves to private IP {ip}"
                    )
        except socket.gaierror:
            raise ValueError(f"invoke_endpoint host '{host}' could not be resolved")
