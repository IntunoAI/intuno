"""Admin authentication dependency."""

from fastapi import Depends

from src.core.auth import get_current_user
from src.exceptions import ForbiddenException
from src.models.auth import User


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require the current user to be an admin.

    Wraps get_current_user and raises 403 if the user does not have
    the is_admin flag set.
    """
    if not getattr(current_user, "is_admin", False):
        raise ForbiddenException("Admin access required")
    return current_user
