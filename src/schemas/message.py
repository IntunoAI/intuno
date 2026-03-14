"""Message domain schemas. Response schemas accept ORM (metadata_ mapped to metadata)."""

from datetime import datetime
from typing import Any, Dict, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class MessageCreate(BaseModel):
    """Message creation schema."""

    role: str  # user | assistant | system | tool
    content: str
    metadata: Optional[Dict[str, Any]] = None


def _message_orm_to_dict(obj: Any) -> Dict[str, Any]:
    """Build dict from Message ORM (metadata_ -> metadata) for response validation."""
    return {
        "id": obj.id,
        "conversation_id": obj.conversation_id,
        "role": obj.role,
        "content": obj.content,
        "metadata": getattr(obj, "metadata_", None),
        "created_at": obj.created_at,
    }


class MessageResponse(BaseModel):
    """Message response schema; parse from ORM (metadata_ -> metadata) via validator."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def orm_metadata(cls, data: Union[Any, Dict]) -> Union[Dict, Any]:
        if hasattr(data, "metadata_"):
            return _message_orm_to_dict(data)
        return data


class MessageListResponse(BaseModel):
    """Message list item schema; same shape, accepts ORM via validator."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def orm_metadata(cls, data: Union[Any, Dict]) -> Union[Dict, Any]:
        if hasattr(data, "metadata_"):
            return _message_orm_to_dict(data)
        return data
