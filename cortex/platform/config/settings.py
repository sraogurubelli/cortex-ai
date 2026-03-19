"""
Platform Settings Module

Pydantic-based settings for Cortex platform features.
Loads configuration from environment variables.
"""

from typing import Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PlatformSettings(BaseSettings):
    """Platform configuration settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================================
    # Application
    # =========================================================================
    app_name: str = Field(default="cortex-ai", description="Application name")
    app_env: Literal["development", "staging", "production"] = Field(
        default="development", description="Application environment"
    )
    debug: bool = Field(default=False, description="Debug mode")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )
    log_format: Literal["json", "text"] = Field(
        default="json", description="Log format"
    )

    # =========================================================================
    # API Server
    # =========================================================================
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port", gt=0, lt=65536)
    api_workers: int = Field(default=4, description="Number of API workers", gt=0)

    # =========================================================================
    # Security & Authentication
    # =========================================================================
    secret_key: str = Field(
        ..., description="Secret key for signing tokens (required)"
    )
    jwt_secrets: list[str] = Field(
        ..., description="JWT signing secrets (comma-separated, supports rotation)"
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_access_token_expire_minutes: int = Field(
        default=60, description="Access token expiration in minutes", gt=0
    )
    jwt_refresh_token_expire_days: int = Field(
        default=30, description="Refresh token expiration in days", gt=0
    )

    allowed_hosts: list[str] = Field(
        default=["localhost", "127.0.0.1"],
        description="Allowed hosts for CORS",
    )

    # CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="CORS allowed origins",
    )
    cors_allow_credentials: bool = Field(
        default=True, description="Allow credentials in CORS"
    )

    # =========================================================================
    # Authorization (RBAC)
    # =========================================================================
    rbac_enabled: bool = Field(
        default=True, description="Enable RBAC authorization"
    )
    permission_cache_ttl_seconds: int = Field(
        default=15, description="Permission cache TTL in seconds", gt=0
    )
    admin_emails: list[str] = Field(
        default=[], description="Bootstrap admin user emails"
    )

    # =========================================================================
    # Database (PostgreSQL)
    # =========================================================================
    database_url: str = Field(
        ..., description="PostgreSQL connection URL (required)"
    )
    database_pool_size: int = Field(
        default=20, description="Database connection pool size", gt=0
    )
    database_max_overflow: int = Field(
        default=10, description="Database max overflow connections", gt=0
    )
    database_echo: bool = Field(
        default=False, description="Echo SQL queries to logs"
    )

    # =========================================================================
    # Redis (Cache & Sessions)
    # =========================================================================
    redis_url: str = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )
    redis_max_connections: int = Field(
        default=50, description="Redis max connections", gt=0
    )
    redis_socket_timeout: int = Field(
        default=5, description="Redis socket timeout in seconds", gt=0
    )
    redis_socket_connect_timeout: int = Field(
        default=5, description="Redis socket connect timeout in seconds", gt=0
    )

    # Cache TTLs
    cache_ttl_embeddings: int = Field(
        default=3600, description="Embeddings cache TTL in seconds", gt=0
    )
    cache_ttl_search: int = Field(
        default=300, description="Search cache TTL in seconds", gt=0
    )
    cache_ttl_session: int = Field(
        default=86400, description="Session cache TTL in seconds", gt=0
    )

    # =========================================================================
    # Streaming (SSE)
    # =========================================================================
    sse_keepalive_interval_seconds: int = Field(
        default=30, description="SSE keepalive ping interval in seconds", gt=0
    )
    sse_connection_timeout_hours: int = Field(
        default=2, description="SSE connection timeout in hours", gt=0
    )

    # =========================================================================
    # Task Queue
    # =========================================================================
    redis_stream_name: str = Field(
        default="cortex:tasks", description="Redis stream name for task queue"
    )
    redis_consumer_group: str = Field(
        default="cortex-workers", description="Redis consumer group for task queue"
    )
    task_queue_workers: int = Field(
        default=4, description="Number of task queue workers", gt=0
    )

    # =========================================================================
    # Migrations
    # =========================================================================
    auto_migrate: bool = Field(
        default=False, description="Run database migrations on startup"
    )

    # =========================================================================
    # Validators
    # =========================================================================
    @field_validator("jwt_secrets", mode="before")
    @classmethod
    def parse_jwt_secrets(cls, v):
        """Parse JWT secrets from comma-separated string or list."""
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v):
        """Parse allowed hosts from comma-separated string or list."""
        if isinstance(v, str):
            return [h.strip() for h in v.split(",") if h.strip()]
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("admin_emails", mode="before")
    @classmethod
    def parse_admin_emails(cls, v):
        """Parse admin emails from comma-separated string or list."""
        if isinstance(v, str):
            return [e.strip() for e in v.split(",") if e.strip()]
        return v


# Global settings instance
_settings: PlatformSettings | None = None


def get_settings() -> PlatformSettings:
    """
    Get global settings instance (singleton pattern).

    Returns:
        PlatformSettings instance
    """
    global _settings
    if _settings is None:
        _settings = PlatformSettings()
    return _settings


def reload_settings() -> PlatformSettings:
    """
    Reload settings from environment (useful for testing).

    Returns:
        New PlatformSettings instance
    """
    global _settings
    _settings = PlatformSettings()
    return _settings
