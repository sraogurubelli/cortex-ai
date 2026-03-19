"""
FastAPI Application Entry Point

Cortex-AI Platform API with authentication, RBAC, and resource management.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cortex.api.middleware.auth import AuthenticationMiddleware
from cortex.api.routes import auth, accounts, organizations, projects, chat
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

    # Authentication middleware (only if RBAC is enabled)
    if settings.rbac_enabled:
        app.add_middleware(AuthenticationMiddleware)
        logger.info("Authentication middleware enabled")

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

    # Health check endpoint
    @app.get("/health", tags=["health"])
    async def health_check():
        """
        Health check endpoint.

        Returns:
            Health status of the service
        """
        return {
            "status": "healthy",
            "service": "cortex-ai-platform",
            "version": "0.1.0",
        }

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
