"""Email utilities. Skeleton for brand verification; wire real provider later."""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def send_brand_verification_code(
    to_email: str,
    code: str,
    expires_at: Optional[datetime] = None,
) -> None:
    """Send brand verification code to the given email.

    Skeleton implementation: no-op / log-only. Wire a real provider
    (SMTP, SendGrid, Resend, etc.) when available.
    """
    logger.info(
        "send_brand_verification_code (skeleton): to=%s code=*** expires_at=%s",
        to_email,
        expires_at,
    )
