"""Broker domain service: agent invocation with logging, quotas, and timeouts."""

import asyncio
import json
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import httpx
from fastapi import Depends

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
        self._http_client: Optional[httpx.AsyncClient] = None
        self._request_id: Optional[str] = None

    def set_http_client(self, client: httpx.AsyncClient) -> None:
        """Inject the shared HTTP client (set by the route layer)."""
        self._http_client = client

    def set_request_id(self, request_id: str) -> None:
        """Set the request ID for distributed tracing."""
        self._request_id = request_id

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

        # Safety check: reject if platform is in emergency halt
        from src.services.safety import check_platform_halt
        await check_platform_halt()

        # Resolve conversation_id and message_id from request if not passed
        conv_id = conversation_id or invoke_request.conversation_id
        msg_id = message_id or invoke_request.message_id

        # Batch independent lookups: config + agent + conversation (if provided)
        config_coro = self.broker_config_repository.get_effective_config(integration_id)
        agent_coro = self.registry_repository.get_agent_by_agent_id(
            invoke_request.agent_id
        )

        if conv_id is not None:
            conv_coro = self.conversation_repository.get_by_id(conv_id)
            config, agent, conversation = await asyncio.gather(
                config_coro,
                agent_coro,
                conv_coro,
            )
        else:
            config, agent = await asyncio.gather(config_coro, agent_coro)
            conversation = None

        # Validate conversation ownership
        if conv_id is not None:
            if not conversation or conversation.user_id != caller_user_id:
                return InvokeResponse(
                    success=False,
                    error="Conversation not found or access denied",
                    latency_ms=int((time.time() - start_time) * 1000),
                    status_code=404,
                )
            if (
                integration_id is not None
                and conversation.integration_id != integration_id
            ):
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

        # Agent already fetched above via asyncio.gather
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

        # Quota check (Redis counters with DB fallback)
        if config:
            from src.core.redis_client import quota_increment

            now = datetime.now(timezone.utc)
            if config.monthly_invocation_quota is not None:
                month_key = f"quota:{integration_id}:monthly:{now.strftime('%Y-%m')}"
                # Remaining seconds until end of month
                next_month = (now.replace(day=28) + timedelta(days=4)).replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )
                month_ttl = max(int((next_month - now).total_seconds()), 1)
                count = await quota_increment(month_key, month_ttl)
                if count is None:
                    # Redis unavailable — fall back to DB scan
                    first_day = now.replace(
                        day=1, hour=0, minute=0, second=0, microsecond=0
                    )
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
                day_key = f"quota:{integration_id}:daily:{now.strftime('%Y-%m-%d')}"
                day_ttl = max(
                    86400 - (now.hour * 3600 + now.minute * 60 + now.second), 1
                )
                count = await quota_increment(day_key, day_ttl)
                if count is None:
                    # Redis unavailable — fall back to DB scan
                    start_of_day = now.replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
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

        # Billing: pre-flight balance check for priced agents
        _pricing_enabled = getattr(agent, "pricing_enabled", False)
        _agent_price_raw = getattr(agent, "base_price", None)
        _agent_price = (
            int(_agent_price_raw) if (_agent_price_raw and _agent_price_raw > 0) else 0
        )

        if _pricing_enabled and _agent_price > 0:
            from src.economy.repositories.wallets import WalletRepository as _WR

            _wr = _WR(self.registry_repository.session)
            _caller_wallet = await _wr.get_by_user_id(caller_user_id)
            if not _caller_wallet or _caller_wallet.balance < _agent_price:
                return InvokeResponse(
                    success=False,
                    error="Insufficient credits",
                    latency_ms=int((time.time() - start_time) * 1000),
                    status_code=402,
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
                    response_data = await generate_brand_agent_response(
                        brand, request_payload
                    )
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
                await self.invocation_log_repository.create_invocation_log(
                    invocation_log
                )
                credits_charged_brand = None
                if success and _pricing_enabled and _agent_price > 0:
                    credits_charged_brand = await self._settle_credits(
                        caller_user_id, agent, _agent_price
                    )
                return InvokeResponse(
                    success=success,
                    data=response_data if success else None,
                    error=None
                    if success
                    else response_data.get("error", "Brand agent error"),
                    latency_ms=latency_ms,
                    status_code=200 if success else 500,
                    conversation_id=conv_id,
                    credits_charged=credits_charged_brand,
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
            allowed = [
                h.strip()
                for h in settings.INVOKE_ENDPOINT_ALLOWED_HOSTS.split(",")
                if h.strip()
            ]
            validate_invoke_endpoint(
                agent.invoke_endpoint, allowed_hosts=allowed if allowed else None
            )
        except ValueError as e:
            return InvokeResponse(
                success=False,
                error=str(e),
                latency_ms=int((time.time() - start_time) * 1000),
                status_code=400,
            )

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

        # Resolve auth from agent.auth_type + stored credentials
        auth_type = (agent.auth_type or "public").lower()
        cred: Optional[object] = None
        cred_value: Optional[str] = None
        if auth_type in ("api_key", "bearer_token"):
            cred = await self.registry_repository.get_agent_credential(
                agent.id, auth_type
            )
            if cred:
                try:
                    from src.core.credential_crypto import decrypt_credential

                    cred_value = decrypt_credential(cred.encrypted_value)
                except ValueError:
                    cred_value = None

            if not cred_value:
                return InvokeResponse(
                    success=False,
                    error="Agent requires credentials; set via POST /registry/agents/{uuid}/credentials",
                    latency_ms=int((time.time() - start_time) * 1000),
                    status_code=503,
                )

        # Determine auth header name and value (public agents send no auth header)
        auth_defaults = {
            "api_key": {"header": "X-API-Key", "scheme": ""},
            "bearer_token": {"header": "Authorization", "scheme": "Bearer"},
        }
        defaults = auth_defaults.get(auth_type, {})
        header_name = (
            cred.auth_header if cred and cred.auth_header else None
        ) or defaults.get("header", "")
        scheme = (
            cred.auth_scheme if cred and cred.auth_scheme is not None else None
        ) or defaults.get("scheme", "")
        header_value = (
            f"{scheme} {cred_value}".strip()
            if (cred_value and scheme)
            else (cred_value or "")
        )

        # Use shared HTTP client when available; fall back to one-shot client
        client = self._http_client
        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(timeout=timeout_sec)

        try:
            for attempt in range(max_retries + 1):
                try:
                    headers = {
                        "Content-Type": "application/json",
                        "User-Agent": "Intuno-Broker/1.0",
                    }
                    if self._request_id:
                        headers["X-Request-ID"] = self._request_id
                    if header_value:
                        headers[header_name] = header_value
                    response = await client.post(
                        agent.invoke_endpoint,
                        json=request_payload,
                        headers=headers,
                        timeout=timeout_sec,
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
                        jitter = retry_backoff * (attempt + 1) * (0.5 + random.random())
                        await asyncio.sleep(jitter)
                        continue
                    break

                except httpx.TimeoutException:
                    response_status_code = 408
                    response_data = None
                    success = False
                    error = "Request timeout"
                    if attempt < max_retries:
                        jitter = retry_backoff * (attempt + 1) * (0.5 + random.random())
                        await asyncio.sleep(jitter)
                        continue
                    break
                except Exception as e:
                    response_status_code = 500
                    response_data = None
                    success = False
                    error = f"Request failed: {str(e)}"
                    if attempt < max_retries:
                        jitter = retry_backoff * (attempt + 1) * (0.5 + random.random())
                        await asyncio.sleep(jitter)
                        continue
                    break
        finally:
            if owns_client:
                await client.aclose()

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

        # Economy: settle credits after successful paid invocation
        credits_charged = None
        if success and _pricing_enabled and _agent_price > 0:
            credits_charged = await self._settle_credits(
                caller_user_id, agent, _agent_price
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
            credits_charged=credits_charged,
        )

    async def invoke_agent_stream(
        self,
        invoke_request: InvokeRequest,
        caller_user_id: UUID,
        integration_id: Optional[UUID] = None,
        conversation_id: Optional[UUID] = None,
        message_id: Optional[UUID] = None,
    ):
        """Invoke an agent with SSE streaming support.

        If the target agent supports streaming, proxies the SSE stream as an
        async generator of dicts. Otherwise, falls back to a normal invocation
        and returns an InvokeResponse.
        """
        # Safety check: reject if platform is in emergency halt
        from src.services.safety import check_platform_halt
        await check_platform_halt()

        # Resolve agent to check streaming support
        agent = await self.registry_repository.get_agent_by_agent_id(
            invoke_request.agent_id
        )

        # Check agent exists and is active (fixes gap where streaming path skipped this)
        if not agent or not agent.is_active:
            return InvokeResponse(
                success=False,
                error="Agent not found or inactive",
                latency_ms=0,
                status_code=404,
            )

        supports_streaming = getattr(agent, "supports_streaming", False)

        if not supports_streaming:
            # Fall back to normal invocation
            return await self.invoke_agent(
                invoke_request,
                caller_user_id,
                integration_id,
                conversation_id,
                message_id,
            )

        # Stream from the agent's endpoint
        return self._stream_from_agent(
            agent,
            invoke_request,
            caller_user_id,
            integration_id,
            conversation_id,
            message_id,
        )

    async def _stream_from_agent(
        self,
        agent,
        invoke_request: InvokeRequest,
        caller_user_id: UUID,
        integration_id: Optional[UUID],
        conversation_id: Optional[UUID],
        message_id: Optional[UUID],
    ):
        """Proxy SSE stream from a streaming-capable agent."""
        import time as _time

        start_time = _time.time()
        request_payload = invoke_request.input or {}

        # Resolve auth (same logic as invoke_agent)
        auth_type = (agent.auth_type or "public").lower()
        header_name, header_value = "", ""
        if auth_type in ("api_key", "bearer_token"):
            cred = await self.registry_repository.get_agent_credential(
                agent.id, auth_type
            )
            if cred:
                from src.core.credential_crypto import decrypt_credential

                try:
                    cred_value = decrypt_credential(cred.encrypted_value)
                except ValueError:
                    cred_value = None
                if cred_value:
                    defaults = {
                        "api_key": {"header": "X-API-Key", "scheme": ""},
                        "bearer_token": {"header": "Authorization", "scheme": "Bearer"},
                    }
                    d = defaults.get(auth_type, {})
                    header_name = cred.auth_header or d.get("header", "")
                    scheme = (
                        cred.auth_scheme if cred.auth_scheme is not None else None
                    ) or d.get("scheme", "")
                    header_value = (
                        f"{scheme} {cred_value}".strip() if scheme else cred_value
                    )

        config = await self.broker_config_repository.get_effective_config(
            integration_id
        )
        timeout_sec = (
            float(config.request_timeout_seconds)
            if config
            else DEFAULT_REQUEST_TIMEOUT_SECONDS
        )

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Intuno-Broker/1.0",
            "Accept": "text/event-stream",
        }
        if header_value:
            headers[header_name] = header_value

        client = self._http_client or httpx.AsyncClient(timeout=timeout_sec)
        owns_client = self._http_client is None

        try:
            async with client.stream(
                "POST",
                agent.invoke_endpoint,
                json=request_payload,
                headers=headers,
                timeout=timeout_sec,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data:
                            try:
                                yield json.loads(data)
                            except json.JSONDecodeError:
                                yield {"text": data}
                    elif line.strip() == "":
                        continue
        finally:
            if owns_client:
                await client.aclose()

    async def _settle_credits(
        self,
        caller_user_id: UUID,
        agent,
        price: int,
    ) -> int | None:
        """Settle credits from caller to agent owner after a paid invocation.

        Debits the caller's **user wallet** and credits the invoked
        **agent wallet** (auto-created if it doesn't exist yet).

        Returns the number of credits charged, or None if settlement failed.
        """
        import logging
        import uuid as _uuid

        from src.economy.models.wallet import Transaction, Wallet
        from src.economy.repositories.wallets import WalletRepository

        logger = logging.getLogger(__name__)

        try:
            session = self.registry_repository.session
            wallet_repo = WalletRepository(session)

            # Debit the caller's user wallet
            caller_wallet = await wallet_repo.get_by_user_id(caller_user_id)
            if not caller_wallet:
                logger.warning(
                    "No user wallet for caller %s — skipping settlement",
                    caller_user_id,
                )
                return None

            debited = await wallet_repo.atomic_debit(caller_wallet.id, price)
            if not debited:
                logger.warning(
                    "Insufficient balance for caller %s (need %d)",
                    caller_user_id,
                    price,
                )
                return None

            reference_id = _uuid.uuid4()

            await wallet_repo.create_transaction(
                Transaction(
                    wallet_id=caller_wallet.id,
                    amount=-price,
                    tx_type="invocation_debit",
                    reference_id=reference_id,
                    description=f"Payment for {agent.agent_id} invocation",
                )
            )

            # Credit the agent's own wallet (auto-create if needed)
            agent_wallet = await wallet_repo.get_by_agent_id(agent.id)
            if not agent_wallet:
                agent_wallet = await wallet_repo.create(
                    Wallet(agent_id=agent.id, wallet_type="agent", balance=0)
                )

            await wallet_repo.atomic_credit(agent_wallet.id, price)
            await wallet_repo.create_transaction(
                Transaction(
                    wallet_id=agent_wallet.id,
                    amount=price,
                    tx_type="invocation_credit",
                    reference_id=reference_id,
                    description=f"Revenue from {agent.agent_id} invocation",
                )
            )

            return price
        except Exception:
            logger.exception("Settlement failed for agent %s", agent.agent_id)
            return None
