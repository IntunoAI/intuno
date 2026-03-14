"""Task domain repository."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.task import Task


class TaskRepository:
    """Repository for task domain operations."""

    def __init__(self, session: AsyncSession = Depends(get_db)):
        self.session = session

    async def create(self, task: Task) -> Task:
        """
        Create a new task.
        :param task: Task
        :return: Task
        """
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def get_by_id(self, task_id: UUID) -> Optional[Task]:
        """
        Get task by ID.
        :param task_id: UUID
        :return: Optional[Task]
        """
        result = await self.session.execute(
            select(Task).where(Task.id == task_id)
        )
        return result.scalar_one_or_none()

    async def update(self, task: Task) -> Task:
        """
        Update a task (fields already set on entity).
        :param task: Task
        :return: Task
        """
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def get_by_idempotency_key(self, key: str) -> Optional[Task]:
        """
        Get task by idempotency key (for idempotent POST).
        :param key: str
        :return: Optional[Task]
        """
        result = await self.session.execute(
            select(Task).where(Task.idempotency_key == key)
        )
        return result.scalar_one_or_none()

    async def get_stale_running_tasks(
        self, older_than_minutes: int
    ) -> List[Task]:
        """
        Get tasks with status=running and updated_at older than threshold.
        For use by a future cron to mark them as timeout.
        :param older_than_minutes: int
        :return: List[Task]
        """
        threshold = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        result = await self.session.execute(
            select(Task)
            .where(Task.status == "running")
            .where(Task.updated_at < threshold)
        )
        return list(result.scalars().all())

    async def mark_stale_tasks_timeout(self, older_than_minutes: int) -> int:
        """
        Mark running tasks older than threshold as status=timeout.
        Returns the number of tasks updated. For use by a future cron.
        :param older_than_minutes: int
        :return: int
        """
        threshold = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        result = await self.session.execute(
            update(Task)
            .where(Task.status == "running")
            .where(Task.updated_at < threshold)
            .values(status="timeout")
        )
        await self.session.commit()
        return result.rowcount or 0
