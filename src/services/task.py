"""Task domain service: create/get tasks, run orchestrator (sync or async)."""

from typing import Optional, Tuple
from uuid import UUID

from fastapi import Depends

from src.core.settings import settings
from src.exceptions import BadRequestException
from src.models.task import Task
from src.repositories.broker import BrokerConfigRepository
from src.repositories.conversation import ConversationRepository
from src.repositories.message import MessageRepository
from src.repositories.registry import RegistryRepository
from src.repositories.invocation_log import InvocationLogRepository
from src.repositories.brand import BrandRepository
from src.repositories.task import TaskRepository
from src.schemas.task import TaskCreate
from src.services.broker import BrokerService
from src.services.registry import RegistryService
from src.utilities.embedding import EmbeddingService
from src.utilities.executor import Executor
from src.utilities.orchestrator import Orchestrator, OrchestratorContext
from src.database import AsyncSessionLocal


class TaskService:
    """Service for task operations: create, get, run orchestrator."""

    def __init__(
        self,
        task_repository: TaskRepository = Depends(),
        conversation_repository: ConversationRepository = Depends(),
        message_repository: MessageRepository = Depends(),
        registry_service: RegistryService = Depends(),
        broker_service: BrokerService = Depends(),
        embedding_service: EmbeddingService = Depends(),
        broker_config_repository: BrokerConfigRepository = Depends(),
    ):
        self.task_repository = task_repository
        self.conversation_repository = conversation_repository
        self.message_repository = message_repository
        self.registry_service = registry_service
        self.broker_service = broker_service
        self.embedding_service = embedding_service
        self.broker_config_repository = broker_config_repository
        executor = Executor(
            registry_service=registry_service,
            broker_service=broker_service,
            embedding_service=embedding_service,
            broker_config_repository=broker_config_repository,
        )
        self.orchestrator = Orchestrator(executor=executor)

    async def _validate_conversation_message(
        self,
        user_id: UUID,
        integration_id: Optional[UUID],
        conversation_id: Optional[UUID],
        message_id: Optional[UUID],
    ) -> None:
        """Validate conversation and message ownership (same rules as Broker)."""
        if conversation_id is not None:
            conversation = await self.conversation_repository.get_by_id(conversation_id)
            if not conversation or conversation.user_id != user_id:
                raise BadRequestException("Conversation not found or access denied")
            if integration_id is not None and conversation.integration_id != integration_id:
                raise BadRequestException("Conversation does not belong to this integration")
        if message_id is not None:
            if conversation_id is None:
                raise BadRequestException("message_id requires conversation_id")
            message = await self.message_repository.get_by_id(message_id)
            if not message or message.conversation_id != conversation_id:
                raise BadRequestException("Message not found or does not belong to conversation")

    async def create(
        self,
        user_id: UUID,
        integration_id: Optional[UUID],
        data: TaskCreate,
        idempotency_key: Optional[str] = None,
        async_mode: bool = False,
    ) -> Tuple[Task, bool]:
        """
        Create a task (or return existing if idempotency key matches).
        Validates conversation_id/message_id. If async_mode, returns (task, True) and
        caller should schedule run_task_background(task.id). Else runs orchestrator
        in-process and returns (task, False).
        """
        if idempotency_key:
            existing = await self.task_repository.get_by_idempotency_key(idempotency_key)
            if existing:
                return (existing, False)

        await self._validate_conversation_message(
            user_id,
            integration_id,
            data.conversation_id,
            data.message_id,
        )

        task = Task(
            user_id=user_id,
            integration_id=integration_id,
            status="pending",
            goal=data.goal,
            input=data.input,
            conversation_id=data.conversation_id,
            message_id=data.message_id,
            external_user_id=data.external_user_id,
            idempotency_key=idempotency_key,
        )
        task = await self.task_repository.create(task)

        if async_mode:
            return (task, True)

        # Sync: run orchestrator in-process
        task.status = "running"
        await self.task_repository.update(task)

        def on_progress(steps: list) -> None:
            pass  # In sync mode we don't persist step progress; update at end

        ctx = OrchestratorContext(
            user_id=user_id,
            integration_id=integration_id,
            conversation_id=data.conversation_id,
            message_id=data.message_id,
            external_user_id=data.external_user_id,
            task_timeout_seconds=settings.TASK_TIMEOUT_SECONDS,
            fallback_agent_id=settings.ORCHESTRATOR_FALLBACK_AGENT_ID,
            fallback_capability_id=settings.ORCHESTRATOR_FALLBACK_CAPABILITY_ID,
            on_step_progress=on_progress,
        )
        result = await self.orchestrator.run(goal=data.goal, input_data=data.input, context=ctx)

        if result.success:
            task.status = "completed"
            task.result = result.result
            task.error_message = None
        else:
            task.status = "failed"
            if result.error_message == "Task timeout exceeded.":
                task.status = "timeout"
            task.result = None
            task.error_message = result.error_message
        task.steps = result.steps
        await self.task_repository.update(task)
        return (task, False)

    async def get(self, task_id: UUID, user_id: UUID) -> Optional[Task]:
        """Get task by ID if owned by user."""
        task = await self.task_repository.get_by_id(task_id)
        if not task or task.user_id != user_id:
            return None
        return task


