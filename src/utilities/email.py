"""Email utilities for brand verification via Resend."""

import logging
from datetime import datetime
from typing import Optional

import httpx

from src.core.settings import settings

logger = logging.getLogger(__name__)

_RESEND_ENDPOINT = "https://api.resend.com/emails"


def _build_verification_html(code: str, expires_at: Optional[datetime]) -> str:
    expiry_text = ""
    if expires_at:
        expiry_text = f"<p style='color:#828387;font-size:13px;'>This code expires at {expires_at.strftime('%H:%M UTC')}.</p>"
    return f"""
<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;background:#F7F5F3;margin:0;padding:32px;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border:1px solid #E0DEDB;border-radius:8px;padding:40px;">
    <h1 style="font-size:24px;color:#37322F;margin-top:0;">Brand Verification</h1>
    <p style="color:#605A57;">Use the code below to verify ownership of your brand:</p>
    <div style="background:#F7F5F3;border-radius:6px;padding:24px;text-align:center;margin:24px 0;">
      <span style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#37322F;font-family:monospace;">{code}</span>
    </div>
    {expiry_text}
    <p style="color:#828387;font-size:13px;">If you didn't request this, you can safely ignore this email.</p>
  </div>
</body>
</html>
"""


async def send_brand_verification_code(
    to_email: str,
    code: str,
    expires_at: Optional[datetime] = None,
) -> None:
    """Send brand verification code email via Resend.

    Falls back to log-only when RESEND_API_KEY is not configured (dev mode).
    Raises RuntimeError on delivery failure.
    """
    if not settings.RESEND_API_KEY:
        logger.info(
            "send_brand_verification_code (dev/no-key): to=%s code=%s expires_at=%s",
            to_email,
            code,
            expires_at,
        )
        return

    from_field = (
        f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>"
        if settings.EMAIL_FROM_NAME
        else settings.EMAIL_FROM_ADDRESS
    )

    payload = {
        "from": from_field,
        "to": [to_email],
        "subject": f"Your brand verification code: {code}",
        "html": _build_verification_html(code, expires_at),
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            _RESEND_ENDPOINT,
            json=payload,
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        )

    if response.status_code not in (200, 201):
        logger.error(
            "Resend API error: status=%s body=%s",
            response.status_code,
            response.text,
        )
        raise RuntimeError(f"Email delivery failed (status {response.status_code})")

    logger.info("Verification email sent via Resend to %s", to_email)
