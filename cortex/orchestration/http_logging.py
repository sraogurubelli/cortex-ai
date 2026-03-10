"""
HTTP Request/Response Logging for debugging LLM and MCP requests.

This module provides utilities to log exact HTTP requests and responses
for both LLM API calls and MCP server calls (when using httpx transport).

Usage:
    from cortex.orchestration.http_logging import enable_http_logging
    enable_http_logging()

    # Your LLM/agent code here - all HTTP calls will be logged

    from cortex.orchestration.http_logging import disable_http_logging
    disable_http_logging()

Context Manager:
    from cortex.orchestration.http_logging import http_logging_context

    with http_logging_context():
        # HTTP requests in this block will be logged
        result = await agent.run("Hello")

Environment Variable:
    Set CORTEX_HTTP_DEBUG=1 to auto-enable on import
"""

import json
import logging
import os
import time
from typing import Any

# Create dedicated logger for HTTP debugging
http_logger = logging.getLogger("cortex.orchestration.http")

# Track original handlers/state
_logging_enabled = False
_original_transport_handle_request = None


def _format_headers(headers: dict | Any, redact_auth: bool = True) -> dict:
    """
    Format headers for logging, optionally redacting auth tokens.

    Args:
        headers: HTTP headers dict or httpx Headers object
        redact_auth: Whether to redact sensitive headers (default True)

    Returns:
        dict: Formatted headers with sensitive values redacted
    """
    if headers is None:
        return {}

    # Convert to dict if needed (httpx Headers object)
    if hasattr(headers, "items"):
        headers = dict(headers.items())
    elif hasattr(headers, "raw"):
        headers = {k.decode(): v.decode() for k, v in headers.raw}

    if not redact_auth:
        return headers

    # Redact sensitive headers
    sensitive_keys = {
        "authorization",
        "x-api-key",
        "api-key",
        "bearer",
        "token",
        "anthropic-api-key",
        "openai-api-key",
    }
    redacted = {}
    for k, v in headers.items():
        key_lower = k.lower()
        if (
            key_lower in sensitive_keys
            or "secret" in key_lower
            or "token" in key_lower
            or "key" in key_lower
        ):
            # Show first 10 chars for debugging, redact rest
            redacted[k] = f"{v[:10]}..." if len(str(v)) > 10 else "[REDACTED]"
        else:
            redacted[k] = v
    return redacted


def _format_body(body: bytes | str | None, max_length: int = 2000) -> str | None:
    """
    Format request/response body for logging.

    Args:
        body: Request/response body (bytes or str)
        max_length: Maximum length before truncation

    Returns:
        str: Formatted body (pretty-printed JSON if possible)
    """
    if body is None:
        return None

    if isinstance(body, bytes):
        try:
            body = body.decode("utf-8")
        except UnicodeDecodeError:
            return f"<binary data: {len(body)} bytes>"

    # Try to pretty-print JSON
    try:
        parsed = json.loads(body)
        formatted = json.dumps(parsed, indent=2)
        if len(formatted) > max_length:
            return (
                formatted[:max_length]
                + f"\n... (truncated, total {len(formatted)} chars)"
            )
        return formatted
    except (json.JSONDecodeError, TypeError):
        if len(body) > max_length:
            return body[:max_length] + f"\n... (truncated, total {len(body)} chars)"
        return body


def _install_httpx_hook():
    """
    Install logging hook into httpx transport.

    This intercepts all httpx HTTP requests, which includes:
    - LangChain LLM calls (ChatOpenAI, ChatAnthropic, ChatGoogleGenerativeAI)
    - MCP server calls (when using HTTP/SSE transport)

    Returns:
        bool: True if successfully installed, False otherwise
    """
    global _original_transport_handle_request

    try:
        import httpx
        from httpx._transports.default import HTTPTransport
    except ImportError:
        http_logger.warning("httpx not installed, HTTP logging not available")
        return False

    if _original_transport_handle_request is not None:
        # Already installed
        return True

    # Store original method
    _original_transport_handle_request = HTTPTransport.handle_request

    def logging_handle_request(self, request: "httpx.Request") -> "httpx.Response":
        """Wrapped handle_request that logs requests and responses."""
        # Generate unique request ID (last 8 digits of nanosecond timestamp)
        request_id = f"{time.time_ns()}"[-8:]

        # Log request
        http_logger.info(f"[{request_id}] >>> HTTP {request.method} {request.url}")
        http_logger.debug(
            f"[{request_id}] >>> Headers: {_format_headers(request.headers)}"
        )

        # Read and log body
        body = None
        if request.content:
            body = request.content
        elif hasattr(request, "read"):
            body = request.read()

        if body:
            http_logger.debug(f"[{request_id}] >>> Body:\n{_format_body(body)}")

        start_time = time.monotonic()

        try:
            response = _original_transport_handle_request(self, request)
            elapsed = time.monotonic() - start_time

            # Log response
            http_logger.info(
                f"[{request_id}] <<< HTTP {response.status_code} ({elapsed:.3f}s)"
            )
            http_logger.debug(
                f"[{request_id}] <<< Headers: {_format_headers(response.headers, redact_auth=False)}"
            )

            # Read and log response body
            # Note: For streaming responses, this may not capture everything
            if response.content:
                http_logger.debug(
                    f"[{request_id}] <<< Body:\n{_format_body(response.content)}"
                )

            return response

        except Exception as e:
            elapsed = time.monotonic() - start_time
            http_logger.error(
                f"[{request_id}] !!! Error after {elapsed:.3f}s: {type(e).__name__}: {e}"
            )
            raise

    # Monkey-patch the HTTPTransport class
    HTTPTransport.handle_request = logging_handle_request
    return True