async def run_task_background(task_id: UUID) -> None:
    """
    Run orchestrator for a task in the background (new session).
    Called by route via BackgroundTasks after returning 202.
    """
    from src.repositories.invocation_log import InvocationLogRepository

    async with AsyncSessionLocal() as session:
        task_repo = TaskRepository(session)
        conversation_repo = ConversationRepository(session)
        message_repo = MessageRepository(session)
        registry_repo = RegistryRepository(session)
        invocation_log_repo = InvocationLogRepository(session)
        brand_repo = BrandRepository(session)
        broker_config_repo = BrokerConfigRepository(session)

        task = await task_repo.get_by_id(task_id)
        if not task or task.status != "pending":
            return

        task.status = "running"
        await task_repo.update(task)

        embedding_service = EmbeddingService()
        registry_service = RegistryService(
            registry_repository=registry_repo,
            invocation_log_repository=invocation_log_repo,
            embedding_service=embedding_service,
            brand_repository=brand_repo,
        )
        broker_service = BrokerService(
            invocation_log_repository=invocation_log_repo,
            broker_config_repository=broker_config_repo,
            registry_repository=registry_repo,
            conversation_repository=conversation_repo,
            message_repository=message_repo,
        )
        executor = Executor(
            registry_service=registry_service,
            broker_service=broker_service,
            embedding_service=embedding_service,
            broker_config_repository=broker_config_repo,
        )
        orchestrator = Orchestrator(executor=executor)

        async def on_progress(steps: list) -> None:
            task.steps = steps
            await task_repo.update(task)

        ctx = OrchestratorContext(
            user_id=task.user_id,
            integration_id=task.integration_id,
            conversation_id=task.conversation_id,
            message_id=task.message_id,
            external_user_id=task.external_user_id,
            task_timeout_seconds=settings.TASK_TIMEOUT_SECONDS,
            fallback_agent_id=settings.ORCHESTRATOR_FALLBACK_AGENT_ID,
            fallback_capability_id=settings.ORCHESTRATOR_FALLBACK_CAPABILITY_ID,
            on_step_progress=on_progress,
        )
        result = await orchestrator.run(goal=task.goal, input_data=task.input or {}, context=ctx)

        if result.success:
            task.status = "completed"
            task.result = result.result
            task.error_message = None
        else:
            task.status = "failed"
            if result.error_message == "Task timeout exceeded.":
                task.status = "timeout"
            task.result = None
            task.error_message = result.error_message
        task.steps = result.steps
        await task_repo.update(task)
