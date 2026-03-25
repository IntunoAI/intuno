"""Cron scheduler — runs workflow executions on a schedule.

Uses APScheduler's async scheduler to register cron triggers defined in
workflow definitions.  Integrates with the BackgroundRunner so scheduled
executions follow the same lifecycle as API-triggered ones.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger as APCronTrigger

logger = logging.getLogger(__name__)


class WorkflowScheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[str, str] = {}

    async def start(self) -> None:
        self._scheduler.start()
        logger.info("Workflow scheduler started")

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("Workflow scheduler stopped")

    def register(
        self,
        workflow_id: uuid.UUID,
        cron_expr: str,
        callback: Any,
    ) -> None:
        """Register a cron job for a workflow.

        ``callback`` is an async callable ``(workflow_id) -> None`` that
        triggers the workflow (usually via BackgroundRunner).
        """
        job_id = f"cron:{workflow_id}"
        if job_id in self._jobs:
            self._scheduler.remove_job(job_id)

        parts = cron_expr.strip().split()
        if len(parts) == 5:
            minute, hour, day, month, day_of_week = parts
            trigger = APCronTrigger(
                minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week,
            )
        else:
            trigger = APCronTrigger.from_crontab(cron_expr)

        self._scheduler.add_job(
            callback,
            trigger,
            args=[workflow_id],
            id=job_id,
            replace_existing=True,
        )
        self._jobs[job_id] = cron_expr
        logger.info("Registered cron job '%s' for workflow %s", cron_expr, workflow_id)

    def unregister(self, workflow_id: uuid.UUID) -> None:
        job_id = f"cron:{workflow_id}"
        if job_id in self._jobs:
            self._scheduler.remove_job(job_id)
            del self._jobs[job_id]
