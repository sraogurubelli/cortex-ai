"""
Lightweight async job queue using Redis Streams.

Provides a simple producer/consumer pattern without heavy dependencies
like Celery. Jobs are JSON-serialized and processed by async workers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

_handlers: dict[str, Callable[..., Coroutine]] = {}


def job_handler(name: str):
    """Decorator to register an async function as a job handler.

    Usage::

        @job_handler("send_webhook")
        async def handle_send_webhook(payload: dict) -> None:
            ...
    """
    def decorator(func):
        _handlers[name] = func
        return func
    return decorator


async def enqueue(job_name: str, payload: dict, redis_url: Optional[str] = None) -> str:
    """Enqueue a job for background processing.

    Returns the job ID.
    """
    from cortex.platform.config.settings import get_settings

    url = redis_url or get_settings().redis_url
    stream = get_settings().redis_stream_name

    import redis.asyncio as aioredis

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    message = json.dumps({
        "job_id": job_id,
        "job_name": job_name,
        "payload": payload,
        "enqueued_at": time.time(),
    })

    try:
        r = aioredis.from_url(url, decode_responses=True)
        await r.xadd(stream, {"data": message})
        await r.aclose()
        logger.info("Enqueued job %s: %s", job_id, job_name)
    except Exception:
        logger.warning("Failed to enqueue job %s, running inline", job_name, exc_info=True)
        handler = _handlers.get(job_name)
        if handler:
            await handler(payload)

    return job_id


class JobQueue:
    """Redis Streams consumer that processes jobs with registered handlers."""

    def __init__(self, redis_url: Optional[str] = None, concurrency: int = 4):
        from cortex.platform.config.settings import get_settings
        self._redis_url = redis_url or get_settings().redis_url
        self._stream = get_settings().redis_stream_name
        self._group = get_settings().redis_consumer_group
        self._consumer = f"worker-{uuid.uuid4().hex[:8]}"
        self._concurrency = concurrency
        self._running = False
        self._semaphore = asyncio.Semaphore(concurrency)

    async def start(self) -> None:
        """Start consuming jobs from the Redis stream."""
        import redis.asyncio as aioredis

        self._running = True
        r = aioredis.from_url(self._redis_url, decode_responses=True)

        try:
            await r.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except Exception:
            pass

        logger.info(
            "Job queue started: stream=%s group=%s consumer=%s handlers=%s",
            self._stream, self._group, self._consumer, list(_handlers.keys()),
        )

        while self._running:
            try:
                entries = await r.xreadgroup(
                    self._group, self._consumer,
                    {self._stream: ">"},
                    count=self._concurrency,
                    block=5000,
                )

                if not entries:
                    continue

                for stream_name, messages in entries:
                    for msg_id, fields in messages:
                        raw = fields.get("data", "{}")
                        asyncio.create_task(
                            self._process(r, msg_id, raw)
                        )

            except asyncio.CancelledError:
                break
            except Exception:
                logger.error("Job queue error", exc_info=True)
                await asyncio.sleep(1)

        await r.aclose()

    async def stop(self) -> None:
        self._running = False

    async def _process(self, redis, msg_id: str, raw: str) -> None:
        async with self._semaphore:
            try:
                data = json.loads(raw)
                job_name = data.get("job_name", "unknown")
                payload = data.get("payload", {})
                job_id = data.get("job_id", "?")

                handler = _handlers.get(job_name)
                if not handler:
                    logger.warning("No handler for job: %s", job_name)
                    await redis.xack(self._stream, self._group, msg_id)
                    return

                start = time.monotonic()
                await handler(payload)
                elapsed = int((time.monotonic() - start) * 1000)

                logger.info("Job %s (%s) completed in %dms", job_id, job_name, elapsed)
                await redis.xack(self._stream, self._group, msg_id)

            except Exception:
                logger.error("Job processing failed: %s", raw[:200], exc_info=True)
                await redis.xack(self._stream, self._group, msg_id)
