"""Agent config and chat request/response schemas."""

from datetime import datetime
from typing import List, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ChatMessage(BaseModel):
    """OpenAI-style message (role + content)."""

    role: Literal["system", "user", "assistant"]
    content: str


class AgentChatRequest(BaseModel):
    """Conversation input: list of messages."""

    messages: List[ChatMessage]


class AgentChatResponse(BaseModel):
    """Assistant text response (no tools)."""

    content: str


class AgentConfigCreate(BaseModel):
    """Schema for creating an agent config."""

    name: str
    guardrail: str
    description: str
    purpose: str


class AgentConfigResponse(BaseModel):
    """Agent config response (for create endpoint)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    guardrail: str
    description: str
    purpose: str
    created_at: datetime
