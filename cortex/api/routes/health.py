"""
Health Check Endpoints

Kubernetes-compatible health checks for liveness and readiness probes.

Endpoints:
- GET /health - Liveness probe (is the app alive?)
- GET /health/ready - Readiness probe (is the app ready to serve traffic?)
- GET /health/startup - Startup probe (has the app finished initialization?)

Usage:
    # Kubernetes probes
    livenessProbe:
      httpGet:
        path: /health
        port: 8000

    readinessProbe:
      httpGet:
        path: /health/ready
        port: 8000
"""

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel

from cortex.platform.database import get_db_manager
from cortex.platform.analytics.starrocks_client import get_starrocks_client
from cortex.platform.events.kafka_producer import get_kafka_producer
from cortex.api.websocket.manager import get_connection_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


# ============================================================================
# Response Models
# ============================================================================


class HealthStatus(BaseModel):
    """Health status response."""

    status: Literal["healthy", "degraded", "unhealthy"]
    timestamp: datetime
    checks: dict[str, bool]
    message: str


# ============================================================================
# Health Check Endpoints
# ============================================================================


@router.get("/health", response_model=HealthStatus)
async def health_check():
    """
    Liveness probe.

    Checks if the application is alive and can respond to requests.
    Does NOT check external dependencies (database, Redis, etc.)

    Returns:
        200: App is alive
        503: App is dead (should be restarted)
    """
    return HealthStatus(
        status="healthy",
        timestamp=datetime.utcnow(),
        checks={"application": True},
        message="Application is running",
    )


@router.get("/health/ready", response_model=HealthStatus)
async def readiness_check():
    """
    Readiness probe.

    Checks if the application is ready to serve traffic.
    Checks critical dependencies: database, Redis (if enabled)

    Returns:
        200: App is ready to serve traffic
        503: App is not ready (remove from load balancer)
    """
    checks = {}
    all_healthy = True

    # Check database
    try:
        db_manager = get_db_manager()
        async with db_manager.session() as session:
            await session.execute("SELECT 1")
        checks["database"] = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        checks["database"] = False
        all_healthy = False

    # Check Redis (graceful degradation if not critical)
    try:
        import redis.asyncio as aioredis
        from cortex.platform.config.settings import get_settings

        settings = get_settings()
        redis_client = await aioredis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            decode_responses=True,
        )
        await redis_client.ping()
        await redis_client.close()
        checks["redis"] = True
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        checks["redis"] = False
        # Redis failure is not critical (graceful degradation)
        # all_healthy = False  # Uncomment to make Redis required

    # Overall status
    if all_healthy:
        status_code = "healthy"
        message = "All critical systems healthy"
        http_status = status.HTTP_200_OK
    else:
        status_code = "degraded"
        message = "Some systems unhealthy"
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE

    response = HealthStatus(
        status=status_code,
        timestamp=datetime.utcnow(),
        checks=checks,
        message=message,
    )

    if http_status == status.HTTP_503_SERVICE_UNAVAILABLE:
        # Return 503 for Kubernetes to remove from service
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.dict(),
        )

    return response


@router.get("/health/startup", response_model=HealthStatus)
async def startup_check():
    """
    Startup probe.

    Checks if the application has finished initialization.
    Used to delay liveness/readiness probes during slow startup.

    Returns:
        200: App has finished startup
        503: App is still starting up
    """
    checks = {}
    all_ready = True

    # Check database connection
    try:
        db_manager = get_db_manager()
        async with db_manager.session() as session:
            await session.execute("SELECT 1")
        checks["database"] = True
    except Exception as e:
        logger.error(f"Database startup check failed: {e}")
        checks["database"] = False
        all_ready = False

    # Check if schema exists (migrations completed)
    try:
        db_manager = get_db_manager()
        async with db_manager.session() as session:
            result = await session.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"
            )
            table_count = result.scalar()
            checks["schema"] = table_count > 0
            if table_count == 0:
                all_ready = False
    except Exception as e:
        logger.error(f"Schema check failed: {e}")
        checks["schema"] = False
        all_ready = False

    # Overall status
    if all_ready:
        status_code = "healthy"
        message = "Application startup complete"
        http_status = status.HTTP_200_OK
    else:
        status_code = "unhealthy"
        message = "Application still starting up"
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE

    response = HealthStatus(
        status=status_code,
        timestamp=datetime.utcnow(),
        checks=checks,
        message=message,
    )

    if http_status == status.HTTP_503_SERVICE_UNAVAILABLE:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.dict(),
        )

    return response


@router.get("/health/detailed", response_model=dict)
async def detailed_health_check():
    """
    Detailed health check (for monitoring/debugging).

    Checks all subsystems including optional ones.

    Returns:
        Detailed health status with all subsystems
    """
    checks = {}

    # Database
    try:
        db_manager = get_db_manager()
        async with db_manager.session() as session:
            await session.execute("SELECT 1")
        checks["database"] = {"status": "healthy", "message": "Connected"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "message": str(e)}

    # Redis
    try:
        import redis.asyncio as aioredis
        from cortex.platform.config.settings import get_settings

        settings = get_settings()
        redis_client = await aioredis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            decode_responses=True,
        )
        await redis_client.ping()
        await redis_client.close()
        checks["redis"] = {"status": "healthy", "message": "Connected"}
    except Exception as e:
        checks["redis"] = {"status": "unhealthy", "message": str(e)}

    # Kafka (optional)
    try:
        from cortex.platform.config.settings import get_settings

        settings = get_settings()
        if settings.kafka_enabled:
            kafka_producer = get_kafka_producer()
            if kafka_producer.enabled:
                checks["kafka"] = {"status": "healthy", "message": "Producer enabled"}
            else:
                checks["kafka"] = {"status": "degraded", "message": "Producer disabled (fallback mode)"}
        else:
            checks["kafka"] = {"status": "disabled", "message": "Kafka disabled in config"}
    except Exception as e:
        checks["kafka"] = {"status": "unhealthy", "message": str(e)}

    # StarRocks (optional)
    try:
        from cortex.platform.config.settings import get_settings

        settings = get_settings()
        if settings.starrocks_enabled:
            starrocks_client = get_starrocks_client()
            is_healthy = await starrocks_client.health_check()
            if is_healthy:
                checks["starrocks"] = {"status": "healthy", "message": "Connected"}
            else:
                checks["starrocks"] = {"status": "degraded", "message": "Not connected (fallback mode)"}
        else:
            checks["starrocks"] = {"status": "disabled", "message": "StarRocks disabled in config"}
    except Exception as e:
        checks["starrocks"] = {"status": "unhealthy", "message": str(e)}

    # WebSocket connection manager
    try:
        manager = get_connection_manager()
        stats = manager.get_stats()
        checks["websocket"] = {
            "status": "healthy",
            "message": f"{stats['total_subscribers']} connections across {stats['total_rooms']} rooms",
            "stats": stats,
        }
    except Exception as e:
        checks["websocket"] = {"status": "unhealthy", "message": str(e)}

    # Overall status
    critical_systems = ["database"]
    critical_healthy = all(
        checks.get(sys, {}).get("status") == "healthy"
        for sys in critical_systems
    )

    return {
        "status": "healthy" if critical_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
    }
