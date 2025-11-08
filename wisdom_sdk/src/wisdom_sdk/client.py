"""The main client for interacting with the Wisdom API."""

from typing import Any, Dict, List

import httpx
from pydantic import ValidationError
from src.wisdom_sdk.exceptions import (
    APIKeyMissingError,
    AuthenticationError,
    InvocationError,
    WisdomError,
)
from src.wisdom_sdk.models import Agent, InvokeResult


class WisdomClient:
    """
    The main client for interacting with the Wisdom Agent Network.
    """

    DEFAULT_BASE_URL = "http://localhost:8000"

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL):
        if not api_key:
            raise APIKeyMissingError()

        self.api_key = api_key
        self.base_url = base_url
        self._http_client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "Wisdom-SDK/0.1.0",
            },
        )

    async def discover(self, query: str, limit: int = 10) -> List[Agent]:
        """
        Discover agents using natural language.

        Args:
            query: A natural language description of the desired capability.
            limit: The maximum number of agents to return.

        Returns:
            A list of Agent objects matching the query.

        Raises:
            AuthenticationError: If the API key is invalid.
            WisdomError: For other API or network errors.
        """
        try:
            response = await self._http_client.get(
                "/registry/discover", params={"query": query, "limit": limit}
            )
            response.raise_for_status()

            # Pydantic will parse the list of dicts into a list of Agent models
            return [Agent(**agent_data) for agent_data in response.json()]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid API key.") from e
            else:
                raise WisdomError(f"API request failed: {e.response.text}") from e
        except (httpx.RequestError, ValidationError) as e:
            raise WisdomError(f"An unexpected error occurred: {e}") from e

    async def invoke(
        self,
        agent_id: str,
        capability_id: str,
        input_data: Dict[str, Any],
    ) -> InvokeResult:
        """
        Invoke an agent's capability.

        Args:
            agent_id: The ID of the agent to invoke.
            capability_id: The ID of the capability to use.
            input_data: A dictionary containing the input for the capability.

        Returns:
            An InvokeResult object with the outcome of the call.

        Raises:
            AuthenticationError: If the API key is invalid.
            InvocationError: If the invocation fails for a known reason (e.g., agent not found).
            WisdomError: For other API or network errors.
        """
        payload = {
            "agent_id": agent_id,
            "capability_id": capability_id,
            "input": input_data,
        }
        try:
            response = await self._http_client.post("/broker/invoke", json=payload)
            response.raise_for_status()

            result = InvokeResult(**response.json())
            if not result.success:
                raise InvocationError(
                    f"Invocation failed: {result.error} (Status: {result.status_code})"
                )

            return result

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid API key.") from e
            else:
                # Attempt to parse the error from the response if possible
                try:
                    error_details = e.response.json().get("detail", e.response.text)
                except Exception:
                    error_details = e.response.text
                raise WisdomError(f"API request failed: {error_details}") from e
        except (httpx.RequestError, ValidationError) as e:
            raise WisdomError(f"An unexpected error occurred: {e}") from e

    async def close(self):
        """
        Closes the underlying HTTP client.
        It's good practice to call this when you're done with the client,
        or use it as an async context manager.
        """
        await self._http_client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
