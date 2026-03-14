"""Encrypt/decrypt per-agent credentials at rest."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from src.core.settings import settings


def _get_fernet_key() -> bytes:
    """Derive Fernet key from CREDENTIALS_ENCRYPTION_KEY or JWT_SECRET_KEY."""
    secret = settings.CREDENTIALS_ENCRYPTION_KEY or settings.JWT_SECRET_KEY
    if not secret:
        raise ValueError("CREDENTIALS_ENCRYPTION_KEY or JWT_SECRET_KEY must be set")
    # Fernet needs 32 bytes, base64-encoded
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_credential(plain: str) -> str:
    """Encrypt a credential for storage. Returns base64-encoded ciphertext."""
    f = Fernet(_get_fernet_key())
    return f.encrypt(plain.encode()).decode()


def decrypt_credential(encrypted: str) -> str:
    """Decrypt a stored credential. Raises ValueError if invalid."""
    try:
        f = Fernet(_get_fernet_key())
        return f.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        raise ValueError("Failed to decrypt credential (invalid or corrupted)")
