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
from src.schemas.brand import (
    BrandCreate,
    BrandResponse,
    BrandUpdate,
    VerifyBrandRequest,
    VerifyBrandResponse,
)
from src.schemas.broker import InvokeRequest, InvokeResponse
from src.schemas.conversation import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
)
from src.schemas.integration import (
    IntegrationCreate,
    IntegrationListResponse,
    IntegrationResponse,
)
from src.schemas.invocation_log import InvocationLogResponse
from src.schemas.message import (
    MessageCreate,
    MessageListResponse,
    MessageResponse,
)
from src.schemas.task import (
    StepSchema,
    TaskCreate,
    TaskListResponse,
    TaskResponse,
)
from src.schemas.registry import (
    AgentListResponse,
    AgentRegistration,
    AgentResponse,
    AgentSearchQuery,
    AgentUpdate,
    DiscoverQuery,
    RateRequest,
    RatingResponse,
)

__all__ = [
    # Auth
    "ApiKeyCreate",
    "ApiKeyListResponse",
    "ApiKeyResponse",
    "TokenResponse",
    "UserLogin",
    "UserRegister",
    "UserResponse",
    # Brand
    "BrandCreate",
    "BrandResponse",
    "BrandUpdate",
    "VerifyBrandRequest",
    "VerifyBrandResponse",
    # Broker
    "InvokeRequest",
    "InvokeResponse",
    # Conversation
    "ConversationCreate",
    "ConversationListResponse",
    "ConversationResponse",
    "ConversationUpdate",
    # Integration
    "IntegrationCreate",
    "IntegrationListResponse",
    "IntegrationResponse",
    # Invocation log
    "InvocationLogResponse",
    # Message
    "MessageCreate",
    "MessageListResponse",
    "MessageResponse",
    # Task
    "StepSchema",
    "TaskCreate",
    "TaskListResponse",
    "TaskResponse",
    # Registry
    "AgentRegistration",
    "AgentListResponse",
    "AgentResponse",
    "AgentSearchQuery",
    "AgentUpdate",
    "DiscoverQuery",
    "RateRequest",
    "RatingResponse",
]
