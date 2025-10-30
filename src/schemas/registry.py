"""Registry domain schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CapabilitySchema(BaseModel):
    """Capability schema matching the AAWW spec."""
    
    id: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    auth_type: Dict[str, str]


class AgentManifest(BaseModel):
    """Agent manifest schema matching the AAWW spec."""
    
    agent_id: str
    name: str
    description: str
    version: str
    endpoints: Dict[str, str]
    capabilities: List[CapabilitySchema]
    requires: Optional[List[Dict[str, str]]] = None
    tags: List[str] = []
    trust: Dict[str, str] = {"verification": "self-signed"}


class AgentResponse(BaseModel):
    """Agent response schema."""
    
    id: UUID
    agent_id: str
    name: str
    description: str
    version: str
    invoke_endpoint: Optional[str] = None
    manifest_json: Dict[str, Any]
    tags: List[str]
    trust_verification: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    capabilities: List[CapabilitySchema]
    requirements: Optional[List[Dict[str, str]]] = None


class AgentListResponse(BaseModel):
    """Agent list response schema."""
    
    id: UUID
    agent_id: str
    name: str
    description: str
    version: str
    invoke_endpoint: Optional[str] = None
    tags: List[str]
    trust_verification: str
    is_active: bool
    created_at: datetime
    capabilities: List[CapabilitySchema] = []


class AgentSearchQuery(BaseModel):
    """Agent search query schema."""
    
    tags: Optional[List[str]] = None
    capability: Optional[str] = None
    search: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class DiscoverQuery(BaseModel):
    """Semantic discovery query schema."""
    
    query: str
    limit: int = Field(default=10, ge=1, le=50)


class AgentCreate(BaseModel):
    """Agent creation schema."""
    
    manifest: AgentManifest


class AgentUpdate(BaseModel):
    """Agent update schema."""
    
    manifest: AgentManifest
