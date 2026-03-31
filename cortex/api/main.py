"""
FastAPI Application Entry Point

Cortex-AI Platform API with authentication, RBAC, and resource management.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text as select_text

from cortex.api.middleware.auth import AuthenticationMiddleware
from cortex.api.routes import (
    # Core routes (Account, Organization, Project, Principal, Token, Membership, Document)
    auth,
    accounts,
    organizations,
    projects,
    documents,
    knowledge,  # Neo4j-based knowledge graph
    health,
)
# Non-core routes (disabled - can be added back incrementally)
# from cortex.api.routes import (
#     chat, chat_extensions, websocket_chat,  # Require Conversation, Message models
#     audit_logs,  # Requires AuditLog model
#     usage,  # Requires UsageRecord model
#     feature_flags,  # Requires FeatureFlag model
#     webhooks,  # Requires Webhook, WebhookDelivery models
#     analytics,  # Requires Message model
#     prompts, agents, skills, models, traces, api_keys,  # TBD
# )
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

    # Initialize Redis caches (Phase 1)
    try:
        from cortex.platform.cache.session import get_session_cache
        from cortex.platform.cache.history import get_history_cache
        from cortex.rag.cache import get_search_cache

        session_cache = get_session_cache()
        await session_cache.connect()
        logger.info("Session cache initialized")

        history_cache = get_history_cache()
        await history_cache.connect()
        logger.info("History cache initialized")

        search_cache = get_search_cache()
        await search_cache.connect()
        logger.info("Search cache initialized")
    except Exception as e:
        logger.warning(f"Cache initialization failed: {e}")
        logger.info("Caches disabled - will fallback to database")

    # Initialize Kafka producer (Phase 2A)
    kafka_producer = None
    if settings.kafka_enabled:
        try:
            from cortex.platform.events.kafka_producer import get_kafka_producer

            kafka_producer = get_kafka_producer()
            await kafka_producer.start()
            logger.info("Kafka producer initialized")
        except Exception as e:
            logger.warning(f"Kafka producer initialization failed: {e}")
            logger.info("Kafka disabled - events will fallback to logging")

    # Initialize WebSocket connection manager (Phase 2B)
    ws_manager = None
    if settings.websocket_enabled:
        try:
            from cortex.api.websocket.manager import get_connection_manager

            ws_manager = get_connection_manager()
            await ws_manager.start()
            logger.info(f"WebSocket manager initialized (instance: {ws_manager.instance_id})")
        except Exception as e:
            logger.warning(f"WebSocket manager initialization failed: {e}")
            logger.info("WebSocket disabled")

    # Initialize StarRocks client (Phase 3)
    starrocks_client = None
    if settings.starrocks_enabled:
        try:
            from cortex.platform.analytics.starrocks_client import get_starrocks_client

            starrocks_client = get_starrocks_client()
            await starrocks_client.connect()
            logger.info("StarRocks client initialized")
        except Exception as e:
            logger.warning(f"StarRocks client initialization failed: {e}")
            logger.info("Analytics disabled - StarRocks not available")

    yield

    # Shutdown
    logger.info("Shutting down Cortex-AI Platform API")

    # Close WebSocket connections (Phase 2B)
    if ws_manager is not None:
        try:
            await ws_manager.shutdown()
            logger.info("WebSocket manager shutdown complete")
        except Exception as e:
            logger.warning(f"WebSocket manager shutdown failed: {e}")

    # Flush and close Kafka producer (Phase 2A)
    if kafka_producer is not None:
        try:
            await kafka_producer.stop()
            logger.info("Kafka producer shutdown complete")
        except Exception as e:
            logger.warning(f"Kafka producer shutdown failed: {e}")

    # Close StarRocks client (Phase 3)
    if starrocks_client is not None:
        try:
            await starrocks_client.close()
            logger.info("StarRocks client closed")
        except Exception as e:
            logger.warning(f"StarRocks client close failed: {e}")

    # Close Redis caches (Phase 1)
    try:
        from cortex.platform.cache.session import get_session_cache
        from cortex.platform.cache.history import get_history_cache
        from cortex.rag.cache import get_search_cache

        session_cache = get_session_cache()
        await session_cache.close()

        history_cache = get_history_cache()
        await history_cache.close()

        search_cache = get_search_cache()
        await search_cache.close()

        logger.info("Caches closed")
    except Exception as e:
        logger.warning(f"Cache shutdown failed: {e}")

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

    # Session middleware (required by authlib for OAuth state)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

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
    # NOTE: Disabled - AuditLog model removed in database cleanup
    # Can be re-enabled when audit logging is added back incrementally
    # try:
    #     from cortex.api.middleware.audit import AuditMiddleware
    #     app.add_middleware(AuditMiddleware)
    #     logger.info("Audit logging middleware enabled")
    # except Exception as e:
    #     logger.warning(f"Audit middleware skipped: {e}")

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

    # Health check endpoints (Phase 4 - now in dedicated health.py module)

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

    # Register core route handlers
    app.include_router(auth.router)
    app.include_router(accounts.router)
    app.include_router(organizations.router)
    app.include_router(projects.router)
    app.include_router(documents.router)
    app.include_router(knowledge.router)  # Neo4j knowledge graph
    app.include_router(health.router)

    # Non-core routes (disabled - can be added back incrementally)
    # app.include_router(chat.router)  # Requires Conversation, Message
    # app.include_router(chat_extensions.router)  # Requires Conversation, Message
    # app.include_router(prompts.router)  # TBD
    # app.include_router(agents.router)  # TBD
    # app.include_router(skills.router)  # TBD
    # app.include_router(models.router)  # TBD
    # app.include_router(traces.router)  # TBD
    # app.include_router(api_keys.router)  # TBD
    # app.include_router(audit_logs.router)  # Requires AuditLog
    # app.include_router(usage.router)  # Requires UsageRecord
    # app.include_router(feature_flags.router)  # Requires FeatureFlag
    # app.include_router(webhooks.router)  # Requires Webhook, WebhookDelivery

    # Phase 2B: WebSocket routes (disabled - requires Conversation, Message)
    # if settings.websocket_enabled:
    #     app.include_router(websocket_chat.router)
    #     logger.info("WebSocket routes registered")

    # Phase 3: Analytics routes (disabled - requires Message model)
    # if settings.starrocks_enabled:
    #     app.include_router(analytics.router)
    #     logger.info("Analytics routes registered")

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
