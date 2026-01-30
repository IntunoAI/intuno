"""Message domain schemas."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel


class MessageCreate(BaseModel):
    """Message creation schema."""

    role: str  # user | assistant | system | tool
    content: str
    metadata: Optional[Dict[str, Any]] = None


class MessageResponse(BaseModel):
    """Message response schema."""

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime


class MessageListResponse(BaseModel):
    """Message list item schema (same as response for list)."""

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
