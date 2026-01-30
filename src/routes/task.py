"""Task routes: POST /tasks, GET /tasks/{task_id}; API key auth; idempotency; async option."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, status
from fastapi.responses import JSONResponse

from src.core.security import get_user_and_integration_from_api_key
from src.exceptions import NotFoundException
from src.models.auth import User
from src.schemas.task import TaskCreate, TaskResponse
from src.services.task import TaskService, run_task_background

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post(
    "",
    responses={
        201: {"description": "Task created and completed (sync)"},
        202: {"description": "Task created, running in background (async)"},
    },
)
async def create_task(
    data: TaskCreate,
    background_tasks: BackgroundTasks,
    user_and_integration: tuple[User, Optional[UUID]] = Depends(
        get_user_and_integration_from_api_key
    ),
    task_service: TaskService = Depends(),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    async_mode: bool = Query(default=False, alias="async"),
):
    """
    Create a task: goal + input; optional conversation_id, message_id.
    Idempotency-Key: if present and task exists for key, return existing task.
    async=true: return 202 with task_id and run orchestrator in background; client polls GET /tasks/{task_id}.
    """
    current_user, integration_id = user_and_integration
    task, is_async = await task_service.create(
        user_id=current_user.id,
        integration_id=integration_id,
        data=data,
        idempotency_key=idempotency_key,
        async_mode=async_mode,
    )
    if is_async:
        background_tasks.add_task(run_task_background, task.id)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"task_id": str(task.id)},
            headers={"Location": f"/tasks/{task.id}"},
        )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=TaskResponse.model_validate(task).model_dump(mode="json"),
    )


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
)
async def get_task(
    task_id: UUID,
    user_and_integration: tuple[User, Optional[UUID]] = Depends(
        get_user_and_integration_from_api_key
    ),
    task_service: TaskService = Depends(),
) -> TaskResponse:
    """
    Get task by ID (user-scoped). Returns task with steps in body.
    """
    current_user, _ = user_and_integration
    task = await task_service.get(task_id, current_user.id)
    if not task:
        raise NotFoundException("Task")
    return TaskResponse.model_validate(task)
