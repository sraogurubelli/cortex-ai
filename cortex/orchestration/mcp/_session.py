"""Custom MCP ClientSession with progress notification support."""

from datetime import timedelta
from typing import Any, Protocol


class ProgressNotificationCallback(Protocol):
    """Protocol for progress notification callbacks."""

    async def __call__(self, params: Any) -> None:
        """Handle a progress notification from MCP server."""
        ...


async def _default_progress_callback(params: Any) -> None:
    """Default no-op progress callback."""
    pass


class CustomClientSession:
    """
    Extended MCP ClientSession that supports progress notification callbacks.

    Wraps the base ClientSession and intercepts progress notifications.
    """

    def __init__(
        self,
        read_stream,
        write_stream,
        read_timeout_seconds: timedelta | None = None,
        progress_notification_callback: ProgressNotificationCallback | None = None,
    ):
        from mcp import ClientSession
        import mcp.types as types

        self._progress_callback = (
            progress_notification_callback or _default_progress_callback
        )
        self._types = types

        # Create the underlying session
        self._session = ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=read_timeout_seconds,
        )

        # Store original notification handler
        self._original_notification_handler = self._session._received_notification

        # Override notification handler
        self._session._received_notification = self._handle_notification

    async def _handle_notification(self, notification) -> None:
        """Handle notifications, including progress notifications."""
        # Check for progress notification
        if hasattr(notification, "root"):
            if isinstance(notification.root, self._types.ProgressNotification):
                await self._progress_callback(notification.root.params)
                return

        # Fall back to original handler
        await self._original_notification_handler(notification)

    async def __aenter__(self):
        await self._session.__aenter__()
        return self

    async def __aexit__(self, *args):
        await self._session.__aexit__(*args)

    async def initialize(self):
        return await self._session.initialize()

    async def list_tools(self):
        return await self._session.list_tools()

    async def call_tool(self, name: str, arguments: dict | None = None):
        return await self._session.call_tool(name, arguments=arguments)

    async def get_prompt(self, name: str, arguments: dict | None = None):
        return await self._session.get_prompt(name, arguments=arguments)

    async def list_prompts(self, cursor: str | None = None):
        return await self._session.list_prompts(cursor=cursor)
