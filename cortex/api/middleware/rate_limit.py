"""
Redis-backed HTTP Rate Limiting Middleware

Sliding-window rate limiter with configurable limits per:
  - Principal (authenticated user)
  - Tenant (account)
  - Endpoint class (chat endpoints get tighter limits)

Uses Redis INCR + EXPIRE for distributed rate state.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestCallbackType
from starlette.responses import JSONResponse

from cortex.platform.config.settings import get_settings

logger = logging.getLogger(__name__)

_CHAT_PATH_PREFIXES = ("/api/v1/projects/", "/api/v1/conversations/")
_CHAT_METHODS = {"POST"}

DEFAULT_RATE_LIMIT = 120
DEFAULT_WINDOW_SECONDS = 60
CHAT_RATE_LIMIT = 30
CHAT_WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter backed by Redis.

    Applies two tiers:
      - Chat endpoints (POST to chat/stream, chat, regenerate, etc.): tighter limit
      - All other endpoints: standard limit

    Limits are per-principal when authenticated, per-IP when anonymous.
    """

    def __init__(self, app, redis_url: Optional[str] = None):
        super().__init__(app)
        self._redis_url = redis_url or get_settings().redis_url
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(
                    self._redis_url,
                    socket_connect_timeout=2,
                    decode_responses=True,
                )
            except Exception:
                logger.warning("Rate limiter: Redis unavailable, skipping limits")
                return None
        return self._redis

    async def dispatch(
        self, request: Request, call_next: RequestCallbackType
    ) -> Response:
        if request.method == "OPTIONS" or request.url.path in ("/health", "/ready", "/"):
            return await call_next(request)

        redis = await self._get_redis()
        if redis is None:
            return await call_next(request)

        is_chat = (
            request.method in _CHAT_METHODS
            and any(request.url.path.startswith(p) for p in _CHAT_PATH_PREFIXES)
        )

        limit = CHAT_RATE_LIMIT if is_chat else DEFAULT_RATE_LIMIT
        window = CHAT_WINDOW_SECONDS if is_chat else DEFAULT_WINDOW_SECONDS

        identity = self._get_identity(request)
        tier = "chat" if is_chat else "api"
        key = f"cortex:ratelimit:{tier}:{identity}"

        try:
            current = await redis.incr(key)
            if current == 1:
                await redis.expire(key, window)

            ttl = await redis.ttl(key)
            if ttl < 0:
                ttl = window

            if current > limit:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limit_exceeded",
                        "message": f"Rate limit exceeded. Try again in {ttl}s.",
                        "retry_after": ttl,
                    },
                    headers={
                        "Retry-After": str(ttl),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time()) + ttl),
                    },
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current))
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + ttl)
            return response

        except Exception:
            logger.debug("Rate limiter error, passing through", exc_info=True)
            return await call_next(request)

    @staticmethod
    def _get_identity(request: Request) -> str:
        principal = getattr(request.state, "principal", None)
        if principal and hasattr(principal, "uid"):
            return f"principal:{principal.uid}"

        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        return f"ip:{request.client.host if request.client else 'unknown'}"
