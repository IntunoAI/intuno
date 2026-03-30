"""Workflow-specific exceptions.

These extend FastAPI's HTTPException (via wisdom's BaseCustomException)
so they are handled automatically by FastAPI's default exception handler.
"""

from __future__ import annotations

from fastapi import HTTPException


class AppException(HTTPException):
    """Base exception for workflow domain errors."""

    status_code: int = 500

    def __init__(self, detail: str = "Internal server error") -> None:
        self.detail = detail
        super().__init__(status_code=self.status_code, detail=detail)


class NotFoundException(AppException):
    status_code = 404


class DSLParseError(AppException):
    status_code = 422


class AgentUnavailableError(AppException):
    status_code = 503


class StepExecutionError(AppException):
    status_code = 502

    def __init__(self, detail: str, attempt: int = 1) -> None:
        super().__init__(detail)
        self.attempt = attempt
