"""
FastAPI Application Entry Point

Cortex-AI Platform API with authentication, RBAC, and resource management.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text as select_text

from cortex.api.middleware.auth import AuthenticationMiddleware
from cortex.api.routes import (
    auth, accounts, organizations, projects, chat, chat_extensions,
    documents, prompts, agents, skills, models, traces,
    api_keys, audit_logs, usage, feature_flags, webhooks,
)
from cortex.platform.config.settings import get_settings
from cortex.platform.database import init_db, close_db

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Handles startup and shutdown events:
    - Startup: Initialize database connections and checkpointer
    - Shutdown: Close database connections and checkpointer
    """
    # Startup
    logger.info("Starting Cortex-AI Platform API")
    logger.info(f"RBAC enabled: {settings.rbac_enabled}")
    logger.info(f"JWT algorithm: {settings.jwt_algorithm}")

    await init_db()
    logger.info("Database initialized")

    # Initialize OpenTelemetry tracing (if OTEL env vars are configured)
    try:
        from cortex.orchestration.observability import initialize_telemetry, is_telemetry_enabled
        initialize_telemetry(
            service_name=os.getenv("OTEL_SERVICE_NAME", "cortex-ai"),
            service_version="0.1.0",
        )
        if is_telemetry_enabled():
            logger.info("OpenTelemetry tracing initialized")
    except Exception as e:
        logger.warning(f"OpenTelemetry initialization skipped: {e}")

    # Initialize Langfuse tracing (if keys are configured)
    langfuse_client = None
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        try:
            from langfuse import Langfuse
            langfuse_client = Langfuse(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
                host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            )
            logger.info("Langfuse tracing initialized")
        except Exception as e:
            logger.warning(f"Langfuse initialization skipped: {e}")

    # Initialize checkpointer for agent session persistence
    try:
        from cortex.orchestration.session.checkpointer import open_checkpointer_pool

        await open_checkpointer_pool(
            database_url=settings.database_url,
            use_memory=settings.app_env == "development",
        )
        logger.info("Checkpointer initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize checkpointer: {e}")
        logger.info("Falling back to in-memory checkpointer")

    yield

    # Shutdown
    logger.info("Shutting down Cortex-AI Platform API")

    # Flush Langfuse
    if langfuse_client is not None:
        try:
            langfuse_client.flush()
            logger.info("Langfuse flushed")
        except Exception as e:
            logger.warning(f"Langfuse flush failed: {e}")

    # Shutdown OpenTelemetry
    try:
        from cortex.orchestration.observability import shutdown_telemetry
        shutdown_telemetry()
        logger.info("OpenTelemetry shutdown complete")
    except Exception as e:
        logger.warning(f"OpenTelemetry shutdown failed: {e}")

    # Close checkpointer
    try:
        from cortex.orchestration.session.checkpointer import close_checkpointer_pool

        await close_checkpointer_pool()
        logger.info("Checkpointer closed")
    except Exception as e:
        logger.warning(f"Failed to close checkpointer: {e}")

    await close_db()
    logger.info("Database connections closed")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="Cortex-AI Platform API",
        description="Enterprise-grade AI orchestration platform with multi-agent coordination, RAG, and RBAC",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.app_env != "production" else None,
        redoc_url="/api/redoc" if settings.app_env != "production" else None,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        """Add unique request ID to each request."""
        import uuid
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # Logging middleware
    @app.middleware("http")
    async def logging_middleware(request: Request, call_next):
        """Log all HTTP requests."""
        import time

        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Log request
        logger.info(
            f"HTTP {request.method} {request.url.path} - "
            f"Status: {response.status_code} - "
            f"Duration: {duration_ms}ms - "
            f"Request-ID: {request.state.request_id}"
        )

        return response

    # Prometheus metrics middleware (optional)
    from cortex.api.middleware.metrics import is_prometheus_enabled, PrometheusMetricsMiddleware, add_metrics_endpoint
    if is_prometheus_enabled():
        app.add_middleware(PrometheusMetricsMiddleware)
        add_metrics_endpoint(app)
        logger.info("Prometheus metrics middleware enabled")

    # Authentication middleware (always active — validates JWT and sets request.state.principal)
    app.add_middleware(AuthenticationMiddleware)
    logger.info("Authentication middleware enabled")

    # Rate limiting middleware (Redis-backed, per-principal/IP)
    try:
        from cortex.api.middleware.rate_limit import RateLimitMiddleware
        app.add_middleware(RateLimitMiddleware)
        logger.info("Rate limiting middleware enabled")
    except Exception as e:
        logger.warning(f"Rate limiting middleware skipped: {e}")

    # Audit logging middleware (records mutations to audit_logs table)
    try:
        from cortex.api.middleware.audit import AuditMiddleware
        app.add_middleware(AuditMiddleware)
        logger.info("Audit logging middleware enabled")
    except Exception as e:
        logger.warning(f"Audit middleware skipped: {e}")

    # Exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Global exception handler for unhandled errors."""
        logger.error(
            f"Unhandled exception: {exc}",
            exc_info=True,
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "path": request.url.path,
                "method": request.method,
            }
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": "An unexpected error occurred. Please try again later.",
                "request_id": getattr(request.state, "request_id", None),
            }
        )

    # Health check endpoint (liveness)
    @app.get("/health", tags=["health"])
    async def health_check():
        """Lightweight liveness probe -- always returns 200 if the process is up."""
        return {
            "status": "healthy",
            "service": "cortex-ai-platform",
            "version": "0.1.0",
        }

    # Deep readiness probe (checks all backends)
    @app.get("/ready", tags=["health"])
    async def readiness_check():
        """Deep readiness probe that verifies DB, Redis, Qdrant, and checkpointer connectivity."""
        import time as _time

        checks: dict = {}
        overall = True
        start = _time.monotonic()

        # Database (PostgreSQL)
        try:
            from cortex.platform.database.session import get_db_manager
            db = get_db_manager()
            async with db.session() as session:
                await session.execute(select_text("SELECT 1"))
            checks["database"] = {"status": "ok"}
        except Exception as e:
            checks["database"] = {"status": "error", "detail": str(e)[:200]}
            overall = False

        # Redis
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
            await r.ping()
            await r.aclose()
            checks["redis"] = {"status": "ok"}
        except Exception as e:
            checks["redis"] = {"status": "error", "detail": str(e)[:200]}
            overall = False

        # Checkpointer (LangGraph state DB)
        try:
            from cortex.orchestration.session.checkpointer import is_checkpointer_healthy
            healthy = await is_checkpointer_healthy()
            checks["checkpointer"] = {"status": "ok" if healthy else "degraded"}
            if not healthy:
                overall = False
        except Exception as e:
            checks["checkpointer"] = {"status": "error", "detail": str(e)[:200]}
            overall = False

        elapsed_ms = int((_time.monotonic() - start) * 1000)

        payload = {
            "status": "ready" if overall else "not_ready",
            "checks": checks,
            "elapsed_ms": elapsed_ms,
        }

        if not overall:
            return JSONResponse(status_code=503, content=payload)
        return payload

    @app.get("/", tags=["root"])
    async def root():
        """
        Root endpoint with API information.

        Returns:
            API metadata
        """
        return {
            "service": "Cortex-AI Platform API",
            "version": "0.1.0",
            "description": "Enterprise-grade AI orchestration platform",
            "docs": "/api/docs" if settings.app_env != "production" else None,
        }

    # Register route handlers
    app.include_router(auth.router)
    app.include_router(accounts.router)
    app.include_router(organizations.router)
    app.include_router(projects.router)
    app.include_router(chat.router)
    app.include_router(chat_extensions.router)
    app.include_router(documents.router)
    app.include_router(prompts.router)
    app.include_router(agents.router)
    app.include_router(skills.router)
    app.include_router(models.router)
    app.include_router(traces.router)
    app.include_router(api_keys.router)
    app.include_router(audit_logs.router)
    app.include_router(usage.router)
    app.include_router(feature_flags.router)
    app.include_router(webhooks.router)

    logger.info("All route handlers registered")

    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "cortex.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )
