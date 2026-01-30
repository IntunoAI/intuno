"""Agent config domain model for configurable chat agents."""

from sqlalchemy import Column, String, Text

from agents.models.base import BaseModel


class AgentConfig(BaseModel):
    """Configurable agent: name, guardrail, description, purpose for chat completion."""

    __tablename__: str = "agent_configs"

    name = Column(String, nullable=False, unique=True, index=True)
    guardrail = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    purpose = Column(Text, nullable=False)
