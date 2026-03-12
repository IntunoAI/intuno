"""Broker domain service: simple 1-1 agent orchestration (invoke + logging; quotas/timeouts via config)."""

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
from fastapi import Depends

from src.models.conversation import Conversation
from src.models.invocation_log import InvocationLog
from src.repositories.broker import BrokerConfigRepository
from src.repositories.conversation import ConversationRepository
from src.repositories.invocation_log import InvocationLogRepository
from src.repositories.message import MessageRepository
from src.repositories.registry import RegistryRepository
from src.schemas.broker import InvokeRequest, InvokeResponse
from src.core.settings import settings

DEFAULT_REQUEST_TIMEOUT_SECONDS = 30


class BrokerService:
    """Service for brokering agent invocations (1-1; config: quotas, timeouts, allowlist)."""

    def __init__(
        self,
        invocation_log_repository: InvocationLogRepository = Depends(),
        broker_config_repository: BrokerConfigRepository = Depends(),
        registry_repository: RegistryRepository = Depends(),
        conversation_repository: ConversationRepository = Depends(),
        message_repository: MessageRepository = Depends(),
    ):
        self.invocation_log_repository = invocation_log_repository
        self.broker_config_repository = broker_config_repository
        self.registry_repository = registry_repository
        self.conversation_repository = conversation_repository
        self.message_repository = message_repository

    async def invoke_agent(
        self,
        invoke_request: InvokeRequest,
        caller_user_id: UUID,
        integration_id: Optional[UUID] = None,
        conversation_id: Optional[UUID] = None,
        message_id: Optional[UUID] = None,
    ) -> InvokeResponse:
        """
        Invoke an agent capability through the broker.
        :param invoke_request: InvokeRequest
        :param caller_user_id: UUID
        :param integration_id: Optional integration (from API key)
        :param conversation_id: Optional conversation (from request, validated)
        :param message_id: Optional message (from request, must belong to conversation)
        :return: InvokeResponse
        """
        start_time = time.time()

        # Load effective broker config (integration override or global)
        config = await self.broker_config_repository.get_effective_config(integration_id)

        # Resolve conversation_id and message_id from request if not passed
        conv_id = conversation_id or invoke_request.conversation_id
        msg_id = message_id or invoke_request.message_id

        # Validate conversation and message ownership
        if conv_id is not None:
            conversation = await self.conversation_repository.get_by_id(conv_id)
            if not conversation or conversation.user_id != caller_user_id:
                return InvokeResponse(
                    success=False,
                    error="Conversation not found or access denied",
                    latency_ms=int((time.time() - start_time) * 1000),
                    status_code=404,
                )
            if integration_id is not None and conversation.integration_id != integration_id:
                return InvokeResponse(
                    success=False,
                    error="Conversation does not belong to this integration",
                    latency_ms=int((time.time() - start_time) * 1000),
                    status_code=403,
                )
            if invoke_request.external_user_id is not None:
                conversation.external_user_id = invoke_request.external_user_id
                await self.conversation_repository.update(conversation)
        else:
            # No conversation: create one for audit so invocation log has conversation_id
            conversation = Conversation(
                user_id=caller_user_id,
                integration_id=integration_id,
                title=None,
                external_user_id=invoke_request.external_user_id,
            )
            conversation = await self.conversation_repository.create(conversation)
            conv_id = conversation.id
        if msg_id is not None:
            if conv_id is None:
                return InvokeResponse(
                    success=False,
                    error="message_id requires conversation_id",
                    latency_ms=int((time.time() - start_time) * 1000),
                    status_code=400,
                )
            message = await self.message_repository.get_by_id(msg_id)
            if not message or message.conversation_id != conv_id:
                return InvokeResponse(
                    success=False,
                    error="Message not found or does not belong to conversation",
                    latency_ms=int((time.time() - start_time) * 1000),
                    status_code=404,
                )

        # Get the agent
        agent = await self.registry_repository.get_agent_by_agent_id(invoke_request.agent_id)
        if not agent or not agent.is_active:
            return InvokeResponse(
                success=False,
                error="Agent not found or inactive",
                latency_ms=int((time.time() - start_time) * 1000),
                status_code=404,
            )

        # Allowlist: if config has non-empty allowed_agent_ids, agent must be in list
        if config and config.allowed_agent_ids and len(config.allowed_agent_ids) > 0:
            if agent.id not in config.allowed_agent_ids:
                return InvokeResponse(
                    success=False,
                    error="Agent not allowed for this integration",
                    latency_ms=int((time.time() - start_time) * 1000),
                    status_code=403,
                )

        # Quota check: monthly and/or daily
        if config:
            now = datetime.now(timezone.utc)
            if config.monthly_invocation_quota is not None:
                first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                count = await self.invocation_log_repository.count_invocations_for_integration(
                    integration_id, first_day, now
                )
                if count >= config.monthly_invocation_quota:
                    return InvokeResponse(
                        success=False,
                        error="Monthly invocation quota exceeded",
                        latency_ms=int((time.time() - start_time) * 1000),
                        status_code=429,
                    )
            if config.daily_invocation_quota is not None:
                start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
                count = await self.invocation_log_repository.count_invocations_for_integration(
                    integration_id, start_of_day, now
                )
                if count >= config.daily_invocation_quota:
                    return InvokeResponse(
                        success=False,
                        error="Daily invocation quota exceeded",
                        latency_ms=int((time.time() - start_time) * 1000),
                        status_code=429,
                    )

        # Find the capability
        capability = None
        for cap in agent.capabilities:
            if cap.capability_id == invoke_request.capability_id:
                capability = cap
                break
        
        if not capability:
            return InvokeResponse(
                success=False,
                error=f"Capability '{invoke_request.capability_id}' not found",
                latency_ms=int((time.time() - start_time) * 1000),
                status_code=404,
            )

        request_payload = invoke_request.input or {}

        timeout_sec = (
            float(config.request_timeout_seconds)
            if config
            else DEFAULT_REQUEST_TIMEOUT_SECONDS
        )
        max_retries = (config.max_retries or 0) if config else 0
        retry_backoff = (config.retry_backoff_seconds or 1) if config else 1

        response_status_code = 500
        response_data: Optional[dict] = None
        success = False
        error: Optional[str] = None

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout_sec) as client:
                    headers = {
                        "Content-Type": "application/json",
                        "User-Agent": "Intuno-Broker/1.0",
                        "X-Intuno-Capability-Id": invoke_request.capability_id,
                    }
                    if settings.AGENTS_API_KEY:
                        headers["X-API-Key"] = settings.AGENTS_API_KEY
                    response = await client.post(
                        agent.invoke_endpoint,
                        json=request_payload,
                        headers=headers,
                    )
                response_status_code = response.status_code

                if response.status_code == 200:
                    try:
                        response_data = response.json()
                        success = True
                        error = None
                    except Exception:
                        response_data = {"raw_response": response.text}
                        success = False
                        error = "Invalid JSON response from agent"
                else:
                    response_data = {"error": response.text}
                    success = False
                    error = f"Agent returned status {response.status_code}"

                # Retry only on timeout or 5xx if we have retries left
                if attempt < max_retries and (
                    response_status_code >= 500 or response_status_code == 408
                ):
                    await asyncio.sleep(retry_backoff * (attempt + 1))
                    continue
                break

            except httpx.TimeoutException:
                response_status_code = 408
                response_data = None
                success = False
                error = "Request timeout"
                if attempt < max_retries:
                    await asyncio.sleep(retry_backoff * (attempt + 1))
                    continue
                break
            except Exception as e:
                response_status_code = 500
                response_data = None
                success = False
                error = f"Request failed: {str(e)}"
                if attempt < max_retries:
                    await asyncio.sleep(retry_backoff * (attempt + 1))
                    continue
                break

        latency_ms = int((time.time() - start_time) * 1000)
        if response_data is None:
            response_data = {"error": error or "Unknown error"}

        # Log the invocation
        invocation_log = InvocationLog(
            caller_user_id=caller_user_id,
            target_agent_id=agent.id,
            capability_id=invoke_request.capability_id,
            request_payload=request_payload,
            response_payload=response_data,
            status_code=response_status_code,
            latency_ms=latency_ms,
            error_message=error,
            integration_id=integration_id,
            conversation_id=conv_id,
            message_id=msg_id,
        )
        await self.invocation_log_repository.create_invocation_log(invocation_log)

        return InvokeResponse(
            success=success,
            data=response_data if success else None,
            error=error,
            latency_ms=latency_ms,
            status_code=response_status_code,
            conversation_id=conv_id,
        )