def _uninstall_httpx_hook():
    """Remove the httpx logging hook."""
    global _original_transport_handle_request

    if _original_transport_handle_request is None:
        return

    try:
        from httpx._transports.default import HTTPTransport

        HTTPTransport.handle_request = _original_transport_handle_request
        _original_transport_handle_request = None
    except ImportError:
        pass


def enable_http_logging(
    level: int = logging.DEBUG,
    log_to_console: bool = True,
    log_to_file: str | None = None,
) -> None:
    """
    Enable HTTP request/response logging.

    This intercepts all httpx requests, which covers:
    - LangChain LLM API calls (ChatOpenAI, ChatAnthropic, etc.)
    - MCP server HTTP requests (when using HTTP/SSE transport)

    Args:
        level: Logging level (DEBUG shows bodies, INFO shows just URLs/status)
        log_to_console: Whether to print to stderr (default True)
        log_to_file: Optional file path to write logs to

    Example:
        from cortex.orchestration.http_logging import enable_http_logging
        enable_http_logging(level=logging.INFO)

        # All HTTP requests will now be logged
        agent = Agent(...)
        result = await agent.run("Hello")
    """
    global _logging_enabled

    if _logging_enabled:
        http_logger.debug("HTTP logging already enabled")
        return

    # Configure logger
    http_logger.setLevel(level)
    http_logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [HTTP] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        http_logger.addHandler(console_handler)

    if log_to_file:
        file_handler = logging.FileHandler(log_to_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        http_logger.addHandler(file_handler)

    # Install httpx hook
    if _install_httpx_hook():
        _logging_enabled = True
        http_logger.info("HTTP request logging enabled")
    else:
        http_logger.warning("Failed to enable HTTP logging")


def disable_http_logging() -> None:
    """
    Disable HTTP request/response logging.

    Example:
        from cortex.orchestration.http_logging import disable_http_logging
        disable_http_logging()
    """
    global _logging_enabled

    if not _logging_enabled:
        return

    _uninstall_httpx_hook()
    http_logger.handlers.clear()
    _logging_enabled = False

    # Use root logger since our handlers are cleared
    logging.getLogger(__name__).info("HTTP request logging disabled")


def is_http_logging_enabled() -> bool:
    """
    Check if HTTP logging is currently enabled.

    Returns:
        bool: True if HTTP logging is active, False otherwise
    """
    return _logging_enabled


class http_logging_context:
    """
    Context manager for temporary HTTP logging.

    Example:
        from cortex.orchestration.http_logging import http_logging_context

        with http_logging_context():
            # HTTP requests in this block will be logged
            result = await agent.run("Hello")
        # Logging automatically disabled after exiting context
    """

    def __init__(
        self,
        level: int = logging.DEBUG,
        log_to_console: bool = True,
        log_to_file: str | None = None,
    ):
        """
        Initialize context manager.

        Args:
            level: Logging level
            log_to_console: Whether to print to stderr
            log_to_file: Optional file path to write logs to
        """
        self.level = level
        self.log_to_console = log_to_console
        self.log_to_file = log_to_file
        self._was_enabled = False

    def __enter__(self):
        self._was_enabled = is_http_logging_enabled()
        if not self._was_enabled:
            enable_http_logging(
                level=self.level,
                log_to_console=self.log_to_console,
                log_to_file=self.log_to_file,
            )
        return self

    def __exit__(self, *args):
        if not self._was_enabled:
            disable_http_logging()


# Auto-enable if environment variable is set
if os.environ.get("CORTEX_HTTP_DEBUG", "").lower() in ("1", "true", "yes"):
    enable_http_logging()
    http_logger.info("HTTP logging auto-enabled via CORTEX_HTTP_DEBUG environment variable")
