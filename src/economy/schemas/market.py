import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OrderCreate(BaseModel):
    """Payload to place a new bid or ask on the marketplace."""

    agent_id: uuid.UUID
    side: str = Field(..., pattern="^(bid|ask)$")
    capability: str = Field(..., min_length=1)
    price: int = Field(..., gt=0)
    quantity: int = Field(default=1, gt=0)


class OrderResponse(BaseModel):
    """Single order in the book."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    agent_id: uuid.UUID
    side: str
    capability: str
    price: int
    quantity: int
    status: str
    tick: int
    created_at: datetime


class TradeResponse(BaseModel):
    """A completed trade between two agents."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    bid_order_id: uuid.UUID
    ask_order_id: uuid.UUID
    buyer_agent_id: uuid.UUID
    seller_agent_id: uuid.UUID
    capability: str
    price: int
    status: str
    latency_ms: int
    tick: int
    created_at: datetime


class OrderBookResponse(BaseModel):
    """Snapshot of current open bids and asks for a capability."""

    capability: str
    bids: list[OrderResponse]
    asks: list[OrderResponse]
