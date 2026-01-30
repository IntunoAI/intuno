"""Expose all schemas for easy importing."""

from src.schemas.auth import (
    ApiKeyCreate,
    ApiKeyListResponse,
    ApiKeyResponse,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)
from src.schemas.broker import InvokeRequest, InvokeResponse
from src.schemas.invocation_log import InvocationLogResponse
from src.schemas.registry import (
    AgentCreate,
    AgentListResponse,
    AgentManifest,
    AgentResponse,
    AgentSearchQuery,
    AgentUpdate,
    CapabilitySchema,
    DiscoverQuery,
)

__all__ = [
    # Auth schemas
    "UserRegister",
    "UserLogin",
    "TokenResponse",
    "ApiKeyCreate",
    "ApiKeyResponse",
    "ApiKeyListResponse",
    "UserResponse",
    # Registry schemas
    "AgentManifest",
    "CapabilitySchema",
    "AgentResponse",
    "AgentListResponse",
    "AgentSearchQuery",
    "DiscoverQuery",
    "AgentCreate",
    "AgentUpdate",
    # Broker schemas
    "InvokeRequest",
    "InvokeResponse",
    "InvocationLogResponse",
]
