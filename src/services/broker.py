"""Broker domain service: agent invocation with logging, quotas, and timeouts."""

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
from fastapi import Depends

import json

from src.core.url_validation import validate_invoke_endpoint
from src.models.conversation import Conversation
from src.repositories.brand import BrandRepository
from src.models.invocation_log import InvocationLog
from src.models.message import Message
from src.repositories.broker import BrokerConfigRepository
from src.repositories.conversation import ConversationRepository
from src.repositories.invocation_log import InvocationLogRepository
from src.repositories.message import MessageRepository
from src.repositories.registry import RegistryRepository
from src.schemas.broker import InvokeRequest, InvokeResponse
from src.schemas.registry import parse_auth_type_stored
from src.core.settings import settings
from src.utilities.brand_agent_llm import generate_brand_agent_response

DEFAULT_REQUEST_TIMEOUT_SECONDS = 30

_TEXT_KEYS = ("message", "query", "text", "content", "prompt", "input")


def _extract_text(payload: dict) -> str:
    """Best-effort extraction of a human-readable string from a dict payload."""
    for key in _TEXT_KEYS:
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return json.dumps(payload, default=str)


class BrokerService:
    """Service for brokering agent invocations (quotas, timeouts, allowlist)."""

    def __init__(
        self,
        invocation_log_repository: InvocationLogRepository = Depends(),
        broker_config_repository: BrokerConfigRepository = Depends(),
        registry_repository: RegistryRepository = Depends(),
        conversation_repository: ConversationRepository = Depends(),
        message_repository: MessageRepository = Depends(),
        brand_repository: BrandRepository = Depends(),
    ):
        self.invocation_log_repository = invocation_log_repository
        self.broker_config_repository = broker_config_repository
        self.registry_repository = registry_repository
        self.conversation_repository = conversation_repository
        self.message_repository = message_repository
        self.brand_repository = brand_repository

    async def invoke_agent(
        self,
        invoke_request: InvokeRequest,
        caller_user_id: UUID,
        integration_id: Optional[UUID] = None,
        conversation_id: Optional[UUID] = None,
        message_id: Optional[UUID] = None,
    ) -> InvokeResponse:
        """Invoke an agent through the broker.

        :param invoke_request: InvokeRequest
        :param caller_user_id: UUID
        :param integration_id: Optional integration (from API key)
        :param conversation_id: Optional conversation
        :param message_id: Optional message
        :return: InvokeResponse
        """
        start_time = time.time()

        # Load effective broker config
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
            # Create conversation for audit trail
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

        # Allowlist check
        if config and config.allowed_agent_ids and len(config.allowed_agent_ids) > 0:
            if agent.id not in config.allowed_agent_ids:
                return InvokeResponse(
                    success=False,
                    error="Agent not allowed for this integration",
                    latency_ms=int((time.time() - start_time) * 1000),
                    status_code=403,
                )

        # Quota check
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

        request_payload = invoke_request.input or {}

        # Brand agent: invoke via LLM internally
        if getattr(agent, "is_brand_agent", False) and agent.brand_id:
            brand = await self.brand_repository.get_by_id(agent.brand_id)
            if brand:
                if msg_id is None and conv_id is not None:
                    user_message = await self.message_repository.create(
                        Message(
                            conversation_id=conv_id,
                            role="user",
                            content=_extract_text(request_payload),
                            metadata_=request_payload,
                        )
                    )
                    msg_id = user_message.id
                try:
                    response_data = await generate_brand_agent_response(brand, request_payload)
                except Exception as e:
                    response_data = {"error": str(e)}
                    success = False
                else:
                    success = True
                latency_ms = int((time.time() - start_time) * 1000)
                if success and conv_id is not None and response_data:
                    await self.message_repository.create(
                        Message(
                            conversation_id=conv_id,
                            role="assistant",
                            content=_extract_text(response_data),
                            metadata_=response_data,
                        )
                    )
                invocation_log = InvocationLog(
                    caller_user_id=caller_user_id,
                    target_agent_id=agent.id,
                    request_payload=request_payload,
                    response_payload=response_data,
                    status_code=200 if success else 500,
                    latency_ms=latency_ms,
                    error_message=None if success else response_data.get("error"),
                    integration_id=integration_id,
                    conversation_id=conv_id,
                    message_id=msg_id,
                )
                await self.invocation_log_repository.create_invocation_log(invocation_log)
                return InvokeResponse(
                    success=success,
                    data=response_data if success else None,
                    error=None if success else response_data.get("error", "Brand agent error"),
                    latency_ms=latency_ms,
                    status_code=200 if success else 500,
                    conversation_id=conv_id,
                )

        # Persist user message
        if msg_id is None and conv_id is not None:
            user_message = await self.message_repository.create(
                Message(
                    conversation_id=conv_id,
                    role="user",
                    content=_extract_text(request_payload),
                    metadata_=request_payload,
                )
            )
            msg_id = user_message.id

        # SSRF protection
        try:
            allowed = [h.strip() for h in settings.INVOKE_ENDPOINT_ALLOWED_HOSTS.split(",") if h.strip()]
            validate_invoke_endpoint(agent.invoke_endpoint, allowed_hosts=allowed if allowed else None)
        except ValueError as e:
            return InvokeResponse(
                success=False,
                error=str(e),
                latency_ms=int((time.time() - start_time) * 1000),
                status_code=400,
            )

        timeout_sec = (
            float(config.request_timeout_seconds) if config else DEFAULT_REQUEST_TIMEOUT_SECONDS
        )
        max_retries = (config.max_retries or 0) if config else 0
        retry_backoff = (config.retry_backoff_seconds or 1) if config else 1

        response_status_code = 500
        response_data: Optional[dict] = None
        success = False
        error: Optional[str] = None

        # Resolve auth from agent.auth_type + stored credentials
        auth_type = (agent.auth_type or "public").lower()
        cred_type = "api_key" if auth_type in ("api_key", "public") else "bearer_token"
        cred = await self.registry_repository.get_agent_credential(agent.id, cred_type)
        cred_value: Optional[str] = None
        if cred:
            try:
                from src.core.credential_crypto import decrypt_credential
                cred_value = decrypt_credential(cred.encrypted_value)
            except ValueError:
                cred_value = None

        if auth_type in ("api_key", "bearer_token") and not cred_value:
            return InvokeResponse(
                success=False,
                error="Agent requires credentials; set via POST /registry/agents/{uuid}/credentials",
                latency_ms=int((time.time() - start_time) * 1000),
                status_code=503,
            )

        # Determine auth header name and value
        auth_defaults = {
            "api_key": {"header": "X-API-Key", "scheme": ""},
            "bearer_token": {"header": "Authorization", "scheme": "Bearer"},
            "public": {"header": "X-API-Key", "scheme": ""},
        }
        defaults = auth_defaults.get(auth_type, auth_defaults["public"])
        header_name = (cred.auth_header if cred and cred.auth_header else None) or defaults["header"]
        scheme = (cred.auth_scheme if cred and cred.auth_scheme is not None else None) or defaults["scheme"]
        header_value = f"{scheme} {cred_value}".strip() if (cred_value and scheme) else (cred_value or "")

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout_sec) as client:
                    headers = {
                        "Content-Type": "application/json",
                        "User-Agent": "Intuno-Broker/1.0",
                    }
                    if header_value:
                        headers[header_name] = header_value
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

        # Persist assistant message on success
        if success and conv_id is not None and response_data:
            await self.message_repository.create(
                Message(
                    conversation_id=conv_id,
                    role="assistant",
                    content=_extract_text(response_data),
                    metadata_=response_data,
                )
            )

        # Log invocation
        invocation_log = InvocationLog(
            caller_user_id=caller_user_id,
            target_agent_id=agent.id,
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
