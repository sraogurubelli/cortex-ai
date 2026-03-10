"""
Embedding Service for RAG.

Provides text embedding generation with optional Redis caching for cost optimization.

Features:
- OpenAI embeddings API integration
- Redis caching layer (optional)
- Batch processing support
- Graceful degradation without Redis

Usage:
    # With Redis caching
    embeddings = EmbeddingService(
        openai_api_key="sk-...",
        redis_url="redis://localhost:6379",
    )

    # Without caching (development)
    embeddings = EmbeddingService(
        openai_api_key="sk-...",
    )

    # Generate embedding
    embedding = await embeddings.generate_embedding("Python is great")

    # Batch processing
    embeddings_list = await embeddings.generate_embeddings([
        "First document",
        "Second document",
    ])

Environment Variables:
    CORTEX_OPENAI_API_KEY: OpenAI API key
    CORTEX_REDIS_URL: Redis URL for caching (optional)
    CORTEX_EMBEDDING_MODEL: Model name (default: text-embedding-3-small)
    CORTEX_EMBEDDING_CACHE_TTL: Cache TTL in seconds (default: 86400 = 1 day)
"""

import hashlib
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Environment configuration
OPENAI_API_KEY = os.getenv("CORTEX_OPENAI_API_KEY", "")
REDIS_URL = os.getenv("CORTEX_REDIS_URL", "redis://localhost:6379")
EMBEDDING_MODEL = os.getenv("CORTEX_EMBEDDING_MODEL", "text-embedding-3-small")
CACHE_TTL = int(os.getenv("CORTEX_EMBEDDING_CACHE_TTL", "86400"))

# Optional imports
try:
    from openai import AsyncOpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI not installed. Install with: pip install openai")

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.debug("Redis not installed. Caching disabled. Install with: pip install redis")


