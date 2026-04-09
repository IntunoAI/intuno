"""Custom HTTP exceptions. All extend HTTPException so FastAPI handles them by default."""

from fastapi import HTTPException, status

__all__ = [
    "BaseCustomException",
    "UnauthorizedException",
    "ForbiddenException",
    "NotFoundException",
    "ResourceAlreadyExistsException",
    "BadRequestException",
    "ValidationException",
    "DatabaseException",
    "RateLimitException",
    "PlatformHaltedException",
    "AgentDisabledException",
]


class BaseCustomException(HTTPException):
    """Base exception class for custom exceptions"""

    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)


# Authentication & Authorization Exceptions
class UnauthorizedException(BaseCustomException):
    """Exception raised when user is not authenticated"""

    def __init__(self, detail: str = "Authentication required"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class ForbiddenException(BaseCustomException):
    """Exception raised when user doesn't have permission"""

    def __init__(
        self, detail: str = "You don't have permission to perform this action"
    ):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


# Resource Exceptions
class NotFoundException(BaseCustomException):
    """Exception raised when a resource is not found"""

    def __init__(self, resource: str = "Resource"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource} not found"
        )


class ResourceAlreadyExistsException(BaseCustomException):
    """Exception raised when attempting to create a resource that already exists"""

    def __init__(self, resource: str = "Resource"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT, detail=f"{resource} already exists"
        )


# Client Error Exceptions
class BadRequestException(BaseCustomException):
    """Exception raised when the request is invalid (e.g. business rule violation)."""

    def __init__(self, detail: str = "Bad request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class ValidationException(BaseCustomException):
    """Exception raised when input validation fails."""

    def __init__(self, detail: str = "Validation error"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail
        )


# Database Exceptions
class DatabaseException(BaseCustomException):
    """Exception raised when database operations fail"""

    def __init__(self, detail: str = "Database operation failed"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail
        )


# Rate Limiting Exceptions
class RateLimitException(BaseCustomException):
    """Exception raised when rate limit is exceeded"""

    def __init__(self, detail: str = "Rate limit exceeded. Please try again later"):
        super().__init__(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)


# Safety & Governance Exceptions
class PlatformHaltedException(BaseCustomException):
    """Exception raised when the platform is in emergency halt mode"""

    def __init__(self, detail: str = "Platform is in emergency halt mode. All agent operations are suspended."):
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


class AgentDisabledException(BaseCustomException):
    """Exception raised when a disabled agent is invoked"""

    def __init__(self, detail: str = "Agent has been disabled by an administrator"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
