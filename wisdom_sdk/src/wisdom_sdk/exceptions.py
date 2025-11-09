class WisdomError(Exception):
    """Base exception for all Wisdom SDK errors."""

    pass


class APIKeyMissingError(WisdomError):
    """Raised when the API key is not provided."""

    def __init__(self, message="API key is required for authentication."):
        self.message = message
        super().__init__(self.message)


class AuthenticationError(WisdomError):
    """Raised when authentication fails."""

    pass


class InvocationError(WisdomError):
    """Raised when an agent invocation fails."""

    pass
