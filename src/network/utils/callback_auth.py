"""HMAC-signed callback URLs for authenticated bidirectional communication.

When delivering a message to an external agent, the reply_url is signed
with an HMAC so that only the intended recipient can POST back.  This
prevents attackers from injecting messages by guessing participant IDs.

Signature: HMAC-SHA256(network_id + participant_id + expiry, secret)
"""

import hashlib
import hmac
import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from uuid import UUID

from src.core.settings import settings

# Default callback URL expiry: 24 hours
CALLBACK_EXPIRY_SECONDS = 86400


def sign_callback_url(
    base_url: str,
    network_id: UUID,
    participant_id: UUID,
    secret: str | None = None,
    expiry_seconds: int = CALLBACK_EXPIRY_SECONDS,
) -> str:
    """Append HMAC signature and expiry to a callback URL.

    Returns the URL with ?sig=<hex>&exp=<timestamp> appended.
    """
    secret = secret or settings.JWT_SECRET_KEY
    exp = int(time.time()) + expiry_seconds

    sig = _compute_signature(network_id, participant_id, exp, secret)

    parsed = urlparse(base_url)
    params = parse_qs(parsed.query)
    params["sig"] = [sig]
    params["exp"] = [str(exp)]
    new_query = urlencode(params, doseq=True)
    signed_url = urlunparse(parsed._replace(query=new_query))
    return signed_url


def verify_callback_signature(
    network_id: UUID,
    participant_id: UUID,
    sig: str,
    exp: str,
    secret: str | None = None,
) -> bool:
    """Verify an HMAC signature from a callback URL.

    Returns True if the signature is valid and not expired.
    """
    secret = secret or settings.JWT_SECRET_KEY

    # Check expiry
    try:
        exp_ts = int(exp)
    except (ValueError, TypeError):
        return False

    if time.time() > exp_ts:
        return False

    expected = _compute_signature(network_id, participant_id, exp_ts, secret)
    return hmac.compare_digest(sig, expected)


def _compute_signature(
    network_id: UUID,
    participant_id: UUID,
    exp: int,
    secret: str,
) -> str:
    """Compute HMAC-SHA256 signature for callback authentication."""
    message = f"{network_id}:{participant_id}:{exp}"
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