class EmbeddingService:
    """
    Embedding service with OpenAI and optional Redis caching.

    Generates text embeddings using OpenAI's API and caches results in Redis
    to reduce costs and improve performance.
    """

    def __init__(
        self,
        openai_api_key: str | None = None,
        redis_url: str | None = None,
        model: str = EMBEDDING_MODEL,
        cache_ttl: int = CACHE_TTL,
    ):
        """
        Initialize embedding service.

        Args:
            openai_api_key: OpenAI API key (or use CORTEX_OPENAI_API_KEY env var)
            redis_url: Redis URL for caching (or use CORTEX_REDIS_URL env var)
            model: OpenAI embedding model (default: text-embedding-3-small)
            cache_ttl: Cache TTL in seconds (default: 86400 = 1 day)

        Raises:
            ImportError: If OpenAI package not installed
        """
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "OpenAI package required for embeddings. Install with: pip install openai"
            )

        self.api_key = openai_api_key or OPENAI_API_KEY
        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set CORTEX_OPENAI_API_KEY or pass openai_api_key parameter"
            )

        self.model = model
        self.cache_ttl = cache_ttl
        self.client = AsyncOpenAI(api_key=self.api_key)

        # Redis caching (optional)
        self.redis_url = redis_url or REDIS_URL
        self.redis: Any | None = None
        self.cache_enabled = REDIS_AVAILABLE and bool(self.redis_url)

        if self.cache_enabled:
            logger.info(f"Embedding service initialized with Redis caching (TTL: {cache_ttl}s)")
        else:
            logger.info("Embedding service initialized without caching")

    async def connect(self) -> None:
        """
        Connect to Redis (if caching enabled).

        Safe to call multiple times - idempotent.
        """
        if not self.cache_enabled:
            return

        if self.redis is None:
            try:
                self.redis = await aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=False,
                )
                await self.redis.ping()
                logger.info("Connected to Redis for embedding cache")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}. Continuing without cache.")
                self.cache_enabled = False
                self.redis = None

    async def disconnect(self) -> None:
        """
        Disconnect from Redis.

        Call at application shutdown.
        """
        if self.redis is not None:
            await self.redis.close()
            self.redis = None
            logger.info("Disconnected from Redis")

    def _generate_cache_key(self, text: str) -> str:
        """
        Generate cache key for text.

        Uses SHA256 hash to handle arbitrary text lengths.

        Args:
            text: Text to generate key for

        Returns:
            str: Cache key in format "cortex:embedding:{model}:{hash}"
        """
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        return f"cortex:embedding:{self.model}:{text_hash}"

    async def _get_from_cache(self, text: str) -> list[float] | None:
        """
        Get embedding from cache.

        Args:
            text: Text to look up

        Returns:
            list[float] | None: Cached embedding or None if not found
        """
        if not self.cache_enabled or self.redis is None:
            return None

        try:
            key = self._generate_cache_key(text)
            cached = await self.redis.get(key)
            if cached:
                logger.debug(f"Cache hit for text (len={len(text)})")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache lookup error: {e}")

        return None

    async def _save_to_cache(self, text: str, embedding: list[float]) -> None:
        """
        Save embedding to cache.

        Args:
            text: Text that was embedded
            embedding: Embedding vector to cache
        """
        if not self.cache_enabled or self.redis is None:
            return

        try:
            key = self._generate_cache_key(text)
            await self.redis.set(
                key,
                json.dumps(embedding),
                ex=self.cache_ttl,
            )
            logger.debug(f"Cached embedding for text (len={len(text)})")
        except Exception as e:
            logger.warning(f"Cache save error: {e}")

    async def generate_embedding(self, text: str) -> list[float]:
        """
        Generate embedding for text.

        Checks cache first, then calls OpenAI API if not found.

        Args:
            text: Text to embed

        Returns:
            list[float]: Embedding vector

        Example:
            >>> embedding = await embeddings.generate_embedding("Python is great")
            >>> len(embedding)
            1536
        """
        # Check cache
        cached = await self._get_from_cache(text)
        if cached is not None:
            return cached

        # Generate with OpenAI
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
            )
            embedding = response.data[0].embedding

            # Cache result
            await self._save_to_cache(text, embedding)

            logger.debug(f"Generated embedding for text (len={len(text)})")
            return embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Uses batch API for efficiency, falls back to individual calls for cache hits.

        Args:
            texts: List of texts to embed

        Returns:
            list[list[float]]: List of embedding vectors

        Example:
            >>> embeddings_list = await embeddings.generate_embeddings([
            ...     "First document",
            ...     "Second document",
            ... ])
            >>> len(embeddings_list)
            2
        """
        if not texts:
            return []

        # Check cache for all texts
        results: list[list[float] | None] = []
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(texts):
            cached = await self._get_from_cache(text)
            results.append(cached)
            if cached is None:
                uncached_indices.append(i)
                uncached_texts.append(text)

        # Generate embeddings for uncached texts
        if uncached_texts:
            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=uncached_texts,
                )

                # Extract embeddings and cache them
                for i, data in enumerate(response.data):
                    embedding = data.embedding
                    text = uncached_texts[i]
                    original_index = uncached_indices[i]

                    results[original_index] = embedding
                    await self._save_to_cache(text, embedding)

                logger.debug(
                    f"Generated {len(uncached_texts)} embeddings "
                    f"({len(texts) - len(uncached_texts)} cached)"
                )

            except Exception as e:
                logger.error(f"Failed to generate batch embeddings: {e}")
                raise

        # Ensure all results are populated
        return [r for r in results if r is not None]

    async def get_cache_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            dict: Cache statistics (size, memory usage, etc.)

        Example:
            >>> stats = await embeddings.get_cache_stats()
            >>> stats["enabled"]
            True
        """
        stats = {
            "enabled": self.cache_enabled,
            "model": self.model,
            "ttl": self.cache_ttl,
        }

        if self.cache_enabled and self.redis is not None:
            try:
                info = await self.redis.info("stats")
                stats["keys"] = info.get("db0", {}).get("keys", 0)
                stats["memory_used"] = info.get("used_memory_human", "unknown")
            except Exception as e:
                logger.warning(f"Failed to get cache stats: {e}")

        return stats

    async def clear_cache(self) -> int:
        """
        Clear all cached embeddings.

        Returns:
            int: Number of keys deleted

        Example:
            >>> deleted = await embeddings.clear_cache()
            >>> print(f"Deleted {deleted} cached embeddings")
        """
        if not self.cache_enabled or self.redis is None:
            return 0

        try:
            pattern = f"cortex:embedding:{self.model}:*"
            cursor = 0
            deleted = 0

            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    deleted += await self.redis.delete(*keys)
                if cursor == 0:
                    break

            logger.info(f"Cleared {deleted} cached embeddings")
            return deleted

        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return 0
