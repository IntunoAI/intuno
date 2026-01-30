"""Configurable agent chat routes: POST /{agent_name} (chat), optional POST "" (create config)."""

from fastapi import APIRouter, Depends, status

from agents.core.auth import require_api_key
from agents.schemas.agent_config import (
    AgentChatRequest,
    AgentChatResponse,
    AgentConfigCreate,
    AgentConfigResponse,
)
from agents.services.agent_config import ConfigurableAgentService

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.post(
    "/{agent_name}",
    response_model=AgentChatResponse,
)
async def chat_with_agent(
    agent_name: str,
    data: AgentChatRequest,
    _: None = Depends(require_api_key),
    configurable_agent_service: ConfigurableAgentService = Depends(),
) -> AgentChatResponse:
    """
    Chat with a configurable agent by name. Loads agent config, builds system prompt, calls OpenAI, returns content.
    :param agent_name: Agent config name
    :param data: AgentChatRequest (messages)
    :param configurable_agent_service: ConfigurableAgentService
    :return: AgentChatResponse (content)
    """
    content = await configurable_agent_service.chat(agent_name, data.messages)
    return AgentChatResponse(content=content)


@router.post(
    "",
    response_model=AgentConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_config(
    data: AgentConfigCreate,
    _: None = Depends(require_api_key),
    configurable_agent_service: ConfigurableAgentService = Depends(),
) -> AgentConfigResponse:
    """
    Create a new agent config (name, guardrail, description, purpose).
    :param data: AgentConfigCreate
    :param configurable_agent_service: ConfigurableAgentService
    :return: AgentConfigResponse
    """
    agent_config = await configurable_agent_service.create(data)
    return AgentConfigResponse.model_validate(agent_config)
