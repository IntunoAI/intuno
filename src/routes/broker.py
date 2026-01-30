"""Broker routes: invoke only; conversation/message CRUD in conversation and message routers."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.security import get_user_and_integration_from_api_key
from src.exceptions import DatabaseException
from src.models.auth import User
from src.schemas.broker import InvokeRequest, InvokeResponse
from src.services.broker import BrokerService

router = APIRouter(prefix="/broker", tags=["Broker"])


@router.post("/invoke", response_model=InvokeResponse)
async def invoke_agent(
    invoke_request: InvokeRequest,
    user_and_integration: tuple[User, Optional[UUID]] = Depends(
        get_user_and_integration_from_api_key
    ),
    broker_service: BrokerService = Depends(),
):
    """
    Invoke an agent capability through the broker.
    Optional conversation_id and message_id attach the invocation to a conversation/message.
    """
    current_user, integration_id = user_and_integration
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
    except Exception:
        raise DatabaseException("Broker error")
