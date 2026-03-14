"""Integration domain schemas. Response schemas accept ORM (metadata_ -> metadata, has_api_key)."""

from datetime import datetime
from typing import Any, Dict, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class IntegrationCreate(BaseModel):
    """Integration creation schema."""

    name: str
    kind: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


def _integration_orm_to_dict(obj: Any) -> Dict[str, Any]:
    """Build dict from Integration ORM (metadata_ -> metadata) for response validation."""
    return {
        "id": obj.id,
        "user_id": obj.user_id,
        "name": obj.name,
        "kind": obj.kind,
        "metadata": getattr(obj, "metadata_", None),
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
    }


class IntegrationResponse(BaseModel):
    """Integration response schema; parse from ORM (metadata_ -> metadata) via validator."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    kind: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def orm_metadata(cls, data: Union[Any, Dict]) -> Union[Dict, Any]:
        if hasattr(data, "metadata_"):
            return _integration_orm_to_dict(data)
        return data


def _integration_list_orm_to_dict(obj: Any) -> Dict[str, Any]:
    """Build dict from Integration ORM for list (has_api_key = len(api_keys) > 0)."""
    api_keys = getattr(obj, "api_keys", [])
    return {
        "id": obj.id,
        "name": obj.name,
        "kind": obj.kind,
        "created_at": obj.created_at,
        "has_api_key": len(api_keys) > 0,
    }


class IntegrationListResponse(BaseModel):
    """Integration list item schema; parse from ORM (has_api_key from api_keys)."""

    id: UUID
    name: str
    kind: Optional[str] = None
    created_at: datetime
    has_api_key: bool = False  # Hint that at least one key exists; never expose raw key

    @model_validator(mode="before")
    @classmethod
    def orm_has_api_key(cls, data: Union[Any, Dict]) -> Union[Dict, Any]:
        if hasattr(data, "api_keys"):
            return _integration_list_orm_to_dict(data)
        return data
