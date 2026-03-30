"""Redis Streams event consumer — listens for events and triggers matching workflows.

Workflows register event triggers (e.g. ``complaint.received``).
External systems publish events to a Redis stream.  The consumer reads
from the stream, matches event names to registered triggers, and fires
workflow executions via the BackgroundRunner.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Callable, Awaitable

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

STREAM_KEY = "agent_os:events"
CONSUMER_GROUP = "agent_os_workers"
CONSUMER_NAME = "worker-1"


class EventConsumer:
    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._registry: dict[str, list[uuid.UUID]] = {}
        self._callback: Callable[[uuid.UUID, dict[str, Any]], Awaitable[None]] | None = None
        self._task: asyncio.Task[None] | None = None

    def set_callback(
        self,
        callback: Callable[[uuid.UUID, dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Set the async callback invoked on event match: ``(workflow_id, event_data) -> None``."""
        self._callback = callback

    def register(self, event_name: str, workflow_id: uuid.UUID) -> None:
        self._registry.setdefault(event_name, []).append(workflow_id)
        logger.info(
            "Registered event trigger '%s' -> workflow %s", event_name, workflow_id,
        )

    def unregister(self, event_name: str, workflow_id: uuid.UUID) -> None:
        wf_list = self._registry.get(event_name, [])
        if workflow_id in wf_list:
            wf_list.remove(workflow_id)

    async def start(self) -> None:
        try:
            await self._redis.xgroup_create(
                STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True,
            )
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._task = asyncio.create_task(self._consume(), name="event-consumer")
        logger.info("Event consumer started on stream '%s'", STREAM_KEY)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Event consumer stopped")

    async def _consume(self) -> None:
        while True:
            try:
                entries = await self._redis.xreadgroup(
                    CONSUMER_GROUP, CONSUMER_NAME,
                    {STREAM_KEY: ">"},
                    count=10,
                    block=5000,
                )
                if not entries:
                    continue
                for _stream, messages in entries:
                    for msg_id, data in messages:
                        await self._handle(msg_id, data)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Event consumer error; retrying in 2s")
                await asyncio.sleep(2)

    async def _handle(self, msg_id: str, data: dict[str, str]) -> None:
        event_name = data.get("event", "")
        payload_raw = data.get("payload", "{}")
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {"raw": payload_raw}

        matching_workflows = self._registry.get(event_name, [])
        if not matching_workflows:
            await self._redis.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)
            return

        for wf_id in matching_workflows:
            if self._callback:
                try:
                    await self._callback(wf_id, payload)
                except Exception:
                    logger.exception(
                        "Failed to trigger workflow %s for event '%s'",
                        wf_id, event_name,
                    )

        await self._redis.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)
