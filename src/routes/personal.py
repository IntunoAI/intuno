"""/personal/entities — Intuno Personal proxy routes.

Frontend users authenticate with wisdom (JWT) and hit these routes;
wisdom forwards to the private wisdom-agents service with the shared
X-API-Key + X-User-Id header. This is the only public entry point to
Intuno Personal.

See the [personal-proxy] ticket and wisdom-agents [personal-trust]
for the bridge design.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from src.core.auth import get_current_user_from_token
from src.exceptions import BadRequestException
from src.models.auth import User
from src.services.personal import PersonalAgentsClient, get_personal_client

router = APIRouter(prefix="/personal", tags=["Personal"])


# ── Local request/response models ──────────────────────────────────
#
# We keep these loose (``Any`` on the entity body) because the full
# schema lives in wisdom-agents. The proxy's job is to forward, not
# duplicate the 30-field schema here. Changes to wisdom-agents'
# EntityConfig schema flow through without needing wisdom updates.


class ChatSendBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=65536)


class ChatSendResponse(BaseModel):
    message_id: Optional[str] = None
    reply: str


# ── Entity CRUD ────────────────────────────────────────────────────


@router.post("/entities", status_code=status.HTTP_201_CREATED)
async def create_entity(
    body: dict[str, Any],
    current_user: User = Depends(get_current_user_from_token),
    client: PersonalAgentsClient = Depends(get_personal_client),
) -> dict[str, Any]:
    """Create a new entity for the authenticated user.

    Enforces the Free-tier quota before forwarding. Body shape matches
    wisdom-agents' ``EntityConfigCreate``.
    """
    from src.core.settings import settings

    # Quota: count user's existing entities.
    existing = await client.list_entities(current_user.id)
    if len(existing) >= settings.PERSONAL_FREE_TIER_ENTITY_CAP:
        raise BadRequestException(
            f"Entity cap reached ({settings.PERSONAL_FREE_TIER_ENTITY_CAP}). "
            "Upgrade your plan to create more.",
        )

    return await client.create_entity(current_user.id, body)


@router.get("/entities")
async def list_entities(
    current_user: User = Depends(get_current_user_from_token),
    client: PersonalAgentsClient = Depends(get_personal_client),
) -> list[dict[str, Any]]:
    """List all entities owned by the authenticated user."""
    return await client.list_entities(current_user.id)


@router.get("/entities/{name}")
async def get_entity(
    name: str,
    current_user: User = Depends(get_current_user_from_token),
    client: PersonalAgentsClient = Depends(get_personal_client),
) -> dict[str, Any]:
    return await client.get_entity(current_user.id, name)


@router.patch("/entities/{name}")
async def update_entity(
    name: str,
    patch: dict[str, Any],
    current_user: User = Depends(get_current_user_from_token),
    client: PersonalAgentsClient = Depends(get_personal_client),
) -> dict[str, Any]:
    if not patch:
        raise BadRequestException("No fields to update")
    return await client.update_entity(current_user.id, name, patch)


@router.delete("/entities/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity(
    name: str,
    current_user: User = Depends(get_current_user_from_token),
    client: PersonalAgentsClient = Depends(get_personal_client),
) -> None:
    await client.delete_entity(current_user.id, name)


@router.post("/entities/{name}/pause")
async def pause_entity(
    name: str,
    current_user: User = Depends(get_current_user_from_token),
    client: PersonalAgentsClient = Depends(get_personal_client),
) -> dict[str, Any]:
    return await client.pause_entity(current_user.id, name)


@router.post("/entities/{name}/resume")
async def resume_entity(
    name: str,
    current_user: User = Depends(get_current_user_from_token),
    client: PersonalAgentsClient = Depends(get_personal_client),
) -> dict[str, Any]:
    return await client.resume_entity(current_user.id, name)


# ── Chat ───────────────────────────────────────────────────────────


@router.post(
    "/entities/{name}/messages",
    response_model=ChatSendResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    name: str,
    body: ChatSendBody,
    current_user: User = Depends(get_current_user_from_token),
    client: PersonalAgentsClient = Depends(get_personal_client),
) -> ChatSendResponse:
    """Send a chat message to the user's entity. Blocks on the entity reply."""
    result = await client.send_chat_message(current_user.id, name, body.content)
    return ChatSendResponse(**result)


@router.get("/entities/{name}/messages")
async def list_messages(
    name: str,
    limit: int = Query(default=50, ge=1, le=200),
    before: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user_from_token),
    client: PersonalAgentsClient = Depends(get_personal_client),
) -> list[dict[str, Any]]:
    """Paginated history for the user's chat with this entity."""
    return await client.list_chat_history(current_user.id, name, limit=limit, before=before)
