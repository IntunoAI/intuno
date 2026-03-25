from fastapi import APIRouter, Depends, Query

from src.economy.schemas.market import (
    OrderBookResponse,
    OrderCreate,
    OrderResponse,
    TradeResponse,
)
from src.economy.services.market import MarketService

router = APIRouter()


@router.post("/orders", response_model=OrderResponse, status_code=201)
async def place_order(
    payload: OrderCreate,
    market_service: MarketService = Depends(),
) -> OrderResponse:
    """Place a new bid or ask on the marketplace."""
    return await market_service.place_order(payload)


@router.get("/book/{capability}", response_model=OrderBookResponse)
async def get_order_book(
    capability: str,
    market_service: MarketService = Depends(),
) -> OrderBookResponse:
    """Get the current order book for a capability."""
    return await market_service.get_order_book(capability)


@router.post("/match/{capability}", response_model=list[TradeResponse])
async def match_orders(
    capability: str,
    tick: int = Query(0, ge=0),
    market_service: MarketService = Depends(),
) -> list[TradeResponse]:
    """Trigger order matching for a capability (used by simulator)."""
    return await market_service.match_orders(capability, tick=tick)


@router.get("/trades", response_model=list[TradeResponse])
async def list_trades(
    market_service: MarketService = Depends(),
    capability: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[TradeResponse]:
    """List recent trades."""
    return await market_service.list_trades(
        capability=capability, limit=limit, offset=offset,
    )
