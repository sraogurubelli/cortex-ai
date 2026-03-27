"""
StarRocks Client

Async client for StarRocks OLAP database.

Features:
- Async I/O with MySQL protocol (StarRocks is MySQL-compatible)
- Connection pooling
- Query execution with parameter binding
- Graceful degradation (falls back to PostgreSQL if unavailable)

Usage:
    client = StarRocksClient(
        host="localhost",
        port=9030,
        database="cortex_analytics",
    )
    await client.connect()

    # Execute query
    results = await client.query(
        "SELECT COUNT(*) as total FROM conversations WHERE tenant_id = %s",
        params=("tenant-123",)
    )

    # Execute with dict results
    results = await client.query_dict(
        "SELECT * FROM messages_fact LIMIT 10"
    )

    # Cleanup
    await client.disconnect()
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import aiomysql
    AIOMYSQL_AVAILABLE = True
except ImportError:
    AIOMYSQL_AVAILABLE = False
    logger.warning("aiomysql not installed. StarRocks client disabled.")


class StarRocksClient:
    """
    Async client for StarRocks OLAP database.

    StarRocks uses MySQL protocol, so we use aiomysql for connectivity.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9030,
        user: str = "root",
        password: str = "",
        database: str = "cortex_analytics",
        pool_size: int = 10,
    ):
        """
        Initialize StarRocks client.

        Args:
            host: StarRocks host
            port: StarRocks query port (default: 9030)
            user: Database user
            password: Database password
            database: Database name
            pool_size: Connection pool size
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.pool_size = pool_size
        self.pool: Any | None = None
        self.enabled = AIOMYSQL_AVAILABLE

        if not self.enabled:
            logger.info("StarRocks client disabled (aiomysql not available)")
        else:
            logger.info(
                f"StarRocks client initialized (host: {host}:{port}, db: {database})"
            )

    async def connect(self) -> None:
        """
        Connect to StarRocks and create connection pool.

        Safe to call multiple times - idempotent.
        Graceful degradation on connection failure.
        """
        if not self.enabled:
            return

        if self.pool is None:
            try:
                self.pool = await aiomysql.create_pool(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    db=self.database,
                    minsize=1,
                    maxsize=self.pool_size,
                    autocommit=True,  # OLAP queries don't need transactions
                    connect_timeout=5,
                )
                logger.info(f"Connected to StarRocks at {self.host}:{self.port}")
            except Exception as e:
                logger.warning(
                    f"Failed to connect to StarRocks: {e}. "
                    "Analytics queries disabled, falling back to PostgreSQL."
                )
                self.enabled = False
                self.pool = None

    async def disconnect(self) -> None:
        """Disconnect from StarRocks."""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            self.pool = None
            logger.info("Disconnected from StarRocks")

    async def query(
        self,
        sql: str,
        params: Optional[tuple] = None,
    ) -> list[tuple]:
        """
        Execute query and return results as list of tuples.

        Args:
            sql: SQL query
            params: Query parameters (for parameterized queries)

        Returns:
            List of tuples (one per row)

        Example:
            >>> results = await client.query(
            ...     "SELECT user_id, COUNT(*) FROM conversations GROUP BY user_id"
            ... )
            >>> for user_id, count in results:
            ...     print(f"User {user_id}: {count} conversations")
        """
        if not self.enabled or not self.pool:
            logger.warning("StarRocks not available, query skipped")
            return []

        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(sql, params)
                    results = await cursor.fetchall()
                    logger.debug(
                        f"StarRocks query executed: {sql[:100]}... ({len(results)} rows)"
                    )
                    return results
        except Exception as e:
            logger.error(f"StarRocks query error: {e}", exc_info=True)
            return []

    async def query_dict(
        self,
        sql: str,
        params: Optional[tuple] = None,
    ) -> list[dict]:
        """
        Execute query and return results as list of dictionaries.

        Args:
            sql: SQL query
            params: Query parameters

        Returns:
            List of dictionaries (one per row, column names as keys)

        Example:
            >>> results = await client.query_dict(
            ...     "SELECT * FROM conversations WHERE tenant_id = %s LIMIT 10",
            ...     params=("tenant-123",)
            ... )
            >>> for row in results:
            ...     print(row["conversation_id"], row["created_at"])
        """
        if not self.enabled or not self.pool:
            logger.warning("StarRocks not available, query skipped")
            return []

        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(sql, params)
                    results = await cursor.fetchall()
                    logger.debug(
                        f"StarRocks query executed: {sql[:100]}... ({len(results)} rows)"
                    )
                    return results
        except Exception as e:
            logger.error(f"StarRocks query error: {e}", exc_info=True)
            return []

    async def query_one(
        self,
        sql: str,
        params: Optional[tuple] = None,
    ) -> Optional[dict]:
        """
        Execute query and return single row as dictionary.

        Args:
            sql: SQL query
            params: Query parameters

        Returns:
            Dictionary or None if no results

        Example:
            >>> result = await client.query_one(
            ...     "SELECT COUNT(*) as total FROM messages WHERE conversation_id = %s",
            ...     params=("conv-123",)
            ... )
            >>> print(result["total"])
        """
        results = await self.query_dict(sql, params)
        return results[0] if results else None

    async def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
    ) -> int:
        """
        Execute non-query statement (INSERT, UPDATE, DELETE).

        Args:
            sql: SQL statement
            params: Statement parameters

        Returns:
            Number of affected rows

        Example:
            >>> affected = await client.execute(
            ...     "DELETE FROM temp_table WHERE created_at < %s",
            ...     params=("2026-01-01",)
            ... )
            >>> print(f"Deleted {affected} rows")
        """
        if not self.enabled or not self.pool:
            logger.warning("StarRocks not available, execute skipped")
            return 0

        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    affected = await cursor.execute(sql, params)
                    logger.debug(
                        f"StarRocks execute: {sql[:100]}... ({affected} rows affected)"
                    )
                    return affected
        except Exception as e:
            logger.error(f"StarRocks execute error: {e}", exc_info=True)
            return 0

    async def execute_many(
        self,
        sql: str,
        params_list: list[tuple],
    ) -> int:
        """
        Execute batch insert/update/delete.

        Args:
            sql: SQL statement
            params_list: List of parameter tuples

        Returns:
            Total number of affected rows

        Example:
            >>> rows = [
            ...     ("conv-1", "2026-03-26", 100),
            ...     ("conv-2", "2026-03-26", 200),
            ... ]
            >>> affected = await client.execute_many(
            ...     "INSERT INTO daily_stats VALUES (%s, %s, %s)",
            ...     rows
            ... )
        """
        if not self.enabled or not self.pool:
            logger.warning("StarRocks not available, execute_many skipped")
            return 0

        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    affected = await cursor.executemany(sql, params_list)
                    logger.debug(
                        f"StarRocks execute_many: {sql[:100]}... "
                        f"({len(params_list)} batches, {affected} rows affected)"
                    )
                    return affected
        except Exception as e:
            logger.error(f"StarRocks execute_many error: {e}", exc_info=True)
            return 0

    async def health_check(self) -> bool:
        """
        Check if StarRocks is healthy.

        Returns:
            True if healthy, False otherwise
        """
        if not self.enabled or not self.pool:
            return False

        try:
            result = await self.query_one("SELECT 1 as health")
            return result is not None and result.get("health") == 1
        except Exception as e:
            logger.error(f"StarRocks health check failed: {e}")
            return False


# ============================================================================
# Global Client Instance
# ============================================================================

_client: Optional[StarRocksClient] = None


def get_starrocks_client(
    host: str = "localhost",
    port: int = 9030,
    user: str = "root",
    password: str = "",
    database: str = "cortex_analytics",
) -> StarRocksClient:
    """
    Get or create global StarRocks client instance.

    Args:
        host: StarRocks host
        port: StarRocks query port
        user: Database user
        password: Database password
        database: Database name

    Returns:
        StarRocksClient instance
    """
    global _client
    if _client is None:
        _client = StarRocksClient(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )
    return _client


async def init_starrocks_client(
    host: str = "localhost",
    port: int = 9030,
    user: str = "root",
    password: str = "",
    database: str = "cortex_analytics",
) -> StarRocksClient:
    """
    Initialize and connect global StarRocks client.

    Args:
        host: StarRocks host
        port: StarRocks query port
        user: Database user
        password: Database password
        database: Database name

    Returns:
        Connected StarRocksClient instance
    """
    client = get_starrocks_client(host, port, user, password, database)
    await client.connect()
    return client


async def shutdown_starrocks_client() -> None:
    """Shutdown global StarRocks client."""
    global _client
    if _client:
        await _client.disconnect()
        _client = None
