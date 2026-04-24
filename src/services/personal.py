"""Intuno Personal service — thin HTTP proxy to wisdom-agents.

wisdom owns user identity (JWT) and quota enforcement; wisdom-agents
owns entity state and runtime. This module is the bridge: given a
current user, it forwards to wisdom-agents with the shared API key +
``X-User-Id`` header so the other side can scope operations.

wisdom-agents is a private internal service. The frontend never talks
to it directly — all traffic flows through these wisdom routes.
"""

from typing import Any, Optional
from uuid import UUID

import httpx
from fastapi import HTTPException

from src.core.settings import settings
from src.exceptions import BadRequestException, ForbiddenException, NotFoundException


class AgentsUpstreamError(HTTPException):
    """Raised when wisdom-agents returns 5xx / 401-from-bad-config / is unreachable.

    Inherits from ``HTTPException`` so FastAPI surfaces it as an HTTP
    response instead of a 500 with a raw traceback.
    """

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(status_code=status_code, detail=message)


class PersonalAgentsClient:
    """Typed wrapper over the wisdom-agents HTTP API.

    One instance per request via a FastAPI dependency. The underlying
    ``httpx.AsyncClient`` is created and closed with the request scope
    to keep connection hygiene simple. For high-QPS endpoints we'd
    hoist to a shared pool; the Personal surface is low-traffic.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._base_url = (base_url or settings.INTUNO_AGENTS_BASE_URL).rstrip("/")
        self._api_key = api_key or settings.INTUNO_AGENTS_API_KEY
        self._timeout = timeout if timeout is not None else settings.INTUNO_AGENTS_TIMEOUT_SECONDS

    def _headers(self, user_id: UUID, extra: Optional[dict] = None) -> dict:
        headers = {
            "X-API-Key": self._api_key,
            "X-User-Id": str(user_id),
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    # ─────────────── low-level request wrapper ──────────────────

    async def _request(
        self,
        method: str,
        path: str,
        user_id: UUID,
        *,
        json: Optional[Any] = None,
        params: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        """Issue one HTTP call. Raises ``AgentsUpstreamError`` on 5xx / network fail."""
        url = f"{self._base_url}{path}"
        timeout_s = timeout if timeout is not None else self._timeout
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                response = await client.request(
                    method,
                    url,
                    headers=self._headers(user_id),
                    json=json,
                    params=params,
                )
        except httpx.HTTPError as exc:
            raise AgentsUpstreamError(
                f"wisdom-agents unreachable: {exc}", status_code=502
            ) from exc

        # 401 from wisdom-agents means our shared API key is wrong — a server
        # misconfig, not a user-facing auth problem. Surface as 502 with a
        # clean message so the traceback doesn't leak.
        if response.status_code == 401:
            raise AgentsUpstreamError(
                "wisdom-agents rejected the shared API key — check "
                "INTUNO_AGENTS_API_KEY matches AGENTS_API_KEY on wisdom-agents.",
                status_code=502,
            )

        if response.status_code >= 500:
            raise AgentsUpstreamError(
                f"wisdom-agents {response.status_code}: {response.text[:200]}",
                status_code=response.status_code,
            )

        return response

    # ─────────────── entity CRUD ────────────────────────────────

    async def list_entities(self, user_id: UUID) -> list[dict]:
        resp = await self._request("GET", "/entities", user_id)
        if resp.status_code == 403:
            raise ForbiddenException("forbidden")
        resp.raise_for_status()
        return resp.json()

    async def create_entity(self, user_id: UUID, payload: dict) -> dict:
        resp = await self._request("POST", "/entities", user_id, json=payload)
        if resp.status_code == 409:
            raise BadRequestException(resp.json().get("detail", "Entity name taken"))
        if resp.status_code in (400, 422):
            raise BadRequestException(resp.json().get("detail", "Validation failed"))
        resp.raise_for_status()
        return resp.json()

    async def get_entity(self, user_id: UUID, name: str) -> dict:
        resp = await self._request("GET", f"/entities/{name}", user_id)
        if resp.status_code == 404:
            raise NotFoundException(f"Entity '{name}' not found")
        if resp.status_code == 403:
            raise ForbiddenException("Not your entity")
        resp.raise_for_status()
        return resp.json()

    async def update_entity(self, user_id: UUID, name: str, patch: dict) -> dict:
        resp = await self._request("PATCH", f"/entities/{name}", user_id, json=patch)
        if resp.status_code == 404:
            raise NotFoundException(f"Entity '{name}' not found")
        if resp.status_code in (400, 422):
            raise BadRequestException(resp.json().get("detail", "Update rejected"))
        resp.raise_for_status()
        return resp.json()

    async def delete_entity(self, user_id: UUID, name: str) -> None:
        resp = await self._request("DELETE", f"/entities/{name}", user_id)
        if resp.status_code == 404:
            raise NotFoundException(f"Entity '{name}' not found")
        if resp.status_code == 403:
            raise ForbiddenException("Not your entity")
        resp.raise_for_status()

    async def pause_entity(self, user_id: UUID, name: str) -> dict:
        resp = await self._request("POST", f"/entities/{name}/pause", user_id)
        if resp.status_code == 404:
            raise NotFoundException(f"Entity '{name}' not found")
        if resp.status_code == 403:
            raise ForbiddenException("Not your entity")
        resp.raise_for_status()
        return resp.json()

    async def resume_entity(self, user_id: UUID, name: str) -> dict:
        resp = await self._request("POST", f"/entities/{name}/resume", user_id)
        if resp.status_code == 404:
            raise NotFoundException(f"Entity '{name}' not found")
        if resp.status_code == 403:
            raise ForbiddenException("Not your entity")
        resp.raise_for_status()
        return resp.json()

    # ─────────────── chat ───────────────────────────────────────

    async def send_chat_message(self, user_id: UUID, name: str, content: str) -> dict:
        resp = await self._request(
            "POST",
            f"/entities/{name}/chat",
            user_id,
            json={"content": content},
            timeout=settings.INTUNO_AGENTS_CHAT_TIMEOUT_SECONDS,
        )
        if resp.status_code == 404:
            raise NotFoundException(f"Entity '{name}' not found")
        if resp.status_code == 403:
            raise ForbiddenException("Not your entity")
        resp.raise_for_status()
        return resp.json()

    async def list_chat_history(
        self,
        user_id: UUID,
        name: str,
        limit: int = 50,
        before: Optional[str] = None,
    ) -> list[dict]:
        params: dict = {"limit": limit}
        if before:
            params["before"] = before
        resp = await self._request(
            "GET", f"/entities/{name}/chat", user_id, params=params
        )
        if resp.status_code == 404:
            raise NotFoundException(f"Entity '{name}' not found")
        if resp.status_code == 403:
            raise ForbiddenException("Not your entity")
        resp.raise_for_status()
        return resp.json()


def get_personal_client() -> PersonalAgentsClient:
    """FastAPI dependency factory."""
    return PersonalAgentsClient()
