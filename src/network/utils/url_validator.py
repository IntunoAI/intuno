"""SSRF-safe URL validation for callback URLs and external fetches.

Rejects private/internal IP ranges and validates URL format to prevent
Server-Side Request Forgery attacks when the platform makes outbound
HTTP requests to user-supplied URLs.
"""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

from src.core.settings import settings
from src.exceptions import BadRequestException

logger = logging.getLogger(__name__)

# Private and internal IP networks that should never be targeted
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_ip(hostname: str) -> bool:
    """Check if a hostname resolves to a private/internal IP."""
    try:
        addr = ipaddress.ip_address(hostname)
        return any(addr in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        # Not an IP literal — resolve the hostname
        pass

    try:
        for info in socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP):
            addr = ipaddress.ip_address(info[4][0])
            if any(addr in net for net in _BLOCKED_NETWORKS):
                return True
    except (socket.gaierror, OSError):
        # DNS resolution failed — reject as suspicious
        return True

    return False


def validate_callback_url(url: str) -> str:
    """Validate a callback URL is safe for the platform to POST to.

    Returns the validated URL string.
    Raises BadRequestException if the URL is unsafe.
    """
    if not url or not url.strip():
        raise BadRequestException("Callback URL cannot be empty")

    parsed = urlparse(url)

    # Must be HTTP or HTTPS
    if parsed.scheme not in ("http", "https"):
        raise BadRequestException(
            f"Callback URL must use http or https scheme, got '{parsed.scheme}'"
        )

    # Require HTTPS in production
    if settings.ENVIRONMENT != "development" and parsed.scheme != "https":
        raise BadRequestException(
            "Callback URL must use HTTPS in production"
        )

    # Must have a hostname
    if not parsed.hostname:
        raise BadRequestException("Callback URL must include a hostname")

    # Check allowlist before rejecting private IPs (supports local dev)
    allowed_hosts = [
        h.strip()
        for h in settings.INVOKE_ENDPOINT_ALLOWED_HOSTS.split(",")
        if h.strip()
    ]
    if allowed_hosts and parsed.hostname.lower() in (h.lower() for h in allowed_hosts):
        return url

    # Reject private/internal IPs
    if _is_private_ip(parsed.hostname):
        raise BadRequestException(
            "Callback URL must not target private or internal networks"
        )

    return url
