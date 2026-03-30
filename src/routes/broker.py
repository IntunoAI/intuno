"""Broker routes: invoke only; conversation/message CRUD in conversation and message routers."""

import json
import logging
from typing import AsyncIterator, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.core.security import get_user_and_integration
from src.exceptions import DatabaseException
from src.models.auth import User
from src.schemas.broker import InvokeRequest, InvokeResponse
from src.services.broker import BrokerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/broker", tags=["Broker"])


@router.post(
    "/invoke",
    response_model=InvokeResponse
)
async def invoke_agent(
    invoke_request: InvokeRequest,
    request: Request,
    user_and_integration: tuple[User, Optional[UUID]] = Depends(
        get_user_and_integration
    ),
    broker_service: BrokerService = Depends(),
):
    """
    Invoke an agent through the broker.
    Optional conversation_id and message_id attach the invocation to a conversation/message.
    """
    current_user, integration_id = user_and_integration
    # Inject shared HTTP client and request tracing
    http_client = getattr(request.app.state, "http_client", None)
    if http_client is not None:
        broker_service.set_http_client(http_client)
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        broker_service.set_request_id(request_id)
    try:
        return await broker_service.invoke_agent(
            invoke_request,
            caller_user_id=current_user.id,
            integration_id=integration_id,
            conversation_id=invoke_request.conversation_id,
            message_id=invoke_request.message_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Broker invoke failed: %s", exc)
        raise DatabaseException("Broker error")


def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Events message."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/invoke/stream")
async def invoke_agent_stream(
    invoke_request: InvokeRequest,
    request: Request,
    user_and_integration: tuple[User, Optional[UUID]] = Depends(
        get_user_and_integration
    ),
    broker_service: BrokerService = Depends(),
):
    """Invoke an agent and return the response as an SSE stream.

    If the target agent supports streaming, the broker proxies the SSE stream.
    Otherwise, the synchronous response is wrapped in a single SSE event.
    """
    current_user, integration_id = user_and_integration
    http_client = getattr(request.app.state, "http_client", None)
    if http_client is not None:
        broker_service.set_http_client(http_client)
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        broker_service.set_request_id(request_id)

    async def event_stream() -> AsyncIterator[str]:
        try:
            result = await broker_service.invoke_agent_stream(
                invoke_request,
                caller_user_id=current_user.id,
                integration_id=integration_id,
                conversation_id=invoke_request.conversation_id,
                message_id=invoke_request.message_id,
            )
            # If the service returned a non-streaming response, wrap it
            if isinstance(result, InvokeResponse):
                if result.success:
                    yield _sse_event("result", result.model_dump(mode="json"))
                else:
                    yield _sse_event("error", {"error": result.error, "status_code": result.status_code})
                yield _sse_event("done", {})
                return

            # Streaming: iterate over async generator from service
            async for chunk in result:
                yield _sse_event("chunk", chunk)
            yield _sse_event("done", {})
        except Exception as exc:
            logger.exception("Broker stream failed: %s", exc)
            yield _sse_event("error", {"error": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
