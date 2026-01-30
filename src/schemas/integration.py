"""Integration domain schemas."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel


class IntegrationCreate(BaseModel):
    """Integration creation schema."""

    name: str
    kind: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class IntegrationResponse(BaseModel):
    """Integration response schema."""

    id: UUID
    user_id: UUID
    name: str
    kind: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class IntegrationListResponse(BaseModel):
    """Integration list item schema."""

    id: UUID
    name: str
    kind: Optional[str] = None
    created_at: datetime
    has_api_key: bool = False  # Hint that at least one key exists; never expose raw key
