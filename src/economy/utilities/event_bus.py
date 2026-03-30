import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from fastapi import WebSocket

log = logging.getLogger("event_bus")


class EventBus:
    """In-memory publish/subscribe bus that also broadcasts to WebSocket clients.

    Event types: OrderPlaced, TradeMatched, SettlementComplete, PriceChanged,
    SimulationTick, SimulationStarted, SimulationStopped.
    """

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._websocket_clients: list[WebSocket] = []

    def subscribe(
        self,
        event_type: str,
        callback: Callable[[str, dict], Coroutine],
    ) -> None:
        """Register an async callback for a specific event type."""
        self._subscribers[event_type].append(callback)

    def unsubscribe(
        self,
        event_type: str,
        callback: Callable,
    ) -> None:
        """Remove a previously registered callback."""
        self._subscribers[event_type] = [
            cb for cb in self._subscribers[event_type] if cb != callback
        ]

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit an event to all subscribers and connected WebSocket clients."""
        envelope = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        for callback in self._subscribers.get(event_type, []):
            try:
                await callback(event_type, data)
            except Exception:
                pass

        for callback in self._subscribers.get("*", []):
            try:
                await callback(event_type, data)
            except Exception:
                pass

        ws_count = len(self._websocket_clients)
        if event_type not in ("SimulationTick",):
            log.info("publish %s → %d ws clients", event_type, ws_count)

        await self._broadcast_to_websockets(envelope)

    async def _broadcast_to_websockets(self, envelope: dict) -> None:
        """Send an event envelope to all connected WebSocket clients."""
        if not self._websocket_clients:
            return

        message = json.dumps(envelope, default=str)
        disconnected: list[WebSocket] = []

        for ws in self._websocket_clients:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            self._websocket_clients.remove(ws)

    def register_websocket(self, websocket: WebSocket) -> None:
        """Add a WebSocket client to the broadcast list."""
        self._websocket_clients.append(websocket)

    def unregister_websocket(self, websocket: WebSocket) -> None:
        """Remove a WebSocket client from the broadcast list."""
        if websocket in self._websocket_clients:
            self._websocket_clients.remove(websocket)


event_bus = EventBus()
