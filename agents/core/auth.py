"""API-token-only authentication. Intuno is the sole consumer."""

from fastapi import Security

from agents.core.security import api_key_header
from agents.core.settings import settings
from agents.exceptions import UnauthorizedException


async def require_api_key(api_key: str = Security(api_key_header)) -> None:
    """
    Validate X-API-Key against the shared secret. Intuno is the only caller.
    Raises UnauthorizedException if missing or invalid.
    """
    if not api_key:
        raise UnauthorizedException("API key is missing")
    if not settings.AGENTS_API_KEY or api_key != settings.AGENTS_API_KEY:
        raise UnauthorizedException("Invalid or expired API key")
