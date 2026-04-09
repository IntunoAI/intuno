"""Background delivery worker for async network messages.

Consumes from a Redis Stream to deliver pending messages to participants
via their callback URLs.  Follows the same consumer-group pattern as
``src.workflow.utils.event_consumer.EventConsumer``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
import redis.asyncio as aioredis

from src.core.settings import settings

logger = logging.getLogger(__name__)

STREAM_KEY = "intuno:network:delivery"
CONSUMER_GROUP = "network_delivery_workers"
CONSUMER_NAME = "delivery-worker-1"


class DeliveryWorker:
    """Reads pending deliveries from Redis Stream and POSTs to callback URLs."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._task: asyncio.Task[None] | None = None
        self._http_client: httpx.AsyncClient | None = None

    async def start(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http_client = http_client
        try:
            await self._redis.xgroup_create(
                STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True,
            )
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._task = asyncio.create_task(self._consume(), name="delivery-worker")
        logger.info("Delivery worker started on stream '%s'", STREAM_KEY)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Delivery worker stopped")

    @staticmethod
    async def enqueue(
        redis: aioredis.Redis,
        *,
        callback_url: str,
        payload: dict[str, Any],
        message_id: str,
        attempt: int = 0,
    ) -> None:
        """Enqueue a delivery task into the Redis Stream."""
        await redis.xadd(
            STREAM_KEY,
            {
                "callback_url": callback_url,
                "payload": json.dumps(payload, default=str),
                "message_id": message_id,
                "attempt": str(attempt),
            },
        )

    async def _consume(self) -> None:
        while True:
            try:
                entries = await self._redis.xreadgroup(
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    {STREAM_KEY: ">"},
                    count=10,
                    block=5000,
                )
                if not entries:
                    continue
                for _stream, messages in entries:
                    for msg_id, data in messages:
                        await self._deliver(msg_id, data)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Delivery worker error; retrying in 2s")
                await asyncio.sleep(2)

    async def _deliver(self, stream_id: str, data: dict[str, str]) -> None:
        callback_url = data.get("callback_url", "")
        payload_raw = data.get("payload", "{}")
        message_id = data.get("message_id", "")
        attempt = int(data.get("attempt", "0"))

        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {"raw": payload_raw}

        client = self._http_client or httpx.AsyncClient(
            timeout=settings.NETWORK_CALLBACK_TIMEOUT_SECONDS
        )
        owns_client = self._http_client is None

        try:
            response = await client.post(
                callback_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Intuno-Network/1.0",
                },
                timeout=settings.NETWORK_CALLBACK_TIMEOUT_SECONDS,
            )
            if response.status_code == 200:
                logger.debug("Delivered message %s to %s", message_id, callback_url)
            else:
                logger.warning(
                    "Delivery to %s returned %d for message %s",
                    callback_url,
                    response.status_code,
                    message_id,
                )
                await self._maybe_retry(data, attempt)
        except Exception:
            logger.warning(
                "Delivery to %s failed for message %s (attempt %d)",
                callback_url,
                message_id,
                attempt,
            )
            await self._maybe_retry(data, attempt)
        finally:
            if owns_client:
                await client.aclose()

        await self._redis.xack(STREAM_KEY, CONSUMER_GROUP, stream_id)

    async def _maybe_retry(self, data: dict[str, str], attempt: int) -> None:
        if attempt < settings.NETWORK_MESSAGE_DELIVERY_MAX_RETRIES:
            backoff = 2 ** (attempt + 1)
            await asyncio.sleep(backoff)
            await self.enqueue(
                self._redis,
                callback_url=data.get("callback_url", ""),
                payload=json.loads(data.get("payload", "{}")),
                message_id=data.get("message_id", ""),
                attempt=attempt + 1,
            )
