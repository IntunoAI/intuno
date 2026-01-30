"""Configurable agent chat service: load config, call OpenAI, return content."""

from typing import List

from fastapi import Depends
from openai import AsyncOpenAI

from agents.core.settings import settings
from agents.exceptions import NotFoundException
from agents.models.agent_config import AgentConfig
from agents.repositories.agent_config import AgentConfigRepository
from agents.schemas.agent_config import AgentConfigCreate, ChatMessage


class ConfigurableAgentService:
    """Service for chat completion using agent config (no tools, pure text)."""

    def __init__(
        self,
        agent_config_repository: AgentConfigRepository = Depends(),
    ):
        self.agent_config_repository = agent_config_repository
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        """Lazy OpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    async def chat(self, agent_name: str, messages: List[ChatMessage]) -> str:
        """
        Load agent config by name, build system prompt, call OpenAI chat completions, return content.
        :param agent_name: Agent config name
        :param messages: Conversation messages (role + content)
        :return: Assistant text content
        :raises NotFoundException: If agent config not found
        """
        config = await self.agent_config_repository.get_by_name(agent_name)
        if not config:
            raise NotFoundException("Agent config")

        system_content = _build_system_message(config)
        request_messages: List[dict] = [
            {"role": "system", "content": system_content},
        ]
        for m in messages:
            request_messages.append({"role": m.role, "content": m.content})

        response = await self.client.chat.completions.create(
            model=settings.AGENT_CHAT_MODEL,
            messages=request_messages,
            temperature=0.7,
        )
        content = response.choices[0].message.content
        return (content or "").strip()

    async def create(self, data: AgentConfigCreate) -> AgentConfig:
        """
        Create a new agent config.
        :param data: AgentConfigCreate
        :return: AgentConfig
        """
        agent_config = AgentConfig(
            name=data.name,
            guardrail=data.guardrail,
            description=data.description,
            purpose=data.purpose,
        )
        return await self.agent_config_repository.create(agent_config)


def _build_system_message(config: AgentConfig) -> str:
    """Build system message from guardrail, description, purpose."""
    parts = []
    if config.guardrail:
        parts.append(f"Guardrail: {config.guardrail}")
    if config.description:
        parts.append(f"Description: {config.description}")
    if config.purpose:
        parts.append(f"Purpose: {config.purpose}")
    return "\n\n".join(parts) if parts else "You are a helpful assistant."
