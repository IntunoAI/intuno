from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.economy.utilities.event_bus import event_bus

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Stream simulation events to the dashboard in real time."""
    await websocket.accept()
    event_bus.register_websocket(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unregister_websocket(websocket)
