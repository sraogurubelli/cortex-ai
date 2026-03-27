"""
Distributed Locks using Redis

Prevents race conditions in multi-instance deployments.

Use Cases:
- Conversation title generation (avoid duplicate generation)
- Rate limit enforcement (cross-instance)
- Resource allocation (agent pools, quotas)
- Cache invalidation coordination

Usage:
    from cortex.api.distributed.locks import DistributedLock

    async with DistributedLock("conversation:conv-123:generate-title") as acquired:
        if acquired:
            # Critical section - only one instance can execute
            title = await generate_title(conversation_id)
            await save_title(conversation_id, title)
        else:
            # Lock acquisition failed, skip or retry
            logger.info("Another instance is generating title")
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, Optional

from cortex.platform.config.settings import get_settings

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available. Distributed locks disabled.")


class DistributedLock:
    """
    Distributed lock using Redis.

    Implements a simple distributed lock with automatic expiration.
    Uses SET NX EX for atomic lock acquisition.
    """

    def __init__(
        self,
        key: str,
        timeout: int = 10,
        blocking: bool = False,
        retry_interval: float = 0.1,
    ):
        """
        Initialize distributed lock.

        Args:
            key: Lock key (e.g., "conversation:conv-123:operation")
            timeout: Lock timeout in seconds (default: 10)
            blocking: Wait for lock if True, fail immediately if False
            retry_interval: Retry interval when blocking (default: 0.1s)
        """
        self.key = f"cortex:lock:{key}"
        self.timeout = timeout
        self.blocking = blocking
        self.retry_interval = retry_interval
        self.token = f"lock-{uuid.uuid4().hex[:12]}"
        self.redis: Any | None = None
        self.enabled = REDIS_AVAILABLE

    async def _get_redis(self) -> Optional[Any]:
        """Get or create Redis connection."""
        if not self.enabled:
            return None

        if self.redis is None:
            try:
                settings = get_settings()
                self.redis = await aioredis.from_url(
                    settings.redis_url,
                    socket_connect_timeout=2,
                    decode_responses=True,
                )
                await self.redis.ping()
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                self.enabled = False
                return None

        return self.redis

    async def acquire(self) -> bool:
        """
        Acquire lock.

        Returns:
            True if lock acquired, False otherwise
        """
        redis = await self._get_redis()
        if not redis:
            logger.warning(f"Redis not available, lock {self.key} skipped")
            return True  # Graceful degradation: proceed without lock

        if self.blocking:
            # Blocking mode: retry until lock acquired or timeout
            deadline = asyncio.get_event_loop().time() + self.timeout
            while True:
                acquired = await self._try_acquire(redis)
                if acquired:
                    return True

                if asyncio.get_event_loop().time() >= deadline:
                    logger.warning(f"Lock acquisition timeout: {self.key}")
                    return False

                await asyncio.sleep(self.retry_interval)
        else:
            # Non-blocking mode: try once
            return await self._try_acquire(redis)

    async def _try_acquire(self, redis: Any) -> bool:
        """
        Try to acquire lock once.

        Args:
            redis: Redis connection

        Returns:
            True if lock acquired, False otherwise
        """
        try:
            # SET NX EX is atomic: set if not exists with expiration
            result = await redis.set(
                self.key,
                self.token,
                ex=self.timeout,
                nx=True,  # Only set if key doesn't exist
            )
            acquired = result is not None

            if acquired:
                logger.debug(f"Lock acquired: {self.key}")
            else:
                logger.debug(f"Lock acquisition failed: {self.key}")

            return acquired

        except Exception as e:
            logger.error(f"Lock acquisition error: {e}")
            return False

    async def release(self) -> bool:
        """
        Release lock.

        Only releases if this instance owns the lock (via token check).

        Returns:
            True if lock released, False otherwise
        """
        redis = await self._get_redis()
        if not redis:
            return True  # No lock to release

        try:
            # Lua script for atomic check-and-delete
            # Only delete if token matches (this instance owns the lock)
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """

            result = await redis.eval(lua_script, 1, self.key, self.token)
            released = result == 1

            if released:
                logger.debug(f"Lock released: {self.key}")
            else:
                logger.debug(f"Lock not released (not owned or expired): {self.key}")

            return released

        except Exception as e:
            logger.error(f"Lock release error: {e}")
            return False

    async def extend(self, additional_time: int) -> bool:
        """
        Extend lock timeout.

        Args:
            additional_time: Additional time in seconds

        Returns:
            True if lock extended, False otherwise
        """
        redis = await self._get_redis()
        if not redis:
            return True

        try:
            # Lua script for atomic check-and-expire
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("expire", KEYS[1], ARGV[2])
            else
                return 0
            end
            """

            result = await redis.eval(
                lua_script,
                1,
                self.key,
                self.token,
                str(additional_time),
            )
            extended = result == 1

            if extended:
                logger.debug(f"Lock extended: {self.key} (+{additional_time}s)")
            else:
                logger.debug(f"Lock not extended (not owned or expired): {self.key}")

            return extended

        except Exception as e:
            logger.error(f"Lock extension error: {e}")
            return False

    async def __aenter__(self):
        """Context manager entry."""
        acquired = await self.acquire()
        return acquired

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.release()
        if self.redis:
            await self.redis.close()
            self.redis = None


# ============================================================================
# Convenience Functions
# ============================================================================


@asynccontextmanager
async def distributed_lock(
    key: str,
    timeout: int = 10,
    blocking: bool = False,
):
    """
    Convenience async context manager for distributed locks.

    Args:
        key: Lock key
        timeout: Lock timeout in seconds
        blocking: Wait for lock if True

    Yields:
        True if lock acquired, False otherwise

    Example:
        >>> async with distributed_lock("resource:123") as acquired:
        ...     if acquired:
        ...         # Critical section
        ...         process_resource(123)
        ...     else:
        ...         logger.info("Resource locked by another instance")
    """
    lock = DistributedLock(key, timeout=timeout, blocking=blocking)
    acquired = await lock.acquire()
    try:
        yield acquired
    finally:
        await lock.release()
        if lock.redis:
            await lock.redis.close()


async def is_locked(key: str) -> bool:
    """
    Check if a resource is locked.

    Args:
        key: Lock key

    Returns:
        True if locked, False otherwise

    Example:
        >>> locked = await is_locked("conversation:conv-123:generate-title")
        >>> if not locked:
        ...     # Proceed with operation
    """
    try:
        settings = get_settings()
        redis = await aioredis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            decode_responses=True,
        )
        full_key = f"cortex:lock:{key}"
        exists = await redis.exists(full_key)
        await redis.close()
        return exists == 1
    except Exception as e:
        logger.error(f"Lock check error: {e}")
        return False  # Assume not locked on error
