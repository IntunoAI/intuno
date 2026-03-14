"""Broker domain: invoke orchestration + invocation logging; quotas, timeouts, policies."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PostgresUUID
from sqlalchemy.orm import relationship

from .base import BaseModel
from .invocation_log import InvocationLog


class BrokerConfig(BaseModel):
    """
    Per-integration or global broker config: timeouts, retries, quotas, allowlist.
    integration_id is None for global defaults; one row per integration override.
    Resolution: integration row if present, else global.
    """

    __tablename__: str = "broker_configs"

    integration_id: Column[Optional[UUID]] = Column(
        PostgresUUID, ForeignKey("integrations.id"), nullable=True, unique=True
    )

    # Timeouts
    request_timeout_seconds: Column[int] = Column(Integer, nullable=False, default=30)

    # Retries (optional)
    max_retries: Column[Optional[int]] = Column(Integer, nullable=True)
    retry_backoff_seconds: Column[Optional[int]] = Column(Integer, nullable=True)

    # Quotas (null = unlimited)
    monthly_invocation_quota: Column[Optional[int]] = Column(Integer, nullable=True)
    daily_invocation_quota: Column[Optional[int]] = Column(Integer, nullable=True)

    # Allowlist: non-empty = only these agent UUIDs allowed; null/empty = allow all
    allowed_agent_ids: Column[Optional[List[UUID]]] = Column(
        ARRAY(PostgresUUID), nullable=True
    )

    integration = relationship("Integration", back_populates="broker_config")


__all__ = ["BrokerConfig", "InvocationLog"]
