"""Broker domain service."""

import time
from uuid import UUID

import httpx

from src.models.broker import InvocationLog
from src.repositories.broker import BrokerRepository
from src.repositories.registry import RegistryRepository
from src.schemas.broker import InvokeRequest, InvokeResponse
from fastapi import Depends


class BrokerService:
    """Service for brokering agent invocations."""

    def __init__(
        self,
        broker_repository: BrokerRepository = Depends(),
        registry_repository: RegistryRepository = Depends(),
    ):
        self.broker_repository = broker_repository
        self.registry_repository = registry_repository

    async def invoke_agent(
        self,
        invoke_request: InvokeRequest,
        caller_user_id: UUID,
    ) -> InvokeResponse:
        """
        Invoke an agent capability through the broker.
        :param invoke_request: InvokeRequest
        :param caller_user_id: UUID
        :return: InvokeResponse
        """
        start_time = time.time()
        
        # Get the agent
        agent = await self.registry_repository.get_agent_by_agent_id(invoke_request.agent_id)
        if not agent or not agent.is_active:
            return InvokeResponse(
                success=False,
                error="Agent not found or inactive",
                latency_ms=int((time.time() - start_time) * 1000),
                status_code=404,
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

        # Prepare the request payload
        request_payload = {
            "capability_id": invoke_request.capability_id,
            "input": invoke_request.input,
        }

        # Make the HTTP call to the agent
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    agent.invoke_endpoint,
                    json=request_payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "Intuno-Broker/1.0",
                    }
                )
                
                latency_ms = int((time.time() - start_time) * 1000)
                
                # Parse response
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

        except httpx.TimeoutException:
            latency_ms = int((time.time() - start_time) * 1000)
            return InvokeResponse(
                success=False,
                error="Request timeout",
                latency_ms=latency_ms,
                status_code=408,
            )
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return InvokeResponse(
                success=False,
                error=f"Request failed: {str(e)}",
                latency_ms=latency_ms,
                status_code=500,
            )

        # Log the invocation
        invocation_log = InvocationLog(
            caller_user_id=caller_user_id,
            target_agent_id=agent.id,
            capability_id=invoke_request.capability_id,
            request_payload=request_payload,
            response_payload=response_data,
            status_code=response.status_code if 'response' in locals() else 500,
            latency_ms=latency_ms,
            error_message=error,
        )
        await self.broker_repository.create_invocation_log(invocation_log)

        return InvokeResponse(
            success=success,
            data=response_data if success else None,
            error=error,
            latency_ms=latency_ms,
            status_code=response.status_code if 'response' in locals() else 500,
        )

    async def get_invocation_logs(
        self,
        user_id: UUID,
        limit: int = 50,
    ) -> list[InvocationLog]:
        """
        Get invocation logs for a user.
        :param user_id: UUID
        :param limit: int
        :return: List[InvocationLog]
        """
        return await self.broker_repository.get_invocation_logs_by_user_id(user_id, limit)

    async def get_agent_invocation_logs(
        self,
        agent_id: UUID,
        limit: int = 50,
    ) -> list[InvocationLog]:
        """
        Get invocation logs for an agent.
        :param agent_id: UUID
        :param limit: int
        :return: List[InvocationLog]
        """
        return await self.broker_repository.get_invocation_logs_by_agent_id(agent_id, limit)